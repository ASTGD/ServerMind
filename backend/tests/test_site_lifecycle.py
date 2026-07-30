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
