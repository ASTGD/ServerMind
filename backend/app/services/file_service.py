"""File service — SFTP-based remote file operations for Linux/Unix servers.

All blocking Paramiko calls are run in a dedicated ThreadPoolExecutor so
the async FastAPI event loop is never blocked.
"""
from __future__ import annotations

import asyncio
import io
import logging
import posixpath
import stat as stat_module
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import paramiko

from app.models.server import Server
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

# Dedicated thread pool for SFTP I/O (separate from SSH exec pool)
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="sftp")

# Maximum bytes to load into the in-browser editor (2 MB)
MAX_READ_BYTES = 2 * 1024 * 1024

# Maximum size for a server→server mission transfer, streamed through the backend
# (never held fully in memory). Big enough for real site/db backups, small enough
# to keep one transfer from monopolising the SFTP pool.
MAX_TRANSFER_BYTES = 512 * 1024 * 1024

_TRANSFER_CHUNK = 256 * 1024


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_sftp(server: Server) -> paramiko.SFTPClient:
    """Open an SFTP channel on the server's pooled SSH connection."""
    from app.services.ssh_service import _get_client  # reuse existing SSH pool

    credential = decrypt(server.encrypted_cred)
    # The pin, like every other caller. Omitting it skipped identity verification AND put
    # the unverified connection in the shared pool, so every later operation inherited it —
    # which is how a rebuilt server went on reporting "online" with no "trust the new key".
    ssh = _get_client(
        str(server.id), server.host, server.port,
        server.username, server.auth_type, credential,
        expected_fingerprint=server.fingerprint,
    )
    return ssh.open_sftp()


def _attr_to_dict(name: str, base_dir: str, attr: paramiko.SFTPAttributes) -> dict:
    """Convert a Paramiko SFTPAttributes to a plain dict for serialisation."""
    mode = attr.st_mode or 0

    if stat_module.S_ISDIR(mode):
        ftype = "dir"
    elif stat_module.S_ISLNK(mode):
        ftype = "link"
    else:
        ftype = "file"

    modified: datetime | None = None
    if attr.st_mtime:
        modified = datetime.fromtimestamp(attr.st_mtime, tz=timezone.utc)

    return {
        "name": name,
        "path": posixpath.join(base_dir, name),
        "type": ftype,
        "size": attr.st_size,
        "permissions": stat_module.filemode(mode),
        "modified": modified,
    }


def _normalise(path: str) -> str:
    """Normalise a POSIX path — collapse ../  and ensure a leading slash."""
    p = posixpath.normpath("/" + path.lstrip("/"))
    return p if p else "/"


# ── Blocking implementations ──────────────────────────────────────────────────

def _list_dir(server: Server, path: str) -> list[dict]:
    sftp = _get_sftp(server)
    try:
        attrs = sftp.listdir_attr(path)
        entries = []
        for a in attrs:
            if a.filename and not a.filename.startswith("."):
                entries.append(_attr_to_dict(a.filename, path, a))
        # Dirs first, then files; alpha within each group
        entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
        return entries
    finally:
        sftp.close()


def _list_dir_all(server: Server, path: str) -> list[dict]:
    """Like _list_dir but includes dot-files."""
    sftp = _get_sftp(server)
    try:
        attrs = sftp.listdir_attr(path)
        entries = []
        for a in attrs:
            if a.filename:
                entries.append(_attr_to_dict(a.filename, path, a))
        entries.sort(key=lambda e: (0 if e["type"] == "dir" else 1, e["name"].lower()))
        return entries
    finally:
        sftp.close()


def _read_file(server: Server, path: str) -> dict:
    sftp = _get_sftp(server)
    try:
        s = sftp.stat(path)
        size = int(s.st_size or 0)
        with sftp.open(path, "rb") as fh:
            raw = fh.read(MAX_READ_BYTES)
        # Attempt UTF-8, then latin-1, then mark as binary
        try:
            content = raw.decode("utf-8")
            is_binary = False
        except UnicodeDecodeError:
            try:
                content = raw.decode("latin-1")
                is_binary = False
            except UnicodeDecodeError:
                content = f"(Binary file — {size:,} bytes — cannot display in editor)"
                is_binary = True
        return {"content": content, "is_binary": is_binary, "size": size}
    finally:
        sftp.close()


def _write_file(server: Server, path: str, content: str) -> None:
    sftp = _get_sftp(server)
    try:
        with sftp.open(path, "w") as fh:
            fh.write(content)
    finally:
        sftp.close()


def _write_private_file(server: Server, path: str, content: str) -> None:
    """Write a file only its owner can read, with no moment where that is untrue.

    The order is what matters. Creating the file, writing it, and then restricting it
    leaves a window in which the contents are world-readable — short, but long enough on
    a shared server, and this is used for files that hold a password. So: create
    exclusively (an existing path is an error, never something we follow, which is what
    stops another user pre-planting a symlink), restrict it while it is still empty, and
    only then write.
    """
    sftp = _get_sftp(server)
    try:
        with sftp.open(path, "wx") as fh:
            fh.chmod(0o600)
            fh.write(content)
    finally:
        sftp.close()


def _mkdir(server: Server, path: str) -> None:
    sftp = _get_sftp(server)
    try:
        sftp.mkdir(path)
    finally:
        sftp.close()


def _rm_recursive(sftp: paramiko.SFTPClient, path: str) -> None:
    """Recursively remove path (file or directory tree)."""
    try:
        st = sftp.stat(path)
    except FileNotFoundError:
        return
    if stat_module.S_ISDIR(st.st_mode or 0):
        for entry in sftp.listdir_attr(path):
            if entry.filename:
                _rm_recursive(sftp, posixpath.join(path, entry.filename))
        sftp.rmdir(path)
    else:
        sftp.remove(path)


def _delete(server: Server, path: str) -> None:
    sftp = _get_sftp(server)
    try:
        _rm_recursive(sftp, path)
    finally:
        sftp.close()


def _rename(server: Server, old_path: str, new_path: str) -> None:
    sftp = _get_sftp(server)
    try:
        sftp.rename(old_path, new_path)
    finally:
        sftp.close()


def _upload(server: Server, path: str, data: bytes) -> None:
    sftp = _get_sftp(server)
    try:
        with sftp.open(path, "wb") as fh:
            fh.write(data)
    finally:
        sftp.close()


def _download(server: Server, path: str) -> bytes:
    sftp = _get_sftp(server)
    try:
        buf = io.BytesIO()
        sftp.getfo(path, buf)
        return buf.getvalue()
    finally:
        sftp.close()


# ── Public async API ──────────────────────────────────────────────────────────

async def list_dir(server: Server, path: str, show_hidden: bool = False) -> list[dict]:
    """Return a sorted directory listing as a list of dicts."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    fn = _list_dir_all if show_hidden else _list_dir
    return await loop.run_in_executor(_executor, fn, server, p)


async def read_file(server: Server, path: str) -> dict:
    """Read a text file. Returns {content, is_binary, size}."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _read_file, server, p)


async def write_file(server: Server, path: str, content: str) -> None:
    """Overwrite a remote file with new text content."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _write_file, server, p, content)


async def write_private(server: Server, path: str, content: str) -> None:
    """Create a new file readable only by its owner. Fails if the path already exists."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _write_private_file, server, p, content)


async def make_dir(server: Server, path: str) -> None:
    """Create a single directory level."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _mkdir, server, p)


async def delete_path(server: Server, path: str) -> None:
    """Delete a file or recursively remove a directory tree."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _delete, server, p)


async def rename_path(server: Server, old_path: str, new_path: str) -> None:
    """Rename or move a file/directory."""
    old_p = _normalise(old_path)
    new_p = _normalise(new_path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _rename, server, old_p, new_p)


async def upload_file(server: Server, path: str, data: bytes) -> None:
    """Write raw bytes to a remote path."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(_executor, _upload, server, p, data)


async def download_file(server: Server, path: str) -> bytes:
    """Read the full raw content of a remote file."""
    p = _normalise(path)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _download, server, p)


# ── Server→server transfer (Ally Missions Stage 2) ────────────────────────────

def _transfer(src: Server, src_path: str, dst: Server, dst_path: str) -> int:
    """Stream ONE file src→dst through the backend in chunks. The servers never talk
    to each other (no shared keys). Refuses directories, oversized files, and an
    existing destination (transfers never overwrite). Returns bytes copied."""
    s_sftp = _get_sftp(src)
    try:
        st = s_sftp.stat(src_path)
        if stat_module.S_ISDIR(st.st_mode or 0):
            raise ValueError("The source is a folder — pack it into one file first (tar/zip).")
        size = st.st_size or 0
        if size > MAX_TRANSFER_BYTES:
            raise ValueError(
                f"The file is {size / 1_000_000:.0f} MB — transfers are capped at "
                f"{MAX_TRANSFER_BYTES / 1_000_000:.0f} MB."
            )
        d_sftp = _get_sftp(dst)
        try:
            try:
                d_sftp.stat(dst_path)
                raise ValueError("The destination file already exists — use a new filename.")
            except IOError:
                pass  # not there — good
            with s_sftp.open(src_path, "rb") as sf, d_sftp.open(dst_path, "wb") as df:
                sf.prefetch()
                copied = 0
                while True:
                    chunk = sf.read(_TRANSFER_CHUNK)
                    if not chunk:
                        break
                    df.write(chunk)
                    copied += len(chunk)
            return copied
        finally:
            d_sftp.close()
    finally:
        s_sftp.close()


async def transfer_between(src: Server, src_path: str, dst: Server, dst_path: str) -> int:
    """Copy one file from ``src`` to ``dst`` via the backend (SFTP both ways).
    Returns the number of bytes copied; raises ValueError with a plain message on
    guard failures (directory / too big / destination exists)."""
    sp, dp = _normalise(src_path), _normalise(dst_path)
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _transfer, src, sp, dst, dp)
