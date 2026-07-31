"""A site you create, and how discovery reconciles with it.

Two paths now write to `sites`: the customer creating one, and a scan finding what is really
on the server. Where they meet is where this is either correct or quietly broken, so that is
what these pin.

The rule underneath all of it: **live means observed.** An installer exiting 0 does not make
a site live — the same "content, not status" discipline the mission verification gate
follows, and for the same reason.
"""
from __future__ import annotations

import uuid

import pytest

from app.models.site import STATUSES, Site
from app.services import site_service as ss


class _FakeDb:
    """Enough session to run sync() against rows held in memory."""

    def __init__(self, rows: list[Site]):
        self._rows = rows
        self.added: list[Site] = []
        self.committed = False

    async def execute(self, _stmt):
        rows = self._rows

        class _R:
            def scalars(self_inner):
                return self_inner

            def all(self_inner):
                return rows

        return _R()

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.committed = True


def _server():
    class _S:
        id = uuid.uuid4()
        user_id = uuid.uuid4()
        name = "web1"
    return _S()


def _row(domain: str, *, status: str = "live", present: bool = True) -> Site:
    s = Site(domain=domain, aliases=[], doc_root="/var/www", source="nginx",
             app_type="php", has_ssl=False, is_present=present, status=status)
    s.id = uuid.uuid4()
    s.install_error = "the old error" if status == "failed" else None
    return s


def _found(domain: str) -> ss.DiscoveredSite:
    return ss.DiscoveredSite(domain=domain, aliases=[], doc_root="/var/www",
                             source="nginx", app_type="php", app_version="", has_ssl=False)


# ── The two paths must not fight ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_site_being_installed_is_not_reported_as_gone():
    """The bug this whole phase had to avoid.

    A scan running in the seconds between "create" and the vhost existing finds nothing for
    that domain. The old sweep marked anything it did not find as absent — so a site the
    customer asked for one moment earlier would be shown as disappeared.
    """
    installing = _row("new.example.com", status="installing")
    db = _FakeDb([installing])
    summary = await ss.sync(db, _server(), found=[])  # the scan sees nothing yet

    assert installing.is_present is True, "a site mid-install has not disappeared"
    assert installing.status == "installing"
    assert summary["gone"] == 0


@pytest.mark.asyncio
async def test_a_failed_site_is_not_reported_as_gone_either():
    """It never arrived, so it cannot vanish. Marking it gone would hide the failure."""
    failed = _row("broken.example.com", status="failed")
    db = _FakeDb([failed])
    await ss.sync(db, _server(), found=[])
    assert failed.is_present is True
    assert failed.status == "failed"
    assert failed.install_error, "the reason must survive so the customer can read it"


@pytest.mark.asyncio
async def test_seeing_the_site_is_what_makes_it_live():
    """Not the installer's exit code — the scan actually finding it on the server."""
    installing = _row("new.example.com", status="installing")
    db = _FakeDb([installing])
    await ss.sync(db, _server(), found=[_found("new.example.com")])

    assert installing.status == "live"
    assert installing.doc_root == "/var/www"


@pytest.mark.asyncio
async def test_a_failed_site_that_turns_up_is_believed():
    """The customer fixed it by hand, or a step we called failed had actually worked.

    Reality beats our record, and the stale error must not linger on a working site.
    """
    failed = _row("fixed.example.com", status="failed")
    db = _FakeDb([failed])
    await ss.sync(db, _server(), found=[_found("fixed.example.com")])

    assert failed.status == "live"
    assert failed.install_error is None, "a live site must not still show why it once failed"


@pytest.mark.asyncio
async def test_a_live_site_that_disappears_is_still_marked_gone():
    """The original behaviour must survive: this is how "when did it vanish?" stays answerable."""
    live = _row("old.example.com", status="live")
    db = _FakeDb([live])
    summary = await ss.sync(db, _server(), found=[])
    assert live.is_present is False
    assert summary["gone"] == 1


@pytest.mark.asyncio
async def test_a_discovered_site_is_live_immediately():
    """It was observed, which is the whole definition."""
    db = _FakeDb([])
    await ss.sync(db, _server(), found=[_found("found.example.com")])
    assert len(db.added) == 1
    assert db.added[0].status == "live"


# ── The catalogue ────────────────────────────────────────────────────────────

def test_every_site_type_names_an_installer_that_exists():
    """A type in the menu with no playbook behind it is a button that cannot work."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    slugs = {p["slug"] for p in OFFICIAL_PLAYBOOKS}
    for name, spec in ss.SITE_TYPES.items():
        assert spec["playbook"] in slugs, (
            f"site type '{name}' points at playbook '{spec['playbook']}', which does not exist"
        )
        assert spec["label"], f"{name} has no label to show"


def test_every_site_type_declares_a_known_app_type():
    from app.models.site import APP_TYPES
    for name, spec in ss.SITE_TYPES.items():
        assert spec["app_type"] in APP_TYPES, f"{name}: unknown app_type {spec['app_type']}"


def test_the_statuses_are_the_ones_the_code_actually_uses():
    assert set(STATUSES) == {"installing", "live", "failed"}


# ── The rule the whole phase rests on ────────────────────────────────────────

class _PairDb:
    """Returns (Site, PlaybookRun) pairs, as the reconcile query does."""

    def __init__(self, pairs):
        self._pairs = pairs
        self.committed = False

    async def execute(self, _stmt):
        pairs = self._pairs

        class _R:
            def all(self_inner):
                return pairs

        return _R()

    async def commit(self):
        self.committed = True


class _Run:
    def __init__(self, status, reason=None):
        self.status = status
        self.failure_reason = reason


@pytest.mark.asyncio
async def test_a_successful_installer_does_NOT_make_a_site_live():
    """The rule this whole phase rests on: live means OBSERVED.

    An installer can exit 0 having written a vhost that does not serve — a wrong root, a
    PHP-FPM socket that is not there, a config the web server never reloaded. Trusting the
    exit code is precisely the false-green this product exists to catch, so a finished run
    leaves the site `installing` until a scan actually sees it.

    Mutation testing found this unprotected: making success mark a site live broke nothing.
    """
    site = _row("new.example.com", status="installing")
    db = _PairDb([(site, _Run("success"))])

    changed = await ss.reconcile_installs(db, uuid.uuid4())

    assert site.status == "installing", (
        "a run that exited 0 is not evidence the site serves — only a scan is"
    )
    assert changed == 0


@pytest.mark.asyncio
async def test_a_failed_installer_marks_the_site_failed_with_its_reason():
    """A failure has to land somewhere the customer will actually look."""
    site = _row("broken.example.com", status="installing")
    db = _PairDb([(site, _Run("failed", "Could not reach the package server"))])

    changed = await ss.reconcile_installs(db, uuid.uuid4())

    assert site.status == "failed"
    assert "package server" in site.install_error
    assert changed == 1
    assert db.committed


@pytest.mark.asyncio
async def test_a_still_running_installer_leaves_the_site_alone():
    site = _row("busy.example.com", status="installing")
    db = _PairDb([(site, _Run("running"))])
    assert await ss.reconcile_installs(db, uuid.uuid4()) == 0
    assert site.status == "installing"


@pytest.mark.asyncio
async def test_a_failure_with_no_reason_still_says_something_useful():
    """"It failed" with a blank explanation is a dead end for the customer."""
    site = _row("quiet.example.com", status="installing")
    db = _PairDb([(site, _Run("failed", None))])
    await ss.reconcile_installs(db, uuid.uuid4())
    assert site.install_error and len(site.install_error) > 10


# ── Creating one ─────────────────────────────────────────────────────────────
#
# These exist because `create()` originally had NO test: every rule below was written and
# none of it was exercised, so a wrong import name survived all the way to a 500 on the
# first real request. Unit tests that cover only the neighbours are not coverage.

class _CreateDb:
    """Serves the duplicate lookup and the playbook lookup, and records what was added."""

    def __init__(self, dup=None, playbook=None):
        self._answers = [dup, playbook]
        self.added: list = []
        self.committed = False

    async def execute(self, _stmt):
        value = self._answers.pop(0) if self._answers else None

        class _R:
            def scalar_one_or_none(self_inner):
                return value

        return _R()

    def add(self, obj):
        self.added.append(obj)
        if getattr(obj, "id", None) is None:
            obj.id = uuid.uuid4()

    async def flush(self):
        pass

    async def commit(self):
        self.committed = True

    async def refresh(self, _obj):
        pass


class _Playbook:
    id = uuid.uuid4()
    script_bash = "echo installing {{DOMAIN}}"
    script_powershell = None


class _User:
    id = uuid.uuid4()


@pytest.mark.asyncio
async def test_creating_a_site_records_it_before_any_work_starts():
    """The whole point of P2. If the row were written after the install, a crash in between
    would leave work running with nothing to attribute it to, and the customer with no sign
    they ever asked."""
    db = _CreateDb(dup=None, playbook=_Playbook())
    site, run_id, script = await ss.create(
        db, _server(), _User(), domain="Shop.Example.com ", site_type="wordpress")

    assert site.status == "installing", "not live — nothing has been observed yet"
    assert site.domain == "shop.example.com", "the domain should be normalised"
    assert site.requested_type == "wordpress"
    assert site.install_run_id, "the row must point at the run doing the work"
    assert run_id and "shop.example.com" in script
    assert db.committed, "committed before the job is enqueued, or the worker may not find it"


@pytest.mark.asyncio
async def test_a_domain_a_customer_typed_badly_gets_a_readable_answer():
    """It reached the customer as "Internal Server Error" until this was caught live:
    clean_domain raises its own error type, which the router's handler did not know."""
    db = _CreateDb(dup=None, playbook=_Playbook())
    with pytest.raises(ss.SiteError) as exc:
        await ss.create(db, _server(), _User(), domain="not a domain", site_type="wordpress")
    assert "example.com" in str(exc.value).lower(), (
        f"the message should show what a good answer looks like: {exc.value}"
    )


@pytest.mark.asyncio
async def test_an_unknown_type_lists_what_is_available():
    db = _CreateDb()
    with pytest.raises(ss.SiteError) as exc:
        await ss.create(db, _server(), _User(), domain="a.example.com", site_type="drupal")
    assert "wordpress" in str(exc.value), "say what CAN be installed, not just what cannot"


@pytest.mark.asyncio
async def test_a_second_site_on_the_same_domain_is_refused():
    """Two installers writing one vhost is a mess nobody can untangle — including the
    double-click case, where the first is still installing."""
    existing = _row("shop.example.com", status="installing")
    db = _CreateDb(dup=existing, playbook=_Playbook())
    with pytest.raises(ss.SiteError) as exc:
        await ss.create(db, _server(), _User(), domain="shop.example.com", site_type="laravel")
    assert "already" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_a_missing_installer_is_reported_not_crashed():
    db = _CreateDb(dup=None, playbook=None)
    with pytest.raises(ss.SiteError) as exc:
        await ss.create(db, _server(), _User(), domain="a.example.com", site_type="wordpress")
    assert "not available" in str(exc.value).lower()


def test_the_api_actually_carries_the_new_state():
    """Caught by reading a real API response, not the database: the row had a status and
    the payload did not, which made every bit of P2 invisible to the customer."""
    site = _row("a.example.com", status="installing")
    site.requested_type = "wordpress"
    site.first_seen = site.last_seen = None
    site.server_id = None
    site.app_version = None
    out = ss.serialize(site)
    assert out["status"] == "installing"
    assert "install_error" in out
    assert out["requested_type"] == "wordpress"


# ── The catalogue the Sites page is built from ───────────────────────────────

class _Pb:
    def __init__(self, slug, variables=None, est=60):
        self.slug = slug
        self.variables = variables or []
        self.est_runtime_sec = est


def _all_playbooks():
    """Stand-ins carrying the same variables the real installers declare."""
    return {
        "create-site": _Pb("create-site", [
            {"name": "DOMAIN", "label": "Domain", "required": True},
            {"name": "WEB_ROOT", "label": "Web root", "default": "/var/www", "required": True},
            {"name": "WITH_PHP", "label": "With PHP", "default": "yes", "required": True}]),
        "wordpress": _Pb("wordpress", [
            {"name": "DOMAIN", "label": "Domain", "required": True},
            {"name": "DB_NAME", "label": "Database", "default": "wordpress", "required": True},
            {"name": "DB_PASS", "label": "Database password", "required": True},
            {"name": "ADMIN_EMAIL", "label": "Admin email", "required": True}]),
        "laravel-site": _Pb("laravel-site", [{"name": "DOMAIN", "required": True}]),
        "create-app": _Pb("create-app", [
            {"name": "DOMAIN", "required": True},
            {"name": "APP_PORT", "label": "Port", "default": "3000", "required": True},
            {"name": "START_CMD", "label": "Start command", "required": False}]),
        "nextcloud": _Pb("nextcloud", [
            {"name": "DOMAIN", "required": True},
            {"name": "NC_ADMIN_PASS", "label": "Admin password", "required": True}]),
        "ghost-cms": _Pb("ghost-cms", [{"name": "DOMAIN", "required": True}]),
    }


def test_the_catalogue_never_asks_for_the_domain_twice():
    """It is asked for once, above the type-specific questions."""
    for item in ss.catalogue(_all_playbooks()):
        names = [f["name"] for f in item["fields"]]
        assert "DOMAIN" not in names, f"{item['id']} asks for the domain again"


def test_a_choice_the_type_already_made_is_not_asked_of_the_customer():
    """Picking "Empty website" IS the answer to WITH_PHP. Asking again would let someone
    choose an empty PHP-less site and then switch PHP on, which is the other type."""
    empty = next(i for i in ss.catalogue(_all_playbooks()) if i["id"] == "static")
    assert "WITH_PHP" not in [f["name"] for f in empty["fields"]]
    assert "WEB_ROOT" in [f["name"] for f in empty["fields"]], (
        "a genuine question should still be asked"
    )


def test_passwords_are_marked_so_the_form_can_hide_them():
    """Same rule that decides what gets encrypted at rest, so the two cannot disagree."""
    wp = next(i for i in ss.catalogue(_all_playbooks()) if i["id"] == "wordpress")
    fields = {f["name"]: f for f in wp["fields"]}
    assert fields["DB_PASS"]["secret"] is True
    assert fields["DB_NAME"]["secret"] is False
    nc = next(i for i in ss.catalogue(_all_playbooks()) if i["id"] == "nextcloud")
    assert {f["name"]: f for f in nc["fields"]}["NC_ADMIN_PASS"]["secret"] is True


def test_a_type_whose_installer_is_missing_is_not_offered():
    """A button that cannot work is worse than no button — the customer has already
    decided to trust it by the time it declines."""
    partial = {"create-site": _all_playbooks()["create-site"]}
    ids = {i["id"] for i in ss.catalogue(partial)}
    assert ids == {"static", "php"}, f"only create-site types should survive: {ids}"


def test_every_type_belongs_to_a_group_that_exists():
    groups = {g[0] for g in ss.SITE_GROUPS}
    for item in ss.catalogue(_all_playbooks()):
        assert item["group"] in groups, f"{item['id']} is in unknown group {item['group']}"


#: The apps that install as a container on a port and need a domain put in front of them.
PORT_ONLY_APPS = ("gitea", "n8n", "uptime-kuma", "vaultwarden", "portainer")


def test_a_port_only_app_is_only_offered_once_it_can_take_a_domain():
    """These install as containers on a PORT.

    Offering one as a site before it can accept a domain would mean the customer types
    git.example.com and gets an IP with a port number — the "button that lets you down
    after you have decided to trust it" problem. So membership of the catalogue is tied to
    the installer actually accepting a DOMAIN, not to someone remembering to check.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for slug in PORT_ONLY_APPS:
        if slug not in ss.SITE_TYPES:
            continue  # not offered — nothing to prove
        pb = by_slug[slug]
        names = [v["name"] for v in (pb.get("variables") or [])]
        assert "DOMAIN" in names, (
            f"{slug} is offered as a site but its installer takes no DOMAIN, so the "
            f"customer would get an IP and a port instead of the address they typed"
        )
        assert "proxy_pass" in pb["script_bash"], (
            f"{slug} takes a DOMAIN but never puts a reverse proxy in front of it"
        )


def test_a_domain_is_optional_for_the_port_only_apps():
    """They also run on servers with no web server at all, where demanding a domain — and
    therefore an nginx — would break a setup that works today."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for slug in PORT_ONLY_APPS:
        var = next(v for v in by_slug[slug]["variables"] if v["name"] == "DOMAIN")
        assert var.get("required") is False, (
            f"{slug}: DOMAIN must stay optional so the port-only install keeps working"
        )


def test_portainer_is_proxied_over_https():
    """Its published port speaks TLS with a self-signed certificate. Proxying to it as
    plain http produces a 502 that looks like the app is broken."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    pb = next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == "portainer")
    assert "proxy_pass https://127.0.0.1:$PORT" in pb["script_bash"]
    assert "proxy_ssl_verify off" in pb["script_bash"], (
        "the certificate is self-signed by design, so verification must be off or every "
        "request fails"
    )
    # And the ones that speak plain HTTP must NOT be switched to https.
    for slug in ("gitea", "n8n", "uptime-kuma", "vaultwarden"):
        other = next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == slug)
        assert "proxy_pass http://127.0.0.1:$PORT" in other["script_bash"], (
            f"{slug} speaks plain HTTP on its port"
        )


def test_the_front_door_never_writes_a_vhost_without_a_domain():
    """The whole block is inside `if [ -n "$DOMAIN" ]`. Without that, a port-only install
    would write a vhost for an empty server_name and break the web server."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for slug in PORT_ONLY_APPS:
        script = by_slug[slug]["script_bash"]
        i = script.index("proxy_pass")
        before = script[:i]
        assert 'if [ -n "${DOMAIN:-}" ]; then' in before, (
            f"{slug}: the proxy must be guarded by a domain being set"
        )


def test_every_catalogue_entry_can_actually_be_created():
    """The catalogue and the create path must agree on the set of types."""
    for item in ss.catalogue(_all_playbooks()):
        assert item["id"] in ss.SITE_TYPES
        assert item["label"] and item["blurb"], f"{item['id']} needs something to show"


def test_every_catalogue_installer_generates_valid_bash():
    """Generate each installer's script and run `bash -n` over it.

    The front door is assembled from shared Python strings full of nested quoting and
    heredocs, so a broken script is a plausible mistake — and one that would only show up
    on a customer's server, mid-install. Both cases are covered because the domain is
    optional and the two paths differ.
    """
    import shutil
    import subprocess
    import tempfile

    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, substitute_variables

    bash = shutil.which("bash")
    if not bash:  # pragma: no cover
        pytest.skip("bash not available")

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for type_id, spec in ss.SITE_TYPES.items():
        pb = by_slug.get(spec["playbook"])
        assert pb is not None, f"{type_id}: playbook {spec['playbook']} is missing"

        for label, domain in (("with a domain", "app.example.com"), ("without one", "")):
            # Fill every declared variable so nothing is left as an unsubstituted
            # placeholder, which would itself be a syntax error.
            variables = {v["name"]: (v.get("default") or "x")
                         for v in (pb.get("variables") or [])}
            variables.update(spec["extra"])
            variables["DOMAIN"] = domain
            script = substitute_variables(pb["script_bash"], variables)

            assert "{{" not in script, f"{type_id} {label}: a placeholder was left unfilled"

            with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
                fh.write(script)
                path = fh.name
            try:
                result = subprocess.run([bash, "-n", path], capture_output=True, text=True)
            finally:
                import os
                os.unlink(path)

            assert result.returncode == 0, (
                f"{type_id} ({spec['playbook']}) {label} produced invalid bash:\n"
                f"{result.stderr.strip()[:400]}"
            )


def test_a_ready_made_app_never_asks_the_customer_for_a_port():
    """The whole point of putting a domain in front is that the port stops being their
    problem. Asking "which port?" reintroduces exactly the concept P4 removed — and the
    answer is one only we can sensibly give, since it has to match what the container
    publishes.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for item in ss.catalogue(by_slug):
        if item["group"] != "apps":
            continue
        names = [f["name"] for f in item["fields"]]
        assert "PORT" not in names, (
            f"{item['id']} asks the customer for a port; it should be decided for them"
        )


def test_the_port_we_decide_matches_what_the_container_publishes():
    """A port chosen here that the installer does not publish gives a proxy pointing at
    nothing — a 502 on a site that reports success."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for type_id, spec in ss.SITE_TYPES.items():
        port = spec["extra"].get("PORT")
        if not port:
            continue
        declared = next(v for v in by_slug[spec["playbook"]]["variables"]
                        if v["name"] == "PORT")
        assert declared.get("default") == port, (
            f"{type_id}: the catalogue installs on port {port} but the playbook's own "
            f"default is {declared.get('default')} — one of them is wrong"
        )


# --- Playbook definitions must actually reach the database ---------------------------
#
# P4 shipped reverse-proxy support as code while production's rows still had no DOMAIN
# variable, so nothing could be given a domain and the feature quietly did nothing. The
# cause was a sync that listed a handful of columns by hand and silently ignored the rest.

def test_sync_covers_every_field_a_definition_owns():
    """A field added to a playbook definition must reach existing rows, not only new ones.

    This is the test that was missing: the old sync updated five columns, so a changed
    title, category, estimated runtime or tag list stayed stale in the database forever
    while looking correct in the repo.
    """
    from app.services.playbook_service import _REPO_OWNED, _build_playbook, OFFICIAL_PLAYBOOKS

    built = _build_playbook(OFFICIAL_PLAYBOOKS[0])
    # Everything the builder sets is owned by the definition, except the identity of the
    # row itself and the counters the running system maintains.
    from sqlalchemy import inspect as sa_inspect

    set_by_builder = {
        c.key for c in sa_inspect(built).mapper.column_attrs
        if getattr(built, c.key, None) is not None
    }
    not_owned = {"id", "slug", "created_at", "updated_at", "run_count", "rating",
                 "author_id", "version"}
    missing = set_by_builder - not_owned - set(_REPO_OWNED)
    assert not missing, (
        f"the builder sets {sorted(missing)} but sync_official never copies them onto an "
        f"existing row, so changing one would never reach a deployed database"
    )


def test_sync_never_touches_the_counters_the_system_owns():
    """run_count and rating are earned by real use and must survive a redeploy."""
    from app.services.playbook_service import _REPO_OWNED

    for owned_by_the_system in ("run_count", "rating", "id", "slug", "created_at"):
        assert owned_by_the_system not in _REPO_OWNED, (
            f"{owned_by_the_system} would be overwritten on every startup"
        )
