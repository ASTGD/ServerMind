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
from app.services import ssh_service, ssm_service, winrm_service

logger = logging.getLogger(__name__)


@dataclass
class ConnectionResult:
    ok: bool
    latency_ms: int
    error: str | None = None
    fingerprint: str | None = None   # the server's current host-key fingerprint (ssh)
    host_key_changed: bool = False   # True when it differs from the pinned one (Risk 3)


async def test_connection(server: Server) -> ConnectionResult:
    """Test connectivity to the server."""
    if server.connection_type == "ssh":
        result = await ssh_service.test_connection(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            expected_fingerprint=server.fingerprint,
        )
        return ConnectionResult(**result)

    if server.connection_type == "ssm":
        # AWS Systems Manager: no address, no port, no host key — the agent dials out and
        # identity is IAM rather than a fingerprint we pin.
        return ConnectionResult(**await ssm_service.test_connection(
            server, await ssm_service.account_for(server)))

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

    if server.connection_type == "rdp":
        # RDP has no command channel — "connected" means the Remote Desktop port is
        # reachable (the guacd viewer streams the pixels from there).
        from app.services import rdp_service
        result = await rdp_service.test_connection(server.host, server.port)
        return ConnectionResult(**result)

    raise NotImplementedError(f"connection_type '{server.connection_type}' not yet supported")


async def execute(server: Server, command: str,
                  read_timeout: int = 60) -> tuple[str, str, int]:
    """Execute command, return (stdout, stderr, exit_code).

    read_timeout is how long the command may produce NO output before the connection is
    treated as dead. SSH only — WinRM has no equivalent knob.
    """
    if server.connection_type == "ssh":
        return await ssh_service.execute(
            str(server.id), server.host, server.port,
            server.username, server.auth_type, server.encrypted_cred,
            command, expected_fingerprint=server.fingerprint, read_timeout=read_timeout,
        )

    if server.connection_type == "ssm":
        return await ssm_service.execute(
            server, await ssm_service.account_for(server), command,
            read_timeout=read_timeout)
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
            command, expected_fingerprint=server.fingerprint,
        )
    if server.connection_type == "ssm":
        return ssm_service.execute_stream(
            server, await ssm_service.account_for(server), command)
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
    # ssm holds nothing to close — every command is its own API call.
