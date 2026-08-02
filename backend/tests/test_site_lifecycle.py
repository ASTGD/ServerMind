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
from app.services import playbook_service, site_service, site_service as ss


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
    """Returns (Site, PlaybookRun) pairs, as the reconcile query does.

    It also answers ``.scalars()`` with nothing, because reconciling now settles uptime
    checks too and asks for rows a different way. A fake that models only the shape it was
    written for stops being a test of the caller and starts being a trap.
    """

    def __init__(self, pairs):
        self._pairs = pairs
        self.committed = False

    async def execute(self, _stmt):
        pairs = self._pairs

        class _R:
            def all(self_inner):
                return pairs

            def scalars(self_inner):
                class _S:
                    def all(self_deep):
                        return []
                return _S()

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
    """Stand-ins carrying the same variables the real installers declare.

    Keyed by the real slugs, so the catalogue's "can this be installed onto an existing
    site" rule — which reads the real definitions — applies to them unchanged.
    """
    return {
        "create-site": _Pb("create-site", [
            {"name": "DOMAIN", "label": "Domain", "required": True},
            {"name": "WEB_ROOT", "label": "Web root", "default": "/var/www", "required": True},
            {"name": "WITH_PHP", "label": "With PHP", "default": "yes", "required": True}]),
        "wordpress-site": _Pb("wordpress-site", [
            {"name": "DOMAIN", "label": "Domain", "required": True},
            {"name": "DB_NAME", "label": "Database", "default": "wordpress", "required": True},
            {"name": "DB_PASS", "label": "Database password", "required": True},
            {"name": "ADMIN_EMAIL", "label": "Admin email", "required": True}]),
        "laravel-site": _Pb("laravel-site", [{"name": "DOMAIN", "required": True}]),
        "create-app": _Pb("create-app", [
            {"name": "DOMAIN", "required": True},
            {"name": "APP_PORT", "label": "Port", "default": "3000", "required": True},
            {"name": "START_CMD", "label": "Start command", "required": False}]),
        "n8n": _Pb("n8n", [
            {"name": "DOMAIN", "required": True},
            {"name": "PORT", "label": "Port", "default": "5678", "required": True},
            {"name": "N8N_USER", "label": "User", "default": "admin", "required": True},
            {"name": "N8N_PASS", "label": "Password", "required": True}]),
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
    n8n = next(i for i in ss.catalogue(_all_playbooks()) if i["id"] == "n8n")
    assert {f["name"]: f for f in n8n["fields"]}["N8N_PASS"]["secret"] is True


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


def test_the_short_list_is_short_enough_to_choose_from():
    """Eight tiles is a choice; twelve under three headings is a catalogue to study.

    The point of the split is that almost nobody needs to see all of it, so if the
    "popular" set ever grows to most of the list it has stopped doing its job.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    items = ss.catalogue(by_slug)
    popular = [i for i in items if i["popular"]]

    assert 6 <= len(popular) <= 8, f"{len(popular)} shown up front"
    assert len(popular) < len(items), "everything is popular, so nothing is"


def test_the_common_website_kinds_are_all_offered_up_front():
    """These are what people actually put on a server. Hiding one behind "show all"
    would make the common case the slow one."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    popular = {i["id"] for i in ss.catalogue(by_slug) if i["popular"]}
    for expected in ("wordpress", "laravel", "static", "php", "app"):
        assert expected in popular, f"{expected} should not need a second click"


def test_every_offered_type_is_reachable_from_one_list_or_the_other():
    """"Show all" has to mean all of what is offered — a type in neither list is one
    nobody can ever reach from this screen."""
    items = ss.catalogue(_all_playbooks())
    popular = {i["id"] for i in items if i["popular"]}
    rest = {i["id"] for i in items if not i["popular"]}
    assert popular | rest == {i["id"] for i in items}
    assert not (popular & rest), "a type cannot be in both lists"


# --- Installing INTO a site that already exists -----------------------------------------
#
# A site is added by its domain alone, which builds an empty site; what runs on it is
# chosen afterwards. That means an installer has to be able to replace the empty site's own
# configuration — and ONLY that. These pin the two conditions that make it safe.

def _guards() -> str:
    from app.services.playbook_service import _SITE_GUARDS
    return _SITE_GUARDS


def test_takeover_requires_our_own_marker_in_the_existing_config():
    """A hand-written vhost must never be replaced, whatever flags are passed."""
    g = _guards()
    assert 'grep -q "Created by ServerAlly"' in g
    # Both conditions on the same branch: asking is not enough on its own.
    assert '[ "${TAKEOVER:-no}" = yes ] && grep -q "Created by ServerAlly"' in g


def test_without_takeover_an_existing_domain_is_still_refused():
    """The default has not changed: pointing a second site at a live domain is an error."""
    g = _guards()
    assert "is already configured on this server" in g


def test_adopt_dir_refuses_a_folder_with_anything_in_it():
    """The folder check is what stops a site in use being deleted. It allows exactly the
    placeholder page an empty site is made of, and nothing else."""
    g = _guards()
    assert 'find "$_d" -mindepth 1 ! -path "$_d/public" ! -path "$_d/public/index.html"' in g
    assert "already has files in it" in g


def test_the_installers_that_make_a_folder_call_adopt_dir_first():
    """Otherwise their own "already exists" check fires and the install never starts."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    for slug in ("create-site", "laravel-site"):
        item = next(p for p in OFFICIAL_PLAYBOOKS if p["slug"] == slug)
        script = _script_for(item)
        assert 'adopt_dir "$SITE_DIR"' in script, slug
        assert script.index('adopt_dir "$SITE_DIR"') < script.index('already exists. Nothing was changed'), slug


def test_only_installers_that_can_take_over_a_site_are_offered():
    """The catalogue is now used to install INTO a site that already exists, so an
    installer that writes its own configuration from scratch cannot appear there — it
    would leave two web-server entries fighting over one domain.

    Derived from the scripts, so an old installer earns its place back by being fixed
    rather than by being added to a list here.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    offered = {i["id"] for i in ss.catalogue(by_slug)}
    for type_id in offered:
        script = _script_for(by_slug[ss.SITE_TYPES[type_id]["playbook"]])
        assert "TAKEOVER" in script, f"{type_id} is offered but cannot take over a site"


def test_the_common_types_are_all_installable_today():
    """These are what the product is for. If one drops out of the catalogue because its
    installer cannot take over a site, that is a regression, not a detail."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    offered = {i["id"] for i in ss.catalogue(by_slug)}
    for expected in ("wordpress", "laravel", "static", "php", "app"):
        assert expected in offered, f"{expected} can no longer be installed onto a site"


# --- An unfilled placeholder must never reach a server ------------------------------------
#
# Found on a real server: running the LEMP playbook with no variables set the database root
# password to the literal text "{{MYSQL_ROOT_PASS}}". Nothing errored and nothing was
# logged — the box simply had a database nobody could open, with a password nobody chose.

def test_a_script_with_an_unfilled_placeholder_is_refused():
    from app.services.playbook_service import UnresolvedVariables, substitute_variables

    with pytest.raises(UnresolvedVariables) as exc:
        substitute_variables('MYSQL_ROOT_PASS="{{MYSQL_ROOT_PASS}}"', {})
    assert "MYSQL_ROOT_PASS" in str(exc.value)


def test_a_partly_filled_script_is_refused_too():
    """The dangerous shape: some answers given, one forgotten."""
    from app.services.playbook_service import UnresolvedVariables, substitute_variables

    with pytest.raises(UnresolvedVariables) as exc:
        substitute_variables('D="{{DOMAIN}}"\nP="{{DB_PASS}}"', {"DOMAIN": "shop.example.com"})
    assert "DB_PASS" in str(exc.value)
    assert "DOMAIN" not in str(exc.value), "only name what is actually still missing"


def test_a_fully_answered_script_passes_through():
    from app.services.playbook_service import substitute_variables

    assert substitute_variables('D="{{DOMAIN}}"', {"DOMAIN": "shop.example.com"}) \
        == 'D="shop.example.com"'


def test_the_guard_does_not_fire_on_ordinary_shell_braces():
    """A narrow pattern on purpose: heredocs for nginx and systemd are full of braces, and
    a guard that refused those would block every installer that writes a config."""
    from app.services.playbook_service import substitute_variables

    for text in ('echo "${HOME}"', 'awk "{{print $1}}"', "func() {{ :; }}", "${!x}"):
        assert substitute_variables(text, {}) == text


def test_every_official_playbook_is_runnable_with_its_own_declared_answers():
    """If a playbook needs a value it never declares, nobody can run it — the guard would
    refuse every attempt, and the customer would have no way to supply the missing one."""
    from app.services.playbook_service import (OFFICIAL_PLAYBOOKS, _script_for,
                                               substitute_variables)

    for item in OFFICIAL_PLAYBOOKS:
        script = _script_for(item)
        if not script:
            continue
        answers = {v["name"]: (v.get("default") or "x") for v in item.get("variables", [])}
        substitute_variables(script, answers)   # raises if the playbook is unrunnable


# --- The takeover switch has to actually reach the script ---------------------------------
#
# It did not. The guard read ${TAKEOVER:-no} and NOTHING ever set it — install() passed it
# as a substitution variable with no placeholder to fill, so the branch always took the "no"
# path and installing onto an existing site was quietly impossible. The tests above this one
# all passed, because they checked that the guard's text existed rather than that the value
# could ever arrive. A script is delivered as text to a fresh shell: substitution is the
# only channel there is.

def test_the_takeover_switch_is_fillable_by_substitution():
    from app.services.playbook_service import _SITE_GUARDS

    assert 'TAKEOVER="{{TAKEOVER}}"' in _SITE_GUARDS, (
        "nothing can set this from outside — a script reaches the server as text"
    )


def test_an_install_really_turns_takeover_on_in_the_finished_script():
    """End to end through substitution, which is what actually runs."""
    from app.services.playbook_service import (OFFICIAL_PLAYBOOKS, _script_for,
                                               substitute_variables)

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    spec = ss.SITE_TYPES["wordpress"]
    answers = {v["name"]: (v.get("default") or "x")
               for v in by_slug[spec["playbook"]]["variables"]}
    # Exactly what install() sends: the type's own extras, then TAKEOVER forced on.
    answers.update({**spec["extra"], "TAKEOVER": "yes"})

    script = substitute_variables(_script_for(by_slug[spec["playbook"]]), answers)
    assert 'TAKEOVER="yes"' in script
    assert "{{TAKEOVER}}" not in script


def test_creating_a_site_leaves_takeover_off():
    """A fresh create must never adopt anything — it has nothing to adopt, and a stray
    "yes" would let it replace a config that happened to be ours."""
    from app.services.playbook_service import (OFFICIAL_PLAYBOOKS, _script_for,
                                               substitute_variables)

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for type_id, spec in ss.SITE_TYPES.items():
        item = by_slug.get(spec["playbook"])
        if item is None or "{{TAKEOVER}}" not in (_script_for(item) or ""):
            continue
        answers = {v["name"]: (v.get("default") or "x") for v in item["variables"]}
        answers.update(spec["extra"])          # what create() sends
        script = substitute_variables(_script_for(item), answers)
        assert 'TAKEOVER="no"' in script, f"{type_id} would adopt on a fresh create"


def test_anything_other_than_yes_is_treated_as_no():
    """The value arrives as text from a form and an API. Only an exact "yes" may unlock it."""
    from app.services.playbook_service import _SITE_GUARDS

    assert 'case "$TAKEOVER" in yes) : ;; *) TAKEOVER=no ;; esac' in _SITE_GUARDS


def test_the_customer_is_never_asked_about_takeover():
    """It is ours to decide, not a question. In `extra`, so the catalogue filters it out."""
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS

    by_slug = {p["slug"]: p for p in OFFICIAL_PLAYBOOKS}
    for item in ss.catalogue(by_slug):
        assert "TAKEOVER" not in [f["name"] for f in item["fields"]], item["id"]


# ── Every installer must be runnable from the site path ──────────────────────
#
# Adding a site sends ONE thing — a domain. Everything else the script needs has to come
# from the playbook's own declared defaults. This was broken in exactly the way an offline
# test cannot notice: the code was right, the playbooks were right, and the join between
# them was missing, so creating a site failed with "This installer still needs WEB_ROOT".

class _FakePlaybook:
    def __init__(self, variables):
        self.variables = variables


def test_declared_defaults_are_read_off_the_playbook():
    pb = _FakePlaybook([
        {"name": "WEB_ROOT", "default": "/var/www", "required": True},
        {"name": "APP_PORT", "default": "3000", "required": True},
    ])
    assert playbook_service.declared_defaults(pb) == {
        "WEB_ROOT": "/var/www", "APP_PORT": "3000"}


def test_an_optional_variable_with_an_empty_default_means_empty():
    """The opposite case, and the one that made "Web application" un-installable.

    ``create-app`` writes ``if [ -n "$START_CMD" ]`` — the script is built to receive
    nothing there. Leaving it unsubstituted made the guard refuse a valid install, which
    only the per-type test below noticed.
    """
    pb = _FakePlaybook([{"name": "START_CMD", "default": "", "required": False}])
    defaults = playbook_service.declared_defaults(pb)
    assert defaults == {"START_CMD": ""}
    assert playbook_service.substitute_variables("CMD={{START_CMD}}", defaults) == "CMD="


def test_a_required_variable_with_an_empty_default_stays_missing():
    """``DB_PASS`` declares "" meaning "you must supply this".

    Treating that as a default is how a playbook once set a database root password to the
    literal text of an unfilled placeholder. It must stay missing so the guard refuses.
    """
    pb = _FakePlaybook([
        {"name": "DB_PASS", "default": "", "required": True},
        {"name": "DB_NAME", "default": "wordpress", "required": True},
    ])
    defaults = playbook_service.declared_defaults(pb)
    assert "DB_PASS" not in defaults
    assert defaults == {"DB_NAME": "wordpress"}

    with pytest.raises(playbook_service.UnresolvedVariables):
        playbook_service.substitute_variables(
            "PASS='{{DB_PASS}}'", {**defaults, "DOMAIN": "x.com"})


def test_declared_defaults_survive_a_playbook_with_junk_variables():
    """A row read back from the database may hold anything."""
    assert playbook_service.declared_defaults(_FakePlaybook(None)) == {}
    assert playbook_service.declared_defaults(_FakePlaybook([])) == {}
    assert playbook_service.declared_defaults(_FakePlaybook(["not-a-dict"])) == {}
    assert playbook_service.declared_defaults(
        _FakePlaybook([{"default": "orphan"}, {"name": "OK", "default": 42}])) == {}


@pytest.mark.parametrize("site_type", sorted(site_service.SITE_TYPES))
def test_every_offered_installer_runs_with_only_a_domain(site_type):
    """The real regression test: for each type the chooser offers, the playbook's own
    defaults plus the domain plus the type's fixed values must fill EVERY placeholder.

    Anything left over is a type that cannot be installed from its own page — which is
    what "The site could not be added" turned out to mean.
    """
    spec = site_service.SITE_TYPES[site_type]
    row = next((p for p in playbook_service.OFFICIAL_PLAYBOOKS
                if p["slug"] == spec["playbook"]), None)
    assert row is not None, f"{site_type} names a playbook that does not exist"
    pb = _FakePlaybook(row.get("variables"))

    # Fields the customer is genuinely asked for (a password) are supplied the way the
    # chooser's form supplies them. The point of the test is that nothing ELSE is missing.
    from_the_form = {
        v["name"]: "supplied-by-the-form"
        for v in (row.get("variables") or [])
        if v.get("required") and v.get("default") == "" and v["name"] != "DOMAIN"
    }

    # Assembled by the SERVICE, not rebuilt here — a copy of this merge in the test is what
    # let the original bug pass: the test proved its own dict was complete, never the one
    # the code actually builds.
    variables = site_service.install_variables(
        pb, spec, "shop.example.com", from_the_form, takeover=True)

    script = playbook_service.substitute_variables(row["script_bash"], variables)
    assert "{{" not in script


def test_the_values_this_feature_decides_cannot_be_overridden_by_the_caller():
    """A request that names its own TAKEOVER or DOMAIN must not win.

    Takeover is what allows an installer to clear a folder. It is granted because this site
    is a known-empty one WE built, not because it was asked for.
    """
    pb = _FakePlaybook([{"name": "WEB_ROOT", "default": "/var/www", "required": True}])
    spec = {"extra": {"WITH_PHP": "no", "TAKEOVER": "no"}}
    got = site_service.install_variables(
        pb, spec, "real.example.com",
        {"DOMAIN": "attacker.example.com", "TAKEOVER": "yes", "WEB_ROOT": "/srv"},
        takeover=False)
    assert got["DOMAIN"] == "real.example.com"
    assert got["TAKEOVER"] == "no"
    # A field the customer legitimately answers still wins over the playbook's default.
    assert got["WEB_ROOT"] == "/srv"


# ── A scan confirms; it never erases ─────────────────────────────────────────
#
# All three of these were live findings on one real Apache server: scanning it relabelled a
# site WE built as "found on the server", blanked its document root, and downgraded what it
# runs to Unknown. The cause is shared — the scan wrote what it could see over what we knew.

async def _scan(row, **seen):
    """Run the REAL sync over one existing row and one scan result.

    Deliberately not a local copy of the update branch — a test that reimplements the code
    it is checking passes when that code is reverted, which is how the variable-defaults bug
    survived its first test in this same file.
    """
    found = ss.DiscoveredSite(domain=row.domain, aliases=[], app_version="", **seen)
    await ss.sync(_FakeDb([row]), _server(), found=[found])
    return row


@pytest.mark.asyncio
async def test_a_site_we_built_is_never_relabelled_as_discovered():
    """Provenance is not something looking at the server can answer.

    It also governs whether we may remove the site — that permission means "we built it, so
    we know its layout" — and a scan silently revoked it.
    """
    row = _row("shop.example.com")
    row.source = "manual"
    await _scan(row, source="apache", doc_root="", app_type="unknown")
    assert row.source == "manual"


@pytest.mark.asyncio
async def test_a_site_we_found_keeps_tracking_which_web_server_reports_it():
    row = _row("shop.example.com")
    row.source = "nginx"
    await _scan(row, source="apache", doc_root="/var/www/shop", app_type="php")
    assert row.source == "apache"


@pytest.mark.asyncio
async def test_a_scan_that_cannot_see_a_document_root_does_not_blank_the_one_we_have():
    """Apache's ``-S`` reports no document root at all, so every Apache scan hit this."""
    row = _row("shop.example.com")
    row.doc_root = "/var/www/shop.example.com"
    await _scan(row, source="apache", doc_root="", app_type="unknown")
    assert row.doc_root == "/var/www/shop.example.com"


@pytest.mark.asyncio
async def test_a_scan_that_can_see_a_better_document_root_wins():
    row = _row("shop.example.com")
    row.doc_root = "/var/www/old"
    await _scan(row, source="nginx", doc_root="/var/www/new", app_type="php")
    assert row.doc_root == "/var/www/new"


@pytest.mark.asyncio
async def test_unknown_means_could_not_tell_and_never_overwrites_what_we_know():
    row = _row("shop.example.com")
    row.app_type, row.app_version = "wordpress", "6.9"
    await _scan(row, source="apache", doc_root="", app_type="unknown")
    assert row.app_type == "wordpress"
    assert row.app_version == "6.9"


@pytest.mark.asyncio
async def test_a_scan_that_really_identifies_an_app_updates_it():
    """The customer installed WordPress by hand onto an empty site — the scan is right."""
    row = _row("shop.example.com")
    row.app_type = "static"
    found = ss.DiscoveredSite(domain="shop.example.com", aliases=[],
                              doc_root="/var/www/shop", source="nginx",
                              app_type="wordpress", app_version="6.9.1")
    await ss.sync(_FakeDb([row]), _server(), found=[found])
    assert row.app_type == "wordpress" and row.app_version == "6.9.1"


# ── An installer must not send the customer away to do something first ───────

def test_installing_laravel_also_installs_composer():
    """A fresh Ubuntu 24.04 has neither Composer nor unzip, so refusing until somebody
    installs them is refusing on every new server. Same mistake the WordPress playbook made
    about wp-cli, and the same fix: a product whose point is not needing expertise should
    not stop and ask for some.
    """
    script = next(p for p in playbook_service.OFFICIAL_PLAYBOOKS
                  if p["slug"] == "laravel-site")["script_bash"]
    assert "getcomposer.org/installer" in script
    assert "pkg_install unzip" in script, "Composer cannot unpack anything without it"
    assert "command -v composer >/dev/null" in script, "not reinstalled when already there"


def test_the_composer_installer_is_verified_before_it_is_run_as_root():
    """It downloads a PHP script and executes it as root. Composer publishes the hash for
    exactly that reason; skipping the check would mean running whatever the network
    returned. Proven on a real Ubuntu 24.04 both ways — it installs when the signature
    matches, and refuses with nothing changed when it cannot be fetched.
    """
    script = next(p for p in playbook_service.OFFICIAL_PLAYBOOKS
                  if p["slug"] == "laravel-site")["script_bash"]
    block = script[script.index("Installing Composer"):script.index("Composer installed")]
    assert "composer.github.io/installer.sig" in block
    assert "hash_file('sha384'" in block
    # Fails CLOSED: an empty signature is a failure to verify, not permission to proceed.
    assert '[ -z "$EXPECTED" ]' in block
    assert "exit 1" in block


# ── A repair function nobody calls repairs nothing ───────────────────────────

def test_the_install_reconciler_is_actually_called_by_something():
    """It existed, worked, was tested — and had NO callers anywhere.

    So a site whose installer failed sat at "Setting up…" indefinitely. A customer watched
    one claim to be building for two hours after it had failed. This is the second time in
    this codebase that a correct repair function turned out to be dead code, which is why
    the wiring is now asserted rather than assumed.
    """
    import pathlib

    router = pathlib.Path(__file__).resolve().parents[1] / "app" / "routers" / "sites.py"
    text = router.read_text()
    calls = text.count("reconcile_installs(")
    assert calls >= 3, (
        f"only {calls} caller(s): every path that TELLS somebody a site's state must "
        f"reconcile first — the fleet list, the per-server list, and the site's own page"
    )


def test_every_path_that_reports_a_sites_state_reconciles_first():
    """Named individually, because the per-server list is the one the customer was looking
    at when they saw a two-hour-old "Setting up…", and wiring only the fleet list would
    have left exactly that page wrong."""
    import pathlib
    import re

    text = (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "routers" / "sites.py").read_text()
    for endpoint in ("async def list_sites", "async def server_sites", "async def get_site"):
        start = text.index(endpoint)
        body = text[start:start + 1400]
        assert "reconcile_installs" in body, f"{endpoint} does not reconcile"


def test_a_site_list_from_an_unreachable_server_says_it_cannot_be_trusted():
    """A server whose identity changed cannot be looked at, so its site list is the last
    thing we saw. Without saying so the page showed four sites from a wiped server, each
    with a confident-sounding reason for being down — stale data presented as current."""
    import pathlib

    text = (pathlib.Path(__file__).resolve().parents[1]
            / "app" / "routers" / "sites.py").read_text()
    body = text[text.index("async def server_sites"):]
    body = body[:body.index("\n@router")]
    assert "stale_because" in body
    for status in ("host_changed", "auth_failed", "offline"):
        assert status in body, f"{status} must count as 'cannot be looked at'"
