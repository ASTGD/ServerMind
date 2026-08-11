"""One certificate, every name the site answers to.

Until now a certificate covered exactly the site's own domain. Nearly every real site is
also served at `www.`, and a certificate that does not name it gives half the visitors a
browser security warning — on a site whose owner has been told HTTPS is on. **That is worse
than no certificate, because it looks handled.**

Ploi asks for the extra names in a comma-separated box. Ours already knows them: they are
the site's aliases. Asking again would be a worse version of something already solved.
"""
import pytest

from app.services import playbook_service as pb
from app.services import ssl_service as ssl


# ── Which names ──────────────────────────────────────────────────────────────

def test_the_site_s_own_domain_comes_first():
    """certbot names the certificate after the first `-d`, and that name is the directory
    everything else refers to under /etc/letsencrypt/live."""
    assert ssl.names_for("shop.com", ["www.shop.com"])[0] == "shop.com"


def test_the_aliases_are_included_without_being_typed_again():
    assert ssl.names_for("shop.com", ["www.shop.com", "shop.co.uk"]) == \
        ["shop.com", "www.shop.com", "shop.co.uk"]


def test_duplicates_and_case_and_trailing_dots_are_tidied():
    """A duplicate `-d` is not fatal but it is noise in a certificate somebody may read."""
    assert ssl.names_for(" Shop.com. ", ["WWW.shop.com", "shop.com", "", None]) == \
        ["shop.com", "www.shop.com"]


def test_a_site_with_no_aliases_is_unchanged():
    assert ssl.names_for("shop.com", []) == ["shop.com"]
    assert ssl.names_for("shop.com", None) == ["shop.com"]


# ── A name reaching a shell ──────────────────────────────────────────────────

def test_the_flags_are_built_from_validated_names():
    assert ssl.certbot_domain_flags(["shop.com", "www.shop.com"]) == \
        "-d shop.com -d www.shop.com"


@pytest.mark.parametrize("bad", [
    "shop.com; rm -rf /", "shop.com && curl x|sh", "$(id)", "not a domain",
    "localhost", "-shop.com", "shop..com",
])
def test_anything_that_is_not_a_hostname_is_refused(bad):
    """A domain ends up in both a command and a filesystem path, so it is validated rather
    than escaped — the same rule the site guards already follow."""
    with pytest.raises(ssl.SslError):
        ssl.valid_name(bad)


def test_a_wildcard_is_refused_with_the_reason():
    """A wildcard cannot be proved over the web challenge this uses, so offering one would
    fail every time — better to say why than to let the customer find out from certbot."""
    with pytest.raises(ssl.SslError) as exc:
        ssl.valid_name("*.shop.com")
    assert "proved through DNS" in str(exc.value)


def test_no_names_at_all_is_refused():
    with pytest.raises(ssl.SslError):
        ssl.certbot_domain_flags([])


# ── The playbook actually uses them ──────────────────────────────────────────

def _spec():
    return next(p for p in pb.OFFICIAL_PLAYBOOKS if p["slug"] == "site-ssl")


def _script():
    return _spec()["script_bash"]


def _vars(**over):
    """Start from what the playbook DECLARES, then override.

    Substitution refuses a placeholder nobody filled — deliberately, because an unfilled
    value would otherwise be used as if it were the answer. So a test that hardcodes three
    variables breaks the day a fourth is added, and would be saying nothing about the
    behaviour it was written for. This mirrors what a caller has to do.
    """
    values = {v["name"]: v.get("default", "") for v in _spec()["variables"]}
    values.update(over)
    return values


def test_certbot_is_given_every_name():
    out = pb.substitute_variables(_script(), _vars(
        DOMAIN="shop.com", EMAIL="a@b.com",
        DOMAIN_FLAGS=ssl.certbot_domain_flags(["shop.com", "www.shop.com"])))
    assert 'DOMAIN_FLAGS="-d shop.com -d www.shop.com"' in out
    assert "certbot $PLUGIN $DOMAIN_FLAGS" in out
    assert "{{" not in out


def test_a_caller_that_sets_nothing_behaves_exactly_as_before():
    """The fallback exists so adding this could not change what an existing caller does."""
    out = pb.substitute_variables(_script(), _vars(
        DOMAIN="shop.com", EMAIL="a@b.com", DOMAIN_FLAGS=""))
    assert '[ -n "$DOMAIN_FLAGS" ] || DOMAIN_FLAGS="-d $DOMAIN"' in out
    assert "{{" not in out


def test_the_playbook_declares_the_variable_it_reads():
    """An undeclared placeholder is refused by substitution, which is how the whole install
    dies rather than one step — the lesson the setup work already learned."""
    declared = {v["name"] for v in _spec()["variables"]}
    assert "DOMAIN_FLAGS" in declared


# ── The endpoint: which failures are fatal and which are not ─────────────────
#
# Run against the real router and real Postgres, because the rule lives in the handler.
# The resolver is faked (a test cannot depend on public DNS) but everything else is real.

import uuid as _uuid

from app.database import AsyncSessionLocal, engine
from app.models import escalation as _escalation  # noqa: F401 — servers FK needs its table
from app.models.playbook import Playbook, PlaybookRun
from app.models.server import Server
from app.models.site import Site
from app.models.user import User
from app.routers import sites as sites_router
from app.services import crypto_service


async def _fixture(db, aliases):
    tag = _uuid.uuid4().hex[:8]
    user = User(email=f"ssl-{tag}@example.com", password_hash="x", is_verified=True)
    db.add(user)
    await db.flush()
    server = Server(user_id=user.id, name=f"srv-{tag}", host="203.0.113.9", port=22,
                    username="root", auth_type="password", connection_type="ssh",
                    encrypted_cred=crypto_service.encrypt("pw"))
    db.add(server)
    await db.flush()
    site = Site(user_id=user.id, server_id=server.id, domain=f"{tag}.example.com",
                aliases=aliases, doc_root="/var/www/x", source="nginx", app_type="php",
                has_ssl=False, is_present=True, status="live")
    db.add(site)
    await db.flush()
    return user, server, site


@pytest.fixture(autouse=True)
async def _fresh_pool():
    """Each async test gets its own event loop, and a pooled connection opened on the last
    one cannot be reused on this one. Disposing between tests is what lets several database
    tests live in one file."""
    yield
    await engine.dispose()


async def _site_ssl_playbook(db):
    """Use the real installer row when this database already has it (the dev database does —
    `sync_official` writes it at every startup), and create a stand-in when it does not."""
    from sqlalchemy import select as _sel

    row = (await db.execute(_sel(Playbook).where(Playbook.slug == "site-ssl"))).scalar_one_or_none()
    if row is None:
        row = Playbook(slug="site-ssl", title="HTTPS", is_official=True,
                       script_bash="D={{DOMAIN}} E={{EMAIL}} F={{DOMAIN_FLAGS}}")
        db.add(row)
    else:
        row.is_official = True
    return row


def _resolver(monkeypatch, *, ready: set):
    """Fake DNS: only the named hosts point at this server."""
    async def check_dns(domain, _server_host):
        ok = domain in ready
        return {"ready": ok, "points_to": [], "server_addresses": ["203.0.113.9"],
                "record": {"type": "A", "name": domain, "value": "203.0.113.9"},
                "reason": None if ok else "does not resolve"}

    monkeypatch.setattr(sites_router.ssl_service, "check_dns", check_dns)


def _no_celery(monkeypatch):
    sent = {}
    monkeypatch.setattr(sites_router.run_playbook_task, "delay",
                        lambda *a, **k: sent.update(script=a[2]))
    return sent


@pytest.mark.asyncio
async def test_a_stale_alias_does_not_block_the_certificate(monkeypatch):
    """The rule worth the endpoint test. Let's Encrypt validates EVERY name on a request and
    fails the whole thing if one cannot be reached — so one alias left over from a domain the
    customer stopped using would stop HTTPS entirely, and certbot's error names the alias
    without saying the rest were fine. It is excluded, and the exclusion is reported."""
    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, [f"www.{_uuid.uuid4().hex[:8]}.example.com",
                                                  "gone.example.com"])
        www = site.aliases[0]
        await _site_ssl_playbook(db)
        await db.commit()

        _resolver(monkeypatch, ready={site.domain, www})
        sent = _no_celery(monkeypatch)

        out = await sites_router.turn_on_ssl(str(site.id), db, user)

    assert out["covers"] == [site.domain, www]
    assert [e["name"] for e in out["excluded"]] == ["gone.example.com"]
    assert out["excluded"][0]["why"], "an excluded name must say why"
    # …and the certificate really is requested for both good names.
    assert f"-d {site.domain} -d {www}" in sent["script"]


@pytest.mark.asyncio
async def test_the_site_s_own_domain_not_pointing_here_is_fatal(monkeypatch):
    """The one name that cannot be skipped: it names the certificate, and a certificate for
    the aliases alone would not cover the site anybody actually visits."""
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, ["www.example.com"])
        await _site_ssl_playbook(db)
        await db.commit()

        _resolver(monkeypatch, ready={"www.example.com"})
        _no_celery(monkeypatch)

        with pytest.raises(HTTPException) as exc:
            await sites_router.turn_on_ssl(str(site.id), db, user)

    assert exc.value.status_code == 422
    assert site.domain in str(exc.value.detail)


@pytest.mark.asyncio
async def test_nothing_is_requested_when_it_would_fail(monkeypatch):
    """A failed attempt spends one of five certificates per domain per week, so a refusal
    must happen before the run row exists — not after certbot says no."""
    from sqlalchemy import func, select as _select
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, [])
        await _site_ssl_playbook(db)
        await db.commit()
        before = (await db.execute(_select(func.count()).select_from(PlaybookRun))).scalar()

        _resolver(monkeypatch, ready=set())
        _no_celery(monkeypatch)

        with pytest.raises(HTTPException):
            await sites_router.turn_on_ssl(str(site.id), db, user)

        after = (await db.execute(_select(func.count()).select_from(PlaybookRun))).scalar()

    assert after == before


@pytest.mark.asyncio
async def test_the_screen_can_say_what_will_be_covered_before_the_button(monkeypatch):
    """Ploi asks for the extra names in a box. Ours already knows them, so the readiness
    answer carries them — and says which ones will be left out."""
    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, ["www.example.com", "gone.example.com"])
        await db.commit()

        _resolver(monkeypatch, ready={site.domain, "www.example.com"})
        out = await sites_router.ssl_readiness(str(site.id), db, user)

    assert out["covers"] == [site.domain, "www.example.com"]
    assert [e["name"] for e in out["excluded"]] == ["gone.example.com"]


# ── The invariant this feature now depends on ────────────────────────────────

@pytest.mark.asyncio
async def test_an_alias_the_web_server_refused_never_reaches_the_certificate(monkeypatch):
    """certbot's nginx plugin finds a block for each `-d` by looking at `server_name`. So
    requesting a name the vhost does not answer to fails the whole certificate.

    The aliases endpoint already writes the vhost BEFORE saving the row, which is what makes
    the two agree — and this feature now depends on that ordering, so it is worth a test that
    fails if a later refactor saves the row first as an "optimisation"."""
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        user, server, site = await _fixture(db, [])
        await db.commit()

        async def _config(*_a, **_k):
            return "/etc/nginx/sites-enabled/x.conf", False, None

        async def _refused(*_a, **_k):
            return "", "nginx: configuration file test failed", 1

        from app.services import connection_manager

        monkeypatch.setattr(sites_router, "_resolve_site_config", _config)
        monkeypatch.setattr(connection_manager, "execute", _refused)

        with pytest.raises(HTTPException):
            await sites_router._alias_apply(server, site, ["www.example.com"], db)

        await db.refresh(site)
        assert site.aliases == [], "an alias the server refused must not be stored"
        # …and therefore can never be asked for.
        assert "www.example.com" not in ssl.names_for(site.domain, site.aliases)


# ── "Request anyway" — Ploi's skip-DNS-verification ──────────────────────────
#
# Our readiness check compares the domain's addresses with the server's, and there is one
# very common case where that is WRONG: a site behind Cloudflare's proxy (or any CDN)
# resolves to the CDN's addresses by design, while an HTTP request still reaches this server
# and the certificate would issue perfectly well. Refusing those customers outright is worse
# than letting them decide, so the check can be overridden — deliberately, and only by them.

@pytest.mark.asyncio
async def test_a_forced_request_skips_the_check_entirely(monkeypatch):
    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, ["www.example.com"])
        await _site_ssl_playbook(db)
        await db.commit()

        _resolver(monkeypatch, ready=set())      # nothing points here as far as we can tell
        sent = _no_celery(monkeypatch)

        out = await sites_router.turn_on_ssl(
            str(site.id), db, user, sites_router.SslIn(force=True))

    assert out["covers"] == [site.domain, "www.example.com"]
    assert out["excluded"] == []
    assert f"-d {site.domain} -d www.example.com" in sent["script"]


@pytest.mark.asyncio
async def test_forcing_still_refuses_a_name_that_is_not_a_domain(monkeypatch):
    """Skipping the DNS check does not skip validation. A name reaches both a shell and a
    filesystem path, and `force` is a statement about DNS — not permission to send anything."""
    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, ["shop.com; rm -rf /"])
        await _site_ssl_playbook(db)
        await db.commit()

        _resolver(monkeypatch, ready=set())
        _no_celery(monkeypatch)

        with pytest.raises(ssl.SslError):
            await sites_router.turn_on_ssl(
                str(site.id), db, user, sites_router.SslIn(force=True))


@pytest.mark.asyncio
async def test_not_forcing_is_still_the_default(monkeypatch):
    """An empty body must never mean "skip the safety check" — the gate has to be the thing
    you get when you ask for nothing."""
    from fastapi import HTTPException

    async with AsyncSessionLocal() as db:
        user, _server, site = await _fixture(db, [])
        await _site_ssl_playbook(db)
        await db.commit()

        _resolver(monkeypatch, ready=set())
        _no_celery(monkeypatch)

        for body in (None, sites_router.SslIn()):
            with pytest.raises(HTTPException):
                await sites_router.turn_on_ssl(str(site.id), db, user, body)


def test_the_refusal_names_the_innocent_cause():
    """A domain that resolves somewhere else is USUALLY a CDN, not a mistake. Saying only
    "not to this server" sends somebody to break a working setup."""
    check = {"ready": False, "points_to": ["104.21.0.1"], "reason": "points somewhere else",
             "record": {"type": "A", "name": "shop.com", "value": "203.0.113.9"}}
    msg = ssl.dns_message("shop.com", check)
    assert "Cloudflare" in msg and "anyway" in msg


def test_a_domain_that_resolves_nowhere_is_not_offered_the_override():
    """Nothing to override: no authority can validate a name that answers nowhere, so the
    button would only spend one of the five attempts allowed each week."""
    check = {"ready": False, "points_to": [], "reason": "does not resolve",
             "record": {"type": "A", "name": "shop.com", "value": "203.0.113.9"}}
    assert "anyway" not in ssl.dns_message("shop.com", check)
