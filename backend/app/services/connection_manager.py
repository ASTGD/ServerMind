"""Connection manager — single entry point for all server communication.

Routes to the correct service based on server.connection_type:
  'ssh'     → ssh_service.py  (Linux/Unix/BSD via Paramiko)
  'winrm'   → winrm_service.py (Windows Server via pywinrm) — Phase 2B
  'hosting' → hosting_service.py (cPanel/CyberPanel/Plesk API) — Phase 7
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass

from app.models.server import Server
from app.services import ssh_service, winrm_service

logger = logging.getLogger(__name__)


@dataclass
class ConnectionResult:
    ok: bool
    latency_ms: int
    error: str | None = None


async def test_connection(server: Server) -> ConnectionResult:
    """Test connectivity to the server."""
    if server.connection_type == "ssh":
        result = await ssh_service.test_connection(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
        )
        return ConnectionResult(**result)

    if server.connection_type == "winrm":
        result = await winrm_service.test_connection(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
        )
        return ConnectionResult(**result)

    if server.connection_type == "hosting":
        from app.services import hosting_service
        result = await hosting_service.test_connection(server)
        return ConnectionResult(**result)

    raise NotImplementedError(f"connection_type '{server.connection_type}' not yet supported")


async def execute(server: Server, command: str) -> tuple[str, str, int]:
    """Execute command, return (stdout, stderr, exit_code)."""
    if server.connection_type == "ssh":
        return await ssh_service.execute(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            command,
        )
    if server.connection_type == "winrm":
        return await winrm_service.execute(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            command,
        )
    raise NotImplementedError(f"connection_type '{server.connection_type}' not yet supported")


async def execute_stream(server: Server, command: str) -> AsyncIterator[str]:
    """Execute command and stream output lines."""
    if server.connection_type == "ssh":
        return ssh_service.execute_stream(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            command,
        )
    if server.connection_type == "winrm":
        return winrm_service.execute_stream(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            command,
        )
    raise NotImplementedError(f"connection_type '{server.connection_type}' not yet supported")


async def close(server: Server) -> None:
    """Close and release the connection to the server."""
    if server.connection_type == "ssh":
        await ssh_service.close(str(server.id))
    elif server.connection_type == "winrm":
        await winrm_service.close(str(server.id))
