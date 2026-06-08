"""SSH service — Paramiko-based connection management for Linux/Unix servers."""
from __future__ import annotations

import asyncio
import io
import logging
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import paramiko

from app.services.crypto_service import decrypt

logger = logging.getLogger(__name__)

# Thread pool for blocking Paramiko I/O
_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="ssh")

# In-memory SSH client pool: {server_id_str: paramiko.SSHClient}
_pool: dict[str, paramiko.SSHClient] = {}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_client(host: str, port: int, username: str, auth_type: str, credential: str) -> paramiko.SSHClient:
    """Open and return an authenticated SSHClient (blocking)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    if auth_type == "password":
        client.connect(host, port=port, username=username, password=credential, timeout=15, banner_timeout=15)
    else:
        # auth_type == "key" — credential is the PEM private key string
        key_file = io.StringIO(credential)
        pkey = None
        for key_class in (paramiko.RSAKey, paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.DSSKey):
            try:
                key_file.seek(0)
                pkey = key_class.from_private_key(key_file)
                break
            except Exception:
                continue
        if pkey is None:
            raise ValueError("Unrecognised private key format")
        client.connect(host, port=port, username=username, pkey=pkey, timeout=15, banner_timeout=15)

    return client


def _get_client(server_id: str, host: str, port: int, username: str, auth_type: str, credential: str) -> paramiko.SSHClient:
    """Return a pooled client, reconnecting if the transport is dead."""
    existing = _pool.get(server_id)
    if existing and existing.get_transport() and existing.get_transport().is_active():
        return existing
    client = _make_client(host, port, username, auth_type, credential)
    _pool[server_id] = client
    return client


# ── Public API ────────────────────────────────────────────────────────────────

async def test_connection(server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str) -> dict:
    """Test SSH connectivity. Returns {'ok': bool, 'latency_ms': int, 'error': str|None}."""
    import time

    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _test() -> dict:
        t0 = time.monotonic()
        try:
            client = _get_client(server_id, host, port, username, auth_type, credential)
            _, stdout, _ = client.exec_command("echo ok", timeout=10)
            stdout.read()
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "error": None}
        except Exception as exc:
            return {"ok": False, "latency_ms": 0, "error": str(exc)}

    return await loop.run_in_executor(_executor, _test)


async def execute(server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str) -> tuple[str, str, int]:
    """Execute a command and return (stdout, stderr, exit_code)."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _run() -> tuple[str, str, int]:
        client = _get_client(server_id, host, port, username, auth_type, credential)
        _, stdout, stderr = client.exec_command(command, timeout=60)
        out = stdout.read().decode(errors="replace")
        err = stderr.read().decode(errors="replace")
        code = stdout.channel.recv_exit_status()
        return out, err, code

    return await loop.run_in_executor(_executor, _run)


async def execute_stream(server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str) -> AsyncIterator[str]:
    """Execute a command and yield stdout/stderr lines as they arrive."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()
    queue: asyncio.Queue[str | None] = asyncio.Queue()

    def _stream() -> None:
        try:
            client = _get_client(server_id, host, port, username, auth_type, credential)
            transport = client.get_transport()
            channel = transport.open_session()
            channel.exec_command(command)
            channel.settimeout(0.5)

            buf = b""
            while True:
                if channel.exit_status_ready() and not channel.recv_ready():
                    break
                try:
                    data = channel.recv(4096)
                    if data:
                        buf += data
                        while b"\n" in buf:
                            line, buf = buf.split(b"\n", 1)
                            loop.call_soon_threadsafe(queue.put_nowait, line.decode(errors="replace"))
                except Exception:
                    pass
            if buf:
                loop.call_soon_threadsafe(queue.put_nowait, buf.decode(errors="replace"))
        except Exception as exc:
            loop.call_soon_threadsafe(queue.put_nowait, f"ERROR: {exc}")
        finally:
            loop.call_soon_threadsafe(queue.put_nowait, None)

    _executor.submit(_stream)

    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


async def close(server_id: str) -> None:
    """Close and remove a pooled SSH client."""
    client = _pool.pop(server_id, None)
    if client:
        try:
            client.close()
        except Exception:
            pass
