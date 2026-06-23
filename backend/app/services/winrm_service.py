"""WinRM service — pywinrm-based connection management for Windows Server.

Mirrors the public surface of ``ssh_service`` (test_connection / execute /
execute_stream / close) so ``connection_manager`` can route by connection type.
pywinrm is synchronous, so every call runs in a thread pool to keep the async
event loop free.

Transport defaults to NTLM (works for local and domain accounts). Port 5986 is
treated as HTTPS (with certificate validation disabled, common for self-signed
WinRM listeners); any other port uses HTTP (default 5985).
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from concurrent.futures import ThreadPoolExecutor

import winrm

from app.services.crypto_service import decrypt
from app.services.ssh_service import CommandError

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=20, thread_name_prefix="winrm")

# Cached pywinrm sessions: {server_id_str: winrm.Session}
_sessions: dict[str, "winrm.Session"] = {}

DEFAULT_HTTP_PORT = 5985
DEFAULT_HTTPS_PORT = 5986


# ── Helpers ───────────────────────────────────────────────────────────────────

def _endpoint(host: str, port: int) -> str:
    scheme = "https" if port == DEFAULT_HTTPS_PORT else "http"
    return f"{scheme}://{host}:{port}/wsman"


def _make_session(host: str, port: int, username: str, credential: str) -> "winrm.Session":
    return winrm.Session(
        _endpoint(host, port),
        auth=(username, credential),
        transport="ntlm",
        server_cert_validation="ignore",
        read_timeout_sec=70,
        operation_timeout_sec=60,
    )


def _get_session(server_id: str, host: str, port: int, username: str, credential: str) -> "winrm.Session":
    session = _sessions.get(server_id)
    if session is None:
        session = _make_session(host, port, username, credential)
        _sessions[server_id] = session
    return session


def _decode(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value or ""


def _clean_ps_error(err: str) -> str:
    """PowerShell errors arrive as CLIXML; strip the wrapper for readability."""
    err = err.strip()
    if err.startswith("#< CLIXML"):
        # Best-effort: drop the CLIXML preamble line.
        parts = err.split("\n", 1)
        err = parts[1] if len(parts) > 1 else err
    return err


# ── Public API (mirrors ssh_service) ────────────────────────────────────────

async def test_connection(
    server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str
) -> dict:
    """Test WinRM connectivity. Returns {'ok', 'latency_ms', 'error'}."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _test() -> dict:
        t0 = time.monotonic()
        try:
            session = _get_session(server_id, host, port, username, credential)
            result = session.run_ps("Write-Output ok")
            latency_ms = int((time.monotonic() - t0) * 1000)
            if result.status_code == 0:
                return {"ok": True, "latency_ms": latency_ms, "error": None}
            return {
                "ok": False,
                "latency_ms": latency_ms,
                "error": _clean_ps_error(_decode(result.std_err))[:300] or "non-zero exit",
            }
        except Exception as exc:  # noqa: BLE001
            _sessions.pop(server_id, None)  # drop a possibly-broken session
            return {"ok": False, "latency_ms": 0, "error": str(exc)}

    return await loop.run_in_executor(_executor, _test)


async def execute(
    server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str
) -> tuple[str, str, int]:
    """Run a PowerShell command, return (stdout, stderr, exit_code)."""
    credential = decrypt(encrypted_cred)
    loop = asyncio.get_event_loop()

    def _run() -> tuple[str, str, int]:
        try:
            session = _get_session(server_id, host, port, username, credential)
            result = session.run_ps(command)
            return _decode(result.std_out), _clean_ps_error(_decode(result.std_err)), int(result.status_code)
        except Exception as exc:  # noqa: BLE001
            _sessions.pop(server_id, None)
            return "", f"WinRM error: {exc}", 1

    return await loop.run_in_executor(_executor, _run)


async def execute_stream(
    server_id: str, host: str, port: int, username: str, auth_type: str, encrypted_cred: str, command: str
) -> AsyncIterator[str]:
    """Run a PowerShell command and yield output lines.

    WinRM is request/response, so unlike SSH this is not incremental — the
    command completes, then its output lines are yielded. The async-iterator
    contract matches ssh_service so callers are unchanged.
    """
    out, err, code = await execute(
        server_id, host, port, username, auth_type, encrypted_cred, command
    )
    for line in out.splitlines():
        yield line
    if err.strip():
        for line in err.splitlines():
            yield line
    # Surface a non-zero exit as a failure (parity with ssh_service).
    if code != 0:
        raise CommandError(code)


async def close(server_id: str) -> None:
    """Drop the cached session for a server (WinRM has no persistent socket)."""
    _sessions.pop(server_id, None)
