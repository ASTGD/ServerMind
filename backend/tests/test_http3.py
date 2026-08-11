"""HTTP/3 for one site — Ploi's SSL → HTTP/3.

Three things decide whether this works, and each fails quietly rather than loudly.

**Most servers cannot do it at all** — nginx needs `--with-http_v3_module`, which arrived in
1.25, and Ubuntu 24.04 (what our own setup installs) ships 1.24. Proven in a container: on
24.04 the probe reports `quic=no`, and forcing it anyway makes nginx refuse with `invalid
parameter "quic"` while the file stays byte-identical and the site keeps serving.

**`reuseport` may appear only once per address:port in the WHOLE configuration.** Also proven
on real nginx 1.27: with one site holding it, a second one gets `duplicate listen options for
0.0.0.0:443` and nginx will not start — that is every site on the machine, not this one.

**The browser has to be told.** Without `Alt-Svc` the listener exists and nobody ever uses it.
The container run confirmed the header really reaches the response.
"""
import re
import subprocess

import pytest

from app.services import http3_service as h3


def probe(**over):
    facts = {"nginx": "yes", "version": "1.27.5", "quic": "yes", "reuseport": "free",
             "on": "no", "https": "yes", "udp": "shut"}
    facts.update(over)
    return h3.parse_probe("\n".join(f"{k}={v}" for k, v in facts.items()))


# ── Can this server do it ────────────────────────────────────────────────────

def test_an_nginx_built_with_it_can():
    p = probe()
    assert p["supported"] is True and p["why"] is None


def test_the_build_flags_decide_it_not_the_version_number():
    """A distribution can ship 1.26 without the module, and the version alone would promise
    something the binary cannot do."""
    p = probe(version="1.26.0", quic="no")
    assert p["supported"] is False
    assert "1.26.0" in p["why"] and "1.25" in p["why"]


def test_the_refusal_names_the_way_forward():
    """Verified in a container: Ubuntu 24.04 really does ship 1.24 without the module, so
    this is the answer most servers will get."""
    p = probe(version="1.24.0 (Ubuntu)", quic="no")
    assert "nginx.org" in p["why"]


def test_a_site_without_https_is_told_why_rather_than_offered_the_switch():
    """QUIC has no unencrypted mode at all."""
    p = probe(https="no")
    assert "HTTPS" in p["why"]


def test_no_nginx_at_all_is_its_own_answer():
    assert "nginx is not running" in probe(nginx="no")["why"]


# ── The reuseport rule ───────────────────────────────────────────────────────

def test_reuseport_is_free_when_nothing_else_has_claimed_it():
    assert probe(reuseport="free")["reuseport_free"] is True


def test_reuseport_taken_by_another_site_is_not_claimed_again():
    """Proven on real nginx: a second one produces `duplicate listen options for
    0.0.0.0:443` and nginx refuses to start — taking down every site on the machine."""
    assert probe(reuseport="taken", on="no")["reuseport_free"] is False


def test_this_site_holding_it_does_not_count_against_itself():
    """Otherwise turning it off and on again for the same site would drop the flag that has
    to be on exactly one listener."""
    assert probe(reuseport="taken", on="yes")["reuseport_free"] is True


# ── The block that gets written ──────────────────────────────────────────────

def _block(with_reuseport=True):
    cmd = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                 with_reuseport=with_reuseport)
    import base64
    arg = re.search(r'python3 - "\$CFG" (\S+) ', cmd).group(1)
    return base64.b64decode(arg.strip("'")).decode()


def test_the_browser_is_told_or_nobody_ever_uses_it():
    """A visitor arrives over HTTP/2 and only upgrades when the response advertises it.
    Without this the port is open, the listener is there, and the feature does nothing."""
    assert 'add_header Alt-Svc \'h3=":443"; ma=86400\' always;' in _block()


def test_always_is_on_the_header():
    """Without `always`, nginx adds it only on 2xx and 3xx — so a visitor whose first
    response is a redirect or an error never learns HTTP/3 exists."""
    assert "always;" in _block()


def test_reuseport_is_written_only_when_it_was_free():
    assert "quic reuseport;" in _block(True)
    assert "listen 443 quic;" in _block(False)
    assert "reuseport" not in _block(False)


def test_http3_is_switched_on_and_not_just_listened_for():
    """`listen … quic` opens the socket; `http3 on` is what makes nginx speak it."""
    assert "http3 on;" in _block()


# ── Run the edit ─────────────────────────────────────────────────────────────

HTTPS_CONF = """\
server {
    listen 80;
    server_name shop.test;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name shop.test;
    ssl_certificate /etc/ssl/x.pem;
    ssl_certificate_key /etc/ssl/x.key;
    root /var/www/shop;
}
"""


def _edit(tmp_path, text, *, on=True, with_reuseport=True):
    import base64

    cfg = tmp_path / "site.conf"
    cfg.write_text(text)
    script = h3._EDIT_ON if on else h3._EDIT_OFF
    args = ["python3", "-", str(cfg)]
    if on:
        args += [base64.b64encode(_block(with_reuseport).encode()).decode(), h3.MARK_START]
    proc = subprocess.run(args, input=script, capture_output=True, text=True)
    return proc.returncode, cfg.read_text(), proc.stdout + proc.stderr


def test_it_goes_into_the_block_that_already_serves_https(tmp_path):
    code, text, out = _edit(tmp_path, HTTPS_CONF)
    assert code == 0, out
    assert text.count("listen 443 quic reuseport;") == 1
    # …and into the HTTPS block, not the redirect one above it.
    https_half = text.split("listen 443 ssl;")[1]
    assert "quic" in https_half


def test_it_is_added_once_per_block_not_once_per_listen_line(tmp_path):
    """The certificate installer already made this mistake: an ordinary vhost has both
    `listen 443 ssl;` and `listen [::]:443 ssl;`, and inserting after each gives nginx a
    duplicate listener."""
    _code, text, _out = _edit(tmp_path, HTTPS_CONF)
    assert text.count(h3.MARK_START) == 1


def test_turning_it_on_twice_changes_nothing(tmp_path):
    _c1, once, _o = _edit(tmp_path, HTTPS_CONF)
    cfg = tmp_path / "site.conf"
    cfg.write_text(once)
    code, twice, out = _edit(tmp_path, once)
    assert code == 0 and "already on" in out
    assert twice == once


def test_turning_it_off_restores_the_file_exactly(tmp_path):
    _c1, on_text, _o = _edit(tmp_path, HTTPS_CONF)
    assert "quic" in on_text
    _c2, off_text, _o2 = _edit(tmp_path, on_text, on=False)
    assert off_text == HTTPS_CONF, "removing it must leave the original file"


def test_a_site_with_no_https_listener_is_refused_rather_than_half_edited(tmp_path):
    plain = "server {\n    listen 80;\n    server_name shop.test;\n}\n"
    code, text, out = _edit(tmp_path, plain)
    assert code == 1
    assert text == plain
    assert "no https listener" in out
    assert h3.explain(1, out, on=True) == (False, h3.explain(1, out, on=True)[1])
    assert "Turn HTTPS on first" in h3.explain(1, out, on=True)[1]


# ── The command around it ────────────────────────────────────────────────────

def test_the_configuration_is_tested_before_anything_is_reloaded():
    """A configuration that does not parse does not break one site — the reload fails for
    the whole machine."""
    cmd = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                 with_reuseport=True)
    assert cmd.index("nginx -t") < cmd.index("reload nginx")


def test_a_refused_configuration_is_put_back():
    cmd = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                 with_reuseport=True)
    assert 'cp -p "$BAK" "$CFG"' in cmd


def test_the_firewall_is_opened_for_udp_not_tcp():
    """QUIC is UDP. Opening 443/tcp again would do nothing, and the port staying shut is the
    failure where everything looks configured and no visitor can connect."""
    on = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                with_reuseport=True)
    off = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=False,
                                 with_reuseport=False)
    assert "ufw allow 443/udp" in on
    assert "ufw allow" not in off, "turning it off must not open anything"


def test_success_is_judged_on_content_not_a_status_code():
    cmd = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                 with_reuseport=True)
    assert '[ -z "$BODY" ]' in cmd


def test_a_site_that_was_already_broken_is_not_blamed_on_this():
    cmd = h3.build_apply_command("/etc/nginx/x.conf", "shop.test", on=True,
                                 with_reuseport=True)
    assert "WAS=$(curl" in cmd and "OK-BROKEN" in cmd
    assert cmd.index("WAS=$(curl") < cmd.index('cp -p "$BAK" "$CFG"')


@pytest.mark.parametrize("code,out,on,ok,says", [
    (0, ">>> OK: 200", True, True, "HTTP/3 is on"),
    (0, ">>> OK: 200", False, True, "HTTP/3 is off"),
    (0, ">>> OK-BROKEN: 500", True, True, "already not loading"),
    (1, "no https listener", True, False, "Turn HTTPS on first"),
    (1, ">>> ERROR: nginx refused the new configuration", True, False, "reuseport"),
    (1, ">>> ERROR: the site stopped serving after the change", True, False, "put back"),
])
def test_the_message_is_ours_and_names_the_likely_cause(code, out, on, ok, says):
    got_ok, message = h3.explain(code, out, on=on)
    assert got_ok is ok
    assert says in message


# ── The endpoint refuses before it writes ────────────────────────────────────
#
# The rule worth an endpoint test: a `quic` listener on an nginx that cannot parse it makes
# the web server refuse its WHOLE configuration, which is every site on the machine. So the
# probe decides, and the refusal happens before anything is written.

import uuid as _uuid

from app.database import AsyncSessionLocal, engine
from app.models import escalation as _escalation  # noqa: F401 — servers FK needs its table
from app.models.server import Server
from app.models.site import Site
from app.models.user import User
from app.routers import sites as sites_router
from app.services import crypto_service


@pytest.fixture(autouse=True)
async def _fresh_pool():
    yield
    await engine.dispose()


async def _site(db, *, panel=None):
    tag = _uuid.uuid4().hex[:8]
    user = User(email=f"h3-{tag}@example.com", password_hash="x", is_verified=True)
    db.add(user)
    await db.flush()
    server = Server(user_id=user.id, name=f"srv-{tag}", host="10.0.0.7", port=22,
                    username="root", auth_type="password", connection_type="ssh",
                    encrypted_cred=crypto_service.encrypt("pw"), panel_type=panel)
    db.add(server)
    await db.flush()
    site = Site(user_id=user.id, server_id=server.id, domain=f"{tag}.example.com",
                aliases=[], doc_root="/var/www/x", source="nginx", app_type="php",
                has_ssl=True, is_present=True, status="live")
    db.add(site)
    await db.flush()
    return user, site


def _written_block(ran) -> str:
    """What the apply command will actually put in the file."""
    import base64

    cmd = [c for c in ran if "BAK=" in c][0]
    arg = re.search(r'python3 - "\$CFG" (\S+) ', cmd)
    assert arg, "the apply command carried no block"
    return base64.b64decode(arg.group(1).strip("'")).decode()


def _server_says(monkeypatch, probe_out, apply_out=(">>> OK: 200", "", 0)):
    ran = []

    async def execute(_server, cmd):
        ran.append(cmd)
        if "quic=" in cmd or "--with-http_v3_module" in cmd:
            return probe_out, "", 0
        return apply_out

    async def config(*_a, **_k):
        return "/etc/nginx/sites-enabled/x.conf", False, None

    from app.services import connection_manager

    monkeypatch.setattr(connection_manager, "execute", execute)
    monkeypatch.setattr(sites_router, "_resolve_site_config", config)
    return ran


@pytest.mark.asyncio
async def test_a_server_that_cannot_do_it_is_refused_before_anything_is_written(monkeypatch):
    async with AsyncSessionLocal() as db:
        user, site = await _site(db)
        await db.commit()
        ran = _server_says(monkeypatch,
                           "nginx=yes\nversion=1.24.0\nquic=no\nreuseport=free\n"
                           "on=no\nhttps=yes\nudp=shut")

        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            await sites_router.set_http3(str(site.id), sites_router.Http3In(enabled=True),
                                         db, user)

    assert exc.value.status_code == 422
    assert "1.24.0" in str(exc.value.detail)
    assert not any("listen 443 quic" in c or "BAK=" in c for c in ran), (
        "nothing may be written to the configuration")


@pytest.mark.asyncio
async def test_reuseport_is_taken_from_the_server_not_assumed(monkeypatch):
    """Exactly one listener in the whole configuration may carry it, and a second makes nginx
    refuse to start. Proven against real nginx; this pins that the endpoint asks."""
    async with AsyncSessionLocal() as db:
        user, site = await _site(db)
        await db.commit()
        ran = _server_says(monkeypatch,
                           "nginx=yes\nversion=1.27.5\nquic=yes\nreuseport=taken\n"
                           "on=no\nhttps=yes\nudp=open")
        await sites_router.set_http3(str(site.id), sites_router.Http3In(enabled=True),
                                     db, user)

    # Decoded, because the block travels base64-encoded — asserting on the command text
    # would silently pass whatever the block actually says.
    wrote = _written_block(ran)
    assert "quic reuseport" not in wrote
    assert "listen 443 quic;" in wrote


@pytest.mark.asyncio
async def test_the_first_site_does_claim_it(monkeypatch):
    async with AsyncSessionLocal() as db:
        user, site = await _site(db)
        await db.commit()
        ran = _server_says(monkeypatch,
                           "nginx=yes\nversion=1.27.5\nquic=yes\nreuseport=free\n"
                           "on=no\nhttps=yes\nudp=open")
        await sites_router.set_http3(str(site.id), sites_router.Http3In(enabled=True),
                                     db, user)

    assert "quic reuseport" in _written_block(ran)


@pytest.mark.asyncio
async def test_turning_it_off_is_never_blocked_by_the_probe(monkeypatch):
    """A server that has lost its HTTP/3 nginx must still be able to remove the block —
    otherwise an upgrade that drops the module leaves a configuration nobody can fix."""
    async with AsyncSessionLocal() as db:
        user, site = await _site(db)
        await db.commit()
        ran = _server_says(monkeypatch,
                           "nginx=yes\nversion=1.24.0\nquic=no\nreuseport=taken\n"
                           "on=yes\nhttps=yes\nudp=open")
        out = await sites_router.set_http3(str(site.id), sites_router.Http3In(enabled=False),
                                           db, user)

    assert out["enabled"] is False
    assert any("BAK=" in c for c in ran)


@pytest.mark.asyncio
async def test_a_panel_server_is_refused_by_name(monkeypatch):
    """A panel rewrites its own vhosts on its own schedule, so anything we add is reverted
    later — at a moment nobody can connect to us."""
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        user, site = await _site(db, panel="cyberpanel")
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await sites_router.read_http3(str(site.id), db, user)

    assert "cyberpanel" in str(exc.value.detail)
