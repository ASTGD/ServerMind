"""MCP activity feed — friendly labels + credential-free serialization
(docs/MCP-SERVER-PLAN.md). The label heuristics turn a raw command into a readable action
("Installing docker.io") and the serializer must never emit anything but the redacted,
feed-shaped fields. The record layer (start/finish/record_done) is exercised live.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.models.mcp_activity import McpActivity
from app.services.mcp_activity_service import friendly_label, serialize


def test_friendly_label_command_heuristics():
    assert friendly_label("run_command", "apt-get install -y docker.io") == "Installing docker.io"
    assert friendly_label("run_command", "apt install nginx") == "Installing nginx"
    assert friendly_label("run_command", "dnf install -y httpd") == "Installing httpd"
    assert friendly_label("run_command", "apt remove --purge apache2") == "Removing apache2"
    assert friendly_label("run_command", "systemctl restart nginx") == "Restarting nginx"
    assert friendly_label("run_command", "systemctl stop horizon") == "Stopping horizon"
    assert friendly_label("run_command", "service mysql start") == "Starting mysql"
    assert friendly_label("run_command", "docker ps") == "Docker ps"
    assert friendly_label("run_command", "docker compose up -d") == "Docker Compose"
    # Fallback: unknown command echoes a truncated form, never crashes.
    assert friendly_label("run_command", "df -h").startswith("Ran: df -h")
    # An empty command never reaches the parser → the tool's own label.
    assert friendly_label("run_command", "") == "Command"


def test_friendly_label_tool_names():
    assert friendly_label("run_security_scan") == "Security scan"
    assert friendly_label("run_threat_scan") == "Threat scan"
    assert friendly_label("create_site") == "Create website"
    assert friendly_label("create_database") == "Create database"
    # Unknown tool degrades to a title-cased name, never raises.
    assert friendly_label("some_new_tool") == "Some New Tool"


def test_serialize_is_feed_shaped_and_credential_free():
    row = McpActivity(
        id=uuid.uuid4(), user_id=uuid.uuid4(), client_id="cid", client_name="Claude",
        tool="run_command", server_id=uuid.uuid4(), server_name="vev.astgd.com",
        status="ok", label="Installing docker.io", command="apt-get install -y docker.io",
        exit_code=0, detail="exit 0",
        started_at=datetime.now(timezone.utc), finished_at=datetime.now(timezone.utc),
    )
    out = serialize(row)
    # Exactly the feed fields — no user_id, no client_id, no server_id (internal ids).
    assert set(out) == {
        "id", "client_name", "tool", "server_name", "status", "label",
        "command", "exit_code", "detail", "started_at", "finished_at",
    }
    assert out["client_name"] == "Claude"
    assert out["status"] == "ok"
    assert out["label"] == "Installing docker.io"
    assert "user_id" not in out and "client_id" not in out and "server_id" not in out


def test_serialize_unknown_client_falls_back():
    row = McpActivity(
        id=uuid.uuid4(), user_id=uuid.uuid4(), client_id=None, client_name=None,
        tool="run_command", status="running", label="Ran: uptime",
        started_at=datetime.now(timezone.utc),
    )
    out = serialize(row)
    assert out["client_name"] == "An app"
    assert out["status"] == "running"
    assert out["finished_at"] is None
