"""Turning HTTPS on for a site over MCP.

The tool used to be panel-only: on an ordinary Linux server — the common case — it said
HTTPS was "not available through MCP yet". The reason was honest, and it was the right
reason: the policy (which names go on the certificate, and the refusals that must happen
before anything is requested) lived inside the app's own endpoint, and a second copy is how
one of them stops excluding a stale alias. So the policy moved into `ssl_service` and both
callers use it.

The tests that matter are the refusals, because a failed attempt is not free: Let's Encrypt
allows five certificates per domain per week and a doomed request spends one. An AI that
retries is exactly the caller that can burn them.
"""
from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

import pytest

from app.mcp import server as m
from app.services import ssl_service


class _Session:
    async def __aenter__(self): return self
    async def __aexit__(self, *e): return False


def _ok(value):
    async def _f(*a, **k): return value
    return _f


SITE = SimpleNamespace(id="site1", domain="shop.example.com",
                       aliases=["www.shop.example.com", "gone.example.com"],
                       doc_root="/var/www/shop.example.com")


def _wire(monkeypatch, *, panel=None, connection="ssh", site=SITE):
    srv = SimpleNamespace(id="s1", name="Box", connection_type=connection,
                          panel_type=panel, host="203.0.113.10")

    class _Res:
        def scalars(self): return self
        def first(self): return site

    class _S(_Session):
        async def execute(self, *a, **k): return _Res()

    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _S())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1", email="a@b.com")))
    monkeypatch.setattr(m, "_executor", _ok((SimpleNamespace(server=srv, can_execute=True), None)))
    monkeypatch.setattr(m, "_audit", _ok(None))
    return srv


def _dns(monkeypatch, ready):
    """Only `ready` names resolve to the server."""
    async def check_names(names, host):
        return {"ready": [n for n in names if n in ready],
                "not_ready": [{"name": n, "why": "This domain does not point at this server."}
                              for n in names if n not in ready]}
    monkeypatch.setattr(ssl_service, "check_names", check_names)


def _started(monkeypatch):
    seen: dict = {}

    async def start(db, *, site, server, user, plan):
        seen.update(domain=site.domain, covers=plan["covers"])
        return "run-123"

    monkeypatch.setattr(ssl_service, "start_issue", start)
    return seen


# ── the ordinary server: the case that used to be refused outright ───────────

def test_an_ordinary_linux_server_can_now_turn_https_on(monkeypatch):
    _wire(monkeypatch)
    _dns(monkeypatch, {"shop.example.com", "www.shop.example.com"})
    seen = _started(monkeypatch)

    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))

    assert "not available through MCP" not in out
    assert "panel" not in out.lower()
    assert seen["covers"] == ["shop.example.com", "www.shop.example.com"]
    assert "run-123" in out


def test_the_certificate_covers_www_not_only_the_bare_domain(monkeypatch):
    """A certificate missing `www` hands half the visitors a browser warning on a site whose
    owner has just been told HTTPS is on."""
    _wire(monkeypatch)
    _dns(monkeypatch, {"shop.example.com", "www.shop.example.com"})
    seen = _started(monkeypatch)

    asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))
    assert "www.shop.example.com" in seen["covers"]


def test_a_stale_alias_is_left_out_and_SAID(monkeypatch):
    """Let's Encrypt fails the whole request if one name cannot be reached, so an alias from
    a domain the customer stopped using would otherwise block HTTPS entirely. Excluding it
    silently is the other failure: the owner believes it is covered."""
    _wire(monkeypatch)
    _dns(monkeypatch, {"shop.example.com", "www.shop.example.com"})
    _started(monkeypatch)

    out = asyncio.run(m.serverally_issue_ssl(
        server="Box", domain="shop.example.com", response_format=m.ResponseFormat.JSON))
    data = json.loads(out)

    assert data["covers"] == ["shop.example.com", "www.shop.example.com"]
    assert [e["name"] for e in data["excluded"]] == ["gone.example.com"]
    assert data["excluded"][0]["why"], "an excluded name must say why"


def test_the_sites_own_domain_not_pointing_here_requests_nothing(monkeypatch):
    """It names the certificate, so it cannot be skipped — and the refusal has to happen
    before anything is asked for, because a failed attempt spends one of five a week."""
    _wire(monkeypatch)
    _dns(monkeypatch, {"www.shop.example.com"})
    seen = _started(monkeypatch)

    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))

    assert not seen, "nothing may be requested when it cannot succeed"
    assert "not requested" in out


def test_a_refusal_names_the_innocent_cause(monkeypatch):
    """Behind Cloudflare the domain resolves to the CDN, so our check says "points somewhere
    else" about a setup that is completely fine. Saying only that sends somebody off to
    break a working site."""
    _wire(monkeypatch)
    _dns(monkeypatch, set())
    _started(monkeypatch)

    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))
    assert "Cloudflare" in out and "force=true" in out


def test_force_skips_the_check_and_asks_for_every_name(monkeypatch):
    _wire(monkeypatch)
    _dns(monkeypatch, set())          # nothing resolves here at all
    seen = _started(monkeypatch)

    out = asyncio.run(m.serverally_issue_ssl(
        server="Box", domain="shop.example.com", force=True))

    assert seen["covers"] == ["shop.example.com", "www.shop.example.com", "gone.example.com"]
    assert "run-123" in out


def test_forcing_twice_does_not_re_suggest_forcing(monkeypatch):
    """The nudge is for somebody who has not tried it. Repeating it to a caller who already
    forced is how an AI loops."""
    _wire(monkeypatch)
    _started(monkeypatch)

    async def boom(**k): raise ssl_service.SslError("that name is not a domain")
    monkeypatch.setattr(ssl_service, "plan_issue", boom)

    out = asyncio.run(m.serverally_issue_ssl(
        server="Box", domain="shop.example.com", force=True))
    assert "force=true" not in out


# ── the boundaries ───────────────────────────────────────────────────────────

def test_a_panel_server_still_goes_through_its_panel(monkeypatch):
    """A panel issues and renews its own certificates on its own schedule, so one we install
    behind its back is reverted later, at a moment nobody can connect to what we did."""
    _wire(monkeypatch, panel="cyberpanel")
    called = {}

    async def panel_issue(srv, d):
        called["d"] = d
        return {"ok": True}

    monkeypatch.setattr(m.hosting_service, "issue_ssl", panel_issue)
    async def never(*a, **k):
        pytest.fail("the certbot path must not run on a panel server")

    monkeypatch.setattr(ssl_service, "start_issue", never)

    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))
    assert called["d"] == "shop.example.com"
    assert "cyberpanel" in out


def test_a_site_we_do_not_know_is_named_rather_than_guessed(monkeypatch):
    _wire(monkeypatch, site=None)
    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="nope.example.com"))
    assert "no website called 'nope.example.com'" in out


def test_a_windows_server_is_told_plainly(monkeypatch):
    _wire(monkeypatch, connection="winrm")
    out = asyncio.run(m.serverally_issue_ssl(server="WinBox", domain="shop.example.com"))
    assert "SSH" in out and "winrm" in out


def test_turning_https_on_needs_permission_to_change_things(monkeypatch):
    monkeypatch.setattr(m, "AsyncSessionLocal", lambda: _Session())
    monkeypatch.setattr(m, "_resolve_caller", _ok(SimpleNamespace(id="u1")))
    monkeypatch.setattr(m, "_executor", _ok((None, "This connection is read-only.")))

    out = asyncio.run(m.serverally_issue_ssl(server="Box", domain="shop.example.com"))
    assert out == "This connection is read-only."


def test_the_app_and_the_tool_share_one_rule():
    """Two copies of "which names, and which refusals" is how one of them stops excluding a
    stale alias. Both must go through ssl_service."""
    import inspect

    from app.routers import sites as sites_router

    for fn in (sites_router.turn_on_ssl, m.serverally_issue_ssl):
        body = inspect.getsource(fn)
        code = "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))
        assert "ssl_service.plan_issue" in code and "ssl_service.start_issue" in code
        assert "check_names(" not in code, f"{fn.__name__} decides names itself"
        assert "certbot_domain_flags" not in code
