"""An uptime check only runs while its site is really there.

Found on the real account: five checks were reporting "down" forever — for a site whose
install had failed and was never built, for three that were wiped when a server was
rebuilt, and for one whose site row had been deleted. None of those can ever recover, and
an alarm nobody can clear is how people learn to ignore every alarm we send.

The cause was narrow: checks are created after a scan for every site marked `is_present`,
and a failed install deliberately KEEPS that flag (it never arrived, so it cannot have
vanished). So we built a watcher for a site that did not exist.
"""
import pytest

from app.services import site_service as ss


class _Site:
    def __init__(self, domain, status="live", is_present=True):
        self.domain = domain
        self.status = status
        self.is_present = is_present


class _Monitor:
    def __init__(self, url, is_active=True):
        self.url = url
        self.is_active = is_active


class _Db:
    """Answers the two queries settle_uptime_checks makes, in order."""

    def __init__(self, sites, monitors):
        self._answers = [sites, monitors]
        self.committed = False

    async def execute(self, _stmt):
        rows = self._answers.pop(0) if self._answers else []

        class _R:
            def scalars(self_inner):
                class _S:
                    def all(self_deep):
                        return rows
                return _S()

        return _R()

    async def commit(self):
        self.committed = True


# ── The rule itself ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("status,present,watched", [
    ("live", True, True),        # a real site
    ("failed", True, False),     # never built — the exact bug
    ("installing", True, False),  # not there YET; checking it just cries wolf
    ("live", False, False),      # was there, a scan can no longer find it
    ("failed", False, False),
    (None, True, False),         # unknown state is not a licence to alarm
])
def test_only_a_site_that_exists_is_worth_checking(status, present, watched):
    assert ss.should_watch(status, present) is watched


# ── Applying it ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_failed_install_stops_being_watched():
    site = _Site("laravel.example.com", status="failed")
    monitor = _Monitor("https://laravel.example.com")
    db = _Db([site], [monitor])

    assert await ss.settle_uptime_checks(db, "u1") == 1
    assert monitor.is_active is False
    assert db.committed


@pytest.mark.asyncio
async def test_a_site_that_comes_back_is_watched_again():
    """Symmetry matters: a customer who fixes a site by hand must not have to remember
    to switch its check back on."""
    site = _Site("shop.example.com", status="live", is_present=True)
    monitor = _Monitor("https://shop.example.com", is_active=False)
    db = _Db([site], [monitor])

    assert await ss.settle_uptime_checks(db, "u1") == 1
    assert monitor.is_active is True


@pytest.mark.asyncio
async def test_a_domain_watched_on_its_own_is_never_touched():
    """The guard that makes this safe. A check with no site row of ours behind it belongs
    to the customer alone — the same reason deleting a site leaves its check running."""
    site = _Site("ours.example.com", status="failed")
    theirs = _Monitor("https://someone-elses-domain.com")
    db = _Db([site], [theirs])

    await ss.settle_uptime_checks(db, "u1")
    assert theirs.is_active is True, "we turned off a check for a domain we do not own"


@pytest.mark.asyncio
async def test_nothing_is_written_when_everything_already_agrees():
    site = _Site("fine.example.com")
    db = _Db([site], [_Monitor("https://fine.example.com")])

    assert await ss.settle_uptime_checks(db, "u1") == 0
    assert db.committed is False, "a no-op still wrote to the database"


@pytest.mark.asyncio
async def test_a_user_with_no_sites_is_left_completely_alone():
    db = _Db([], [_Monitor("https://anything.com")])
    assert await ss.settle_uptime_checks(db, "u1") == 0


@pytest.mark.parametrize("url,host", [
    ("https://shop.example.com", "shop.example.com"),
    ("http://shop.example.com/health", "shop.example.com"),
    ("https://SHOP.example.com", "shop.example.com"),
    ("https://shop.example.com:8443", "shop.example.com"),
    ("not a url at all", ""),
])
def test_a_check_is_matched_to_its_site_by_hostname(url, host):
    assert ss.monitor_host(url) == host
