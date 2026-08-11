"""A scan that could not look must not decide your websites are gone.

This is the same rule as the malware scan's verdict, applied where the consequence is worse.
`sync` marks a site it did not see `is_present=False`, and the 2 August uptime work then
PAUSES that site's monitoring. So a single scan on a non-root connection would mark every
live website "no longer found" and silence its checks.

Measured on the owner's real CyberPanel server (two production sites, both serving):

| Connected as        | Lines the probe returned |
|---------------------|--------------------------|
| root                | 6                        |
| ubuntu (before)     | **0**                    |
| ubuntu (after)      | 6 — identical to root    |
| no sudo at all      | 1 — the privilege line   |

**You may record what you saw. You may not conclude anything from what you did not.**
"""
import subprocess

import pytest

from app.services import privilege as pv
from app.services import site_service as ss


SENT = "___SM_SITE___"


# ── The probe ────────────────────────────────────────────────────────────────

def test_the_probe_reports_what_it_could_read():
    cmd = ss.build_discovery_command()
    assert "SA_PRIV" in cmd
    assert f'{SENT}|privilege|$SA_PRIV' in cmd


def test_the_privilege_is_decided_before_anything_uses_it():
    cmd = ss.build_discovery_command()
    assert cmd.index("SA_SUDO=") < cmd.index("$SA_SUDO nginx")


def test_every_config_source_escalates():
    """nginx, Apache, the OpenLiteSpeed vhosts and the CyberPanel CLI are all root-only on a
    panel box. One of them left un-escalated is one source of sites silently lost."""
    cmd = ss.build_discovery_command()
    for needle in ("$SA_SUDO nginx -T", "$SA_SUDO $a -S",
                   "$SA_SUDO test -d /usr/local/lsws/conf/vhosts",
                   "$SA_SUDO test -x /usr/bin/cyberpanel",
                   "$SA_SUDO /usr/bin/cyberpanel listWebsitesJson"):
        assert needle in cmd, f"not escalated: {needle}"


def test_a_glob_expands_inside_the_escalated_shell(tmp_path):
    """The bug this test exists for, found by running the probe on a real server.

    `$SA_SUDO ls -d /path/*/` expands the glob as the UNPRIVILEGED user first. On a directory
    it cannot read, the pattern matches nothing, so `ls` receives the literal string and
    fails — and a live OpenLiteSpeed server reported no sites while sudo was working
    perfectly. Both real websites were lost from that source.

    Modelled here with `set -f`, which turns expansion off in the OUTER shell exactly as an
    unreadable directory does, and leaves it on in the inner one. That is the whole
    difference between the two forms.
    """
    vhosts = tmp_path / "vhosts"
    (vhosts / "shop.example.com").mkdir(parents=True)

    def run(script):
        return subprocess.run(["bash", "-c", script], capture_output=True, text=True).stdout

    naive = run(f"set -f; ls -d {vhosts}/*/ 2>/dev/null")
    fixed = run(f"""set -f; sh -c 'ls -d {vhosts}/*/' 2>/dev/null""")

    assert "shop.example.com" not in naive, "the naive form should fail — that was the bug"
    assert "shop.example.com" in fixed, "the fixed form must see it"

    assert "$SA_SUDO sh -c" in ss.build_discovery_command(), "the probe must use the fixed form"


def test_the_probe_is_valid_shell():
    """The prelude is multi-line. Flattening its newlines to '; ' produces `then;`, which is
    a syntax error — and the whole probe then returns nothing, which is exactly the failure
    this change removes."""
    r = subprocess.run(["bash", "-n"], input=ss.build_discovery_command(),
                       text=True, capture_output=True)
    assert r.returncode == 0, r.stderr


# ── Reading it back ──────────────────────────────────────────────────────────

def test_the_privilege_line_is_not_a_website():
    sites, _ = ss.parse_discovery(
        f"{SENT}|privilege|sudo||no\n{SENT}|nginx|shop.example.com|/var/www/shop|yes")
    kept = [s for s in sites if s.source != "privilege"]
    assert [s.domain for s in kept] == ["shop.example.com"]


# ── The guard ────────────────────────────────────────────────────────────────

def test_sync_will_not_run_without_being_told_whether_it_could_see_everything():
    """No default, on purpose. Forgetting is a TypeError at the call — loud — rather than a
    silent wrong answer. The same reason `ssh_service._get_client` made its fingerprint
    keyword-only with no default after three callers quietly skipped verification."""
    import inspect

    sig = inspect.signature(ss.sync)
    param = sig.parameters["complete"]
    assert param.kind is inspect.Parameter.KEYWORD_ONLY
    assert param.default is inspect.Parameter.empty, "complete must have no default"


def test_every_caller_says_which_it_is():
    import inspect

    from app.routers import sites as router

    for src in (inspect.getsource(router.scan_server),
                inspect.getsource(ss._look_where_an_install_just_finished)):
        assert "complete=" in src, "a caller that omits it would crash, but say so explicitly"


# ── The consequence, against the real database ───────────────────────────────

import uuid as _uuid

from app.database import AsyncSessionLocal, engine
from app.models import escalation as _escalation  # noqa: F401 — servers FK needs its table
from app.models.server import Server
from app.models.site import Site
from app.models.user import User
from app.services import crypto_service


@pytest.fixture(autouse=True)
async def _fresh_pool():
    yield
    await engine.dispose()


async def _server_with_two_live_sites(db):
    tag = _uuid.uuid4().hex[:8]
    user = User(email=f"disc-{tag}@example.com", password_hash="x", is_verified=True)
    db.add(user)
    await db.flush()
    server = Server(user_id=user.id, name=f"srv-{tag}", host="10.0.0.5", port=22,
                    username="ubuntu", auth_type="key", connection_type="ssh",
                    encrypted_cred=crypto_service.encrypt("k"))
    db.add(server)
    await db.flush()
    for name in ("a", "b"):
        db.add(Site(user_id=user.id, server_id=server.id,
                    domain=f"{name}-{tag}.example.com", aliases=[],
                    doc_root=f"/home/{name}/public_html", source="openlitespeed",
                    app_type="wordpress", has_ssl=True, is_present=True, status="live"))
    await db.flush()
    return server


@pytest.mark.asyncio
async def test_a_blind_scan_does_not_mark_live_sites_gone():
    """The bug, stated as a test.

    On the owner's real CyberPanel server the probe returned ZERO lines as a non-root user
    while two production websites were serving. Without this guard, one scan marks both
    "no longer found" — and `settle_uptime_checks` then pauses their monitoring.
    """
    async with AsyncSessionLocal() as db:
        server = await _server_with_two_live_sites(db)
        await db.commit()

        summary = await ss.sync(db, server, [], complete=False)

        rows = (await db.execute(
            __import__("sqlalchemy").select(Site).where(Site.server_id == server.id)
        )).scalars().all()

    assert summary["gone"] == 0
    assert summary["complete"] is False, "the caller must be able to see it was partial"
    assert all(r.is_present for r in rows), "a blind scan may conclude nothing"


@pytest.mark.asyncio
async def test_a_complete_scan_still_marks_a_removed_site_gone():
    """The guard must not break the real job. A site genuinely deleted from a server it could
    fully read is still recorded as gone — otherwise stale rows accumulate for ever."""
    async with AsyncSessionLocal() as db:
        server = await _server_with_two_live_sites(db)
        await db.commit()

        summary = await ss.sync(db, server, [], complete=True)

        rows = (await db.execute(
            __import__("sqlalchemy").select(Site).where(Site.server_id == server.id)
        )).scalars().all()

    assert summary["gone"] == 2
    assert not any(r.is_present for r in rows)


@pytest.mark.asyncio
async def test_a_blind_scan_still_records_what_it_did_see():
    """Refusing outright would make a partially-readable server unusable. New information is
    always welcome; only conclusions from absence are not."""
    async with AsyncSessionLocal() as db:
        server = await _server_with_two_live_sites(db)
        await db.commit()

        found = [ss.DiscoveredSite(domain="new.example.com", source="nginx",
                                   doc_root="/var/www/new", has_ssl=False,
                                   app_type="php", app_version=None)]
        summary = await ss.sync(db, server, found, complete=False)

    assert summary["added"] == 1
    assert summary["gone"] == 0
