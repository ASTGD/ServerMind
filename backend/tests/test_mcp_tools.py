"""MCP tool guarantees (docs/MCP-SERVER-PLAN.md §3, §10).

The one that matters: **no tool may ever return a credential.** These assert it against
the actual serialised payload of the credential-free serialisers — not the code's shape —
mirroring ``test_user_detail_never_exposes_a_credential``. Rule-7 isolation (a token holder
sees only their own servers) is proven end-to-end in the live OAuth validation; here we lock
the pure, deterministic guarantees that back it.
"""
from __future__ import annotations

import asyncio
import json
import uuid

from app.mcp.server import (
    _looks_binary,
    _mission_summary,
    _scan_finding_public,
    _server_public,
    _step_public,
    mcp_server,
)
from app.models.server import Server

# Sentinels that must NEVER appear in any tool payload.
_SECRET_CRED = "AES256GCM::c2VjcmV0LWNyZWQtZG8tbm90LWxlYWs="
_SECRET_FP = "SHA256:do-not-leak-this-host-fingerprint"

# The read tools this phase ships — locked as read-only so a write can't sneak in as one.
_READ_TOOLS = {
    "serverally_list_servers", "serverally_get_server", "serverally_get_metrics",
    "serverally_get_fleet_health", "serverally_get_security_scan", "serverally_get_threat_scan",
    "serverally_list_playbooks", "serverally_list_missions", "serverally_get_mission",
    "serverally_list_sites", "serverally_list_files", "serverally_read_file",
    "serverally_get_playbook_run", "serverally_list_backups",
}

# Phase 3 writes — NOT read-only; run_playbook additionally changes the server.
_WRITE_TOOLS = {
    "serverally_run_security_scan", "serverally_run_threat_scan", "serverally_run_playbook",
    "serverally_run_backup", "serverally_create_site", "serverally_issue_ssl",
    "serverally_create_database",
}


def _server(**over) -> Server:
    s = Server()
    s.id = uuid.uuid4()
    s.user_id = uuid.uuid4()
    s.name, s.host, s.port, s.username = "Prod-1", "10.0.0.1", 22, "root"
    s.auth_type, s.connection_type, s.panel_type = "password", "ssh", None
    s.category, s.os_type, s.os_version, s.arch, s.shell = "vps", "ubuntu", "22.04", "x86_64", "bash"
    s.status, s.tags, s.notes = "online", ["prod"], "note"
    s.last_seen = s.created_at = None
    # The secrets that must never escape:
    s.encrypted_cred = _SECRET_CRED
    s.fingerprint = _SECRET_FP
    for k, v in over.items():
        setattr(s, k, v)
    return s


def test_server_public_never_leaks_credentials():
    """A Server carrying a real-looking encrypted_cred + fingerprint serialises without
    either the keys or their values."""
    payload = _server_public(_server())
    blob = json.dumps(payload)
    assert "encrypted_cred" not in payload
    assert "fingerprint" not in payload
    assert _SECRET_CRED not in blob
    assert _SECRET_FP not in blob
    # ...but the useful, non-secret fields ARE present.
    assert payload["name"] == "Prod-1"
    assert payload["host"] == "10.0.0.1"
    assert payload["os"] == "ubuntu 22.04"


def test_scan_finding_whitelist_drops_unknown_keys():
    """The scan-finding serialiser keeps known safe keys and drops anything else — so a
    future field (or a rogue key in the stored JSON) can't leak."""
    finding = {
        "severity": "high", "title": "SSH root login enabled", "detail": "PermitRootLogin yes",
        "fix": "Set PermitRootLogin no",
        # things that must be dropped:
        "password": "hunter2", "raw_config": {"nested": "object"}, "token": "sk-leak",
    }
    out = _scan_finding_public(finding)
    assert out == {"severity": "high", "title": "SSH root login enabled",
                   "detail": "PermitRootLogin yes", "fix": "Set PermitRootLogin no"}
    assert "password" not in out and "token" not in out and "raw_config" not in out


def test_mission_step_truncates_and_drops_nested():
    """A transcript step keeps scalars, truncates long strings (command output), and drops
    nested structures."""
    step = {
        "n": 3, "action": "run", "command": "df -h", "exit_code": 0,
        "output": "x" * 5000,               # long → truncated
        "nested": {"a": 1}, "list": [1, 2],  # dropped
    }
    out = _step_public(step)
    assert out["n"] == 3 and out["action"] == "run" and out["exit_code"] == 0
    assert len(out["output"]) < 5000 and "more chars" in out["output"]
    assert "nested" not in out and "list" not in out


def test_mission_summary_is_scalar_and_safe():
    """Mission summary carries only display scalars (no transcript/steps blob)."""
    class _M:
        id = uuid.uuid4()
        goal, status, verified = "Fix the site", "complete", True
        server_name, skill_slug, steps_used, summary = "Prod-1", "wordpress-rescue", 7, "Done."
        created_at = None
    out = _mission_summary(_M())
    assert out["goal"] == "Fix the site" and out["verified"] is True
    assert "steps" not in out and "transcript" not in out  # heavy/possibly-sensitive blobs excluded here


def test_looks_binary_detects_what_latin1_would_hide():
    """read_file's own binary guard — file_service's latin-1 fallback lets real binaries
    through (a live /bin/bash did), so the tool must catch NUL + control-heavy content."""
    assert _looks_binary("\x7fELF\x02\x01\x01\x00\x00\x00 binary")     # NUL present
    assert _looks_binary("".join(chr(b) for b in range(0, 32)) * 200)  # control-heavy
    assert not _looks_binary("NAME=\"Ubuntu\"\nVERSION=\"20.04\"\n")   # ordinary text
    assert not _looks_binary("")                                        # empty is not binary


def test_read_tools_are_read_only_and_writes_are_not():
    """Read tools declare readOnlyHint; write tools do NOT (and run_playbook is destructive)
    — so a client can trust the annotations, and no write tool masquerades as a read."""
    tools = {t.name: t for t in asyncio.run(mcp_server.list_tools())}
    assert _READ_TOOLS <= set(tools), f"missing read tools: {_READ_TOOLS - set(tools)}"
    assert _WRITE_TOOLS <= set(tools), f"missing write tools: {_WRITE_TOOLS - set(tools)}"
    for name in _READ_TOOLS:
        a = tools[name].annotations
        assert a and a.readOnlyHint is True and a.destructiveHint is False, f"{name} not read-only"
    for name in _WRITE_TOOLS:
        a = tools[name].annotations
        assert a and a.readOnlyHint is False, f"{name} wrongly marked read-only"
    assert tools["serverally_run_playbook"].annotations.destructiveHint is True
