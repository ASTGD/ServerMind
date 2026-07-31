"""SSH service — Paramiko-based connection management for Linux/Unix servers."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import paramiko

from app.config import settings
from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

# Thread pool for blocking Paramiko I/O
_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="ssh")

# In-memory SSH client pool: {server_id_str: paramiko.SSHClient}
_pool: dict[str, paramiko.SSHClient] = {}

# Host-key fingerprint observed on the most recent connect per server, so a caller
# with a DB session can persist it for trust-on-first-use (Risk 3).
_fingerprints: dict[str, str] = {}


class CommandError(Exception):
    """Raised when a streamed command finishes with a non-zero exit status.

    Lets callers (playbook runner, AI chat) detect script failure even though
    the output streamed fine — a non-zero shell exit is a failure, not an I/O
    error. ``winrm_service`` imports and raises this too for parity.
    """

    def __init__(self, exit_code: int) -> None:
        self.exit_code = exit_code
        super().__init__(f"command exited with status {exit_code}")


class CommandStalled(Exception):
    """Raised when a streamed command produces no output for too long (likely
    waiting for interactive input it can't receive) or exceeds the max runtime.

    Carries the tail of recent output so the caller can show the user what the
    command was stuck on — e.g. an unanswered prompt (Update 16, Phase A).
    """

    def __init__(self, last_output: str, reason: str = "idle") -> None:
        self.last_output = last_output
        self.reason = reason  # "idle" | "max_runtime"
        super().__init__(f"command stalled ({reason})")


# User-facing note shown when a streamed command stalls (Update 16, Phase A).
STALL_NOTE = (
    "⏱ No output for a while — this looks stuck, most likely waiting for an answer "
    "it can't get. Stopped. Nothing was broken; you can try again, or run it in the "
    "Terminal to answer by hand."
)


class HostKeyMismatch(Exception):
    """Raised when a server presents a host key different from the one pinned on
    first connect — the server's identity changed (rebuilt / IP reused) or the
    connection is being intercepted. We refuse rather than connect (Risk 3)."""

    def __init__(self, expected: str, actual: str) -> None:
        self.expected = expected
        self.actual = actual
        super().__init__(
            "Server identity changed — the host key does not match the one trusted "
            "before. The server may have been rebuilt, or the connection may be "
            "intercepted. Refused for safety."
        )


def is_host_key_mismatch(exc: BaseException | None) -> bool:
    """True when a failure is a pinned-host-key mismatch (server identity changed)."""
    return isinstance(exc, HostKeyMismatch)


def _key_classes() -> tuple:
    """The private-key formats this paramiko build can actually read.

    Built from what is installed rather than written out, because the list is not stable:
    paramiko 5 removed ``DSSKey`` (DSA has been disabled in OpenSSH for years), and naming
    it directly raised AttributeError before a single key was tried — so EVERY key login
    failed, not just DSA ones, the moment paramiko was upgraded. requirements.txt pins an
    older version, which is exactly why nobody noticed.

    Ordered most-likely-first; each is tried in turn until one parses the key.
    """
    names = ("RSAKey", "Ed25519Key", "ECDSAKey", "DSSKey")
    return tuple(cls for cls in (getattr(paramiko, n, None) for n in names) if cls)


def _key_fingerprint(key: paramiko.PKey) -> str:
    """OpenSSH-style SHA256 fingerprint of a host key, e.g. 'SHA256:abc…'."""
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def pop_captured_fingerprint(server_id: str) -> str | None:
    """Return (and clear) the host-key fingerprint captured on the last connect for
    this server, so the caller can persist it (trust-on-first-use)."""
    return _fingerprints.pop(server_id, None)


def is_auth_error(exc: BaseException | None = None, message: str | None = None) -> bool:
    """True when a connection failure is an authentication failure (wrong
    password/key) — i.e. the stored credentials are stale, as opposed to the server
    being unreachable. Used to flag servers that need their password updated."""
    if isinstance(exc, paramiko.AuthenticationException):
        return True
    text = message if message is not None else (str(exc) if exc else "")
    return "authentication failed" in text.lower()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(host: str, port: int, username: str, auth_type: str, credential: str) -> tuple[paramiko.SSHClient, str]:
    """Open an authenticated SSHClient and capture its host-key fingerprint (blocking).

    AutoAddPolicy accepts the key at the transport level; identity verification
    against a pinned fingerprint happens in _get_client (Risk 3)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if auth_type == "password":
        client.connect(host, port=port, username=username, password=credential, timeout=15, banner_timeout=15)
    else:
        # auth_type == "key" — credential is the PEM private key string
        key_file = io.StringIO(credential)
        pkey = None
        for key_class in _key_classes():
            try:
                key_file.seek(0)
                pkey = key_class.from_private_key(key_file)
                break
            except Exception:
                continue
        if pkey is None:
            raise ValueError("Unrecognised private key format")
        client.connect(host, port=port, username=username, pkey=pkey, timeout=15, banner_timeout=15)

    host_key = client.get_transport().get_remote_server_key()
    return client, _key_fingerprint(host_key)


def _get_client(
    server_id: str, host: str, port: int, username: str, auth_type: str, credential: str,
    expected_fingerprint: str | None = None,
) -> paramiko.SSHClient:
    """Return a pooled client, reconnecting if the transport is dead.

    On a fresh connect, the server's host-key fingerprint is checked against
    ``expected_fingerprint`` (the pinned one); a mismatch raises HostKeyMismatch and
    the connection is refused. The observed fingerprint is stashed for the caller to
    persist on first connect (trust-on-first-use) (Risk 3)."""
    existing = _pool.get(server_id)
    if existing and existing.get_transport() and existing.get_transport().is_active():
        return existing
    client, fingerprint = _make_client(host, port, username, auth_type, credential)
    if expected_fingerprint and fingerprint != expected_fingerprint:
        try:
            client.close()
        except Exception:
            pass
        raise HostKeyMismatch(expected_fingerprint, fingerprint)
    _fingerprints[server_id] = fingerprint
    _pool[server_id] = client
    return client


# ── Public API ────────────────────────────────────────────────────────────────

async def test_connection(
    server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str,
    expected_fingerprint: str | None = None,
) -> dict:
    """Test SSH connectivity and verify server identity.

    Returns {'ok', 'latency_ms', 'error', 'fingerprint', 'host_key_changed'}. On a
    pinned-key mismatch the connect is refused and host_key_changed is True (Risk 3)."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _test() -> dict:
        t0 = time.monotonic()
        try:
            client = _get_client(server_id, host, port, username, auth_type, credential, expected_fingerprint)
            _, stdout, _ = client.exec_command("echo ok", timeout=10)
            stdout.read()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {
                "ok": True, "latency_ms": latency_ms, "error": None,
                "fingerprint": _fingerprints.get(server_id), "host_key_changed": False,
            }
        except HostKeyMismatch as exc:
            return {
                "ok": False, "latency_ms": 0, "error": str(exc),
                "fingerprint": exc.actual, "host_key_changed": True,
            }
        except Exception as exc:
            return {
                "ok": False, "latency_ms": 0, "error": str(exc),
                "fingerprint": None, "host_key_changed": False,
            }

    return await loop.run_in_executor(_executor, _test)


async def execute(server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str, expected_fingerprint: str | None = None) -> tuple[str, str, int]:
    """Execute a command and return (stdout, stderr, exit_code)."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _run() -> tuple[str, str, int]:
        client = _get_client(server_id, host, port, username, auth_type, credential, expected_fingerprint)
        _, stdout, stderr = client.exec_command(command, timeout=60)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code

    return await loop.run_in_executor(_executor, _run)


async def execute_stream(server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str, expected_fingerprint: str | None = None) -> AsyncIterator[str]:
    """Execute a command and yield stdout/stderr lines as they arrive.

    Watches for stalls (Update 16, Phase A): if no output arrives for
    SSH_IDLE_TIMEOUT_SECONDS — likely a prompt waiting for input it can't get — or
    the command runs past SSH_MAX_RUNTIME_SECONDS, the channel is closed and
    CommandStalled is raised carrying the tail of recent output.
    """
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    result: dict[str, object] = {"exit_code": None, "stalled": None, "last_output": "", "error": None}
    idle_timeout = settings.SSH_IDLE_TIMEOUT_SECONDS
    max_runtime = settings.SSH_MAX_RUNTIME_SECONDS

    def _stream() -> None:
        tail = b""  # rolling tail of recent raw output, shown if the command stalls
        try:
            client = _get_client(server_id, host, port, username, auth_type, credential, expected_fingerprint)
            transport = client.get_transport()
            channel = transport.open_session()
            # Merge stderr into the same stream. Installers (apt, pip, etc.) write
            # most of their progress to stderr — without this the live output looks
            # frozen until the final stdout line. This mirrors what a real terminal
            # shows (interleaved stdout + stderr).
            channel.set_combine_stderr(True)
            channel.exec_command(command)
            channel.settimeout(0.5)

            start = time.monotonic()
            last_activity = start
            buf = b""
            while True:
                if channel.exit_status_ready() and not channel.recv_ready():
                    break
                now = time.monotonic()
                if now - last_activity > idle_timeout or now - start > max_runtime:
                    # No output for too long (likely a prompt) or past the ceiling.
                    result["stalled"] = "idle" if now - last_activity > idle_timeout else "max_runtime"
                    result["last_output"] = tail[-1024:].decode(errors="replace")
                    try:
                        channel.close()
                    except Exception:
                        pass
                    return
                try:
                    data = channel.recv(4096)
                    if data:
                        last_activity = time.monotonic()
                        tail = (tail + data)[-2048:]
                        buf += data
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            loop.call_soon_threadsafe(queue.put_nowait, line.decode(errors="replace"))
                except Exception:
                    pass
            if buf:
                loop.call_soon_threadsafe(queue.put_nowait, buf.decode(errors="replace"))
            # Capture the script's exit status so the caller can tell success
            # from failure (e.g. a command-not-found mid-script exits non-zero).
            result["exit_code"] = channel.recv_exit_status()
        except Exception as exc:
            result["error"] = str(exc)
            loop.call_soon_threadsafe(queue.put_nowait, f"ERROR: {exc}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    _executor.submit(_stream)

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item

    if result["stalled"]:
        raise CommandStalled(str(result["last_output"]), reason=str(result["stalled"]))
    if result["error"]:
        # The stream aborted before a clean exit (connection reset, host-key change,
        # etc.) — that's a failure, not a successful run. The error line is already in
        # the streamed output, so the caller can extract a reason from it.
        raise CommandError(-1)
    code = result["exit_code"]
    if code is not None and code != 0:
        raise CommandError(int(code))


async def close(server_id: str) -> None:
    """Close and remove a pooled SSH client."""
    client = _pool.pop(server_id, None)
    if client:
        try:
            client.close()
        except Exception:
            pass


async def open_shell(
    server_id: str,
    host: str,
    port: int,
    username: str,
    auth_type: str,
    encrypted_cred: str,
    cols: int = 80,
    rows: int = 24,
) -> paramiko.Channel:
    """Open an interactive PTY shell channel for terminal use."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _open() -> paramiko.Channel:
        client = _get_client(server_id, host, port, username, auth_type, credential)
        transport = client.get_transport()
        channel = transport.open_session()
        channel.get_pty(term="xterm-256color", width=cols, height=rows)
        channel.invoke_shell()
        return channel

    return await loop.run_in_executor(_executor, _open)
