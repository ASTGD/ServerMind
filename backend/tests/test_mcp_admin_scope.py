"""Full-power ("mcp:admin") scope + the run_command shell tool (docs/MCP-SERVER-PLAN.md §3
Decisions Log 2026-07-24).

run_command deliberately crosses the "no shell over MCP" line at the user's explicit opt-in.
These lock the contract around it: the 3-tier scope mapping, that admin is advertised so a
client can request it, that the tool is registered as a NON-read-only destructive tool, and
that the consent page actually offers the "Full power" choice. The runtime gate (needs
mcp:admin + execute) and the blocklist floor are verified live, like the other write tools.
"""
from __future__ import annotations

import asyncio

from app.mcp.oauth_provider import (
    ALL_SCOPES,
    DEFAULT_SCOPES,
    SCOPE_ADMIN,
    SCOPE_READ,
    SCOPE_WRITE,
    scopes_for_access_level,
)
from app.mcp.server import mcp_server
from app.routers.mcp_oauth import _page


def test_scope_tiers_are_additive():
    """Each consent tier grants the ones below it; unknown/blank falls back to read-only."""
    assert scopes_for_access_level("read") == [SCOPE_READ]
    assert scopes_for_access_level("full") == [SCOPE_READ, SCOPE_WRITE]
    assert scopes_for_access_level("admin") == [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
    # Anything unexpected must NOT silently grant more than read-only.
    assert scopes_for_access_level("") == [SCOPE_READ]
    assert scopes_for_access_level("root") == [SCOPE_READ]
    assert scopes_for_access_level("write") == [SCOPE_READ]


def test_admin_scope_is_advertised_but_not_the_default():
    """DCR valid_scopes + metadata must include mcp:admin (a client can request it), but the
    safe first-connection default stays read-only."""
    assert SCOPE_ADMIN in ALL_SCOPES
    assert ALL_SCOPES == [SCOPE_READ, SCOPE_WRITE, SCOPE_ADMIN]
    assert DEFAULT_SCOPES == [SCOPE_READ]


def test_run_command_registered_as_destructive_not_read_only():
    tools = {t.name: t for t in asyncio.run(mcp_server.list_tools())}
    assert "serverally_run_command" in tools, "run_command must be registered"
    ann = tools["serverally_run_command"].annotations
    # It runs arbitrary commands — must never be mislabeled read-only, and is destructive.
    assert ann.readOnlyHint is False
    assert ann.destructiveHint is True


def test_consent_page_offers_all_three_access_levels():
    html = _page(client_name="Claude", txn="tok")
    # Read-only + Full access existed; Full power (admin) is the new third radio.
    assert 'value="read"' in html
    assert 'value="full"' in html
    assert 'value="admin"' in html
    assert "Full power" in html
    # The powerful option is honestly labeled (it runs any command).
    assert "any command" in html.lower()
