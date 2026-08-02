"""Removing a site has to finish.

The customer pressed Remove on a failed site. The removal ran, the server confirmed there
was nothing left of it — and the row stayed on screen for ever, so from where they were
sitting nothing had happened at all.

Two faults, both in the handover between the run and the row:

* nothing ever deleted the row on success. The scan cannot do it either, because it
  deliberately never buries a row that is not ``live`` — the rule that stops a site being
  marked missing halfway through its own install;
* the removal reused the ``installing`` status and left ``install_run_id`` pointing at the
  ORIGINAL install, so the reconciler judged the removal by an unrelated run and put the
  site straight back to "Setup failed".
"""
import uuid

import pytest

from app.services import site_service as ss


class _Run:
    def __init__(self, status, reason=None):
        self.status = status
        self.failure_reason = reason


class _Site:
    def __init__(self, status="removing", domain="gone.example.com"):
        self.domain = domain
        self.status = status
        self.install_error = None
        self.is_present = True


class _Db:
    """Answers the reconcile join, then the two queries the uptime step makes."""

    def __init__(self, pairs):
        self._pairs = pairs
        self.deleted = []
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

    async def delete(self, obj):
        self.deleted.append(obj)

    async def commit(self):
        self.committed = True


@pytest.mark.asyncio
async def test_a_finished_removal_takes_the_row_with_it():
    """The whole point of the feature. Without this the site is gone from the server and
    still on the screen, which is worse than not removing it — the list now lies."""
    site = _Site()
    db = _Db([(site, _Run("success"), "site-remove")])

    changed = await ss.reconcile_installs(db, uuid.uuid4())

    assert db.deleted == [site]
    assert changed == 1 and db.committed


@pytest.mark.asyncio
async def test_a_removal_that_failed_says_so_and_keeps_the_row():
    """The site is still on the server, so the row must stay — and must not quietly go
    back to looking like an ordinary site."""
    site = _Site()
    db = _Db([(site, _Run("failed", "the web server rejected its own configuration"), "site-remove")])

    await ss.reconcile_installs(db, uuid.uuid4())

    assert db.deleted == []
    assert site.status == "remove_failed"
    assert "web server rejected" in site.install_error


@pytest.mark.asyncio
async def test_a_removal_still_running_is_left_alone():
    site = _Site()
    db = _Db([(site, _Run("running"), "site-remove")])

    assert await ss.reconcile_installs(db, uuid.uuid4()) == 0
    assert db.deleted == [] and site.status == "removing"


@pytest.mark.asyncio
async def test_a_failure_with_no_reason_still_says_something_useful():
    site = _Site()
    db = _Db([(site, _Run("failed", None), "site-remove")])
    await ss.reconcile_installs(db, uuid.uuid4())
    assert site.install_error and len(site.install_error) > 10


# ── The install path must not have changed ───────────────────────────────────

@pytest.mark.asyncio
async def test_an_install_that_succeeded_is_still_not_made_live_here():
    """Live means a scan SAW it. An installer exiting 0 is exactly the false green this
    product exists to catch, and a removal being concluded on success must not leak into
    the install path."""
    site = _Site(status="installing")
    db = _Db([(site, _Run("success"), "laravel-site")])

    assert await ss.reconcile_installs(db, uuid.uuid4()) == 0
    assert site.status == "installing"
    assert db.deleted == [], "an install that exited 0 must never delete the site"


@pytest.mark.asyncio
async def test_an_install_that_failed_still_becomes_failed():
    site = _Site(status="installing")
    db = _Db([(site, _Run("failed", "no web server is running on this server"), "site-remove")])

    await ss.reconcile_installs(db, uuid.uuid4())

    assert site.status == "failed"
    assert "no web server" in site.install_error


# ── The scan must keep its hands off both ────────────────────────────────────

def test_a_scan_never_buries_a_site_that_is_being_removed():
    """The same rule that stops a site being marked missing halfway through its install —
    and the reason the scan cannot be what finishes a removal."""
    import inspect

    source = inspect.getsource(ss.sync)
    assert 'row.status == "live"' in source, (
        "the scan marks rows absent by status; if that changed, a removing row can be "
        "buried mid-flight and the reconciler will never see it again"
    )


@pytest.mark.asyncio
async def test_a_removal_is_never_concluded_from_some_other_run():
    """The second half of the original bug, and the dangerous half.

    The row kept pointing at the ORIGINAL install, so a finished install was read as a
    finished removal. Concluding from the wrong run is worse than concluding late, so a
    run that is not the removal is left alone.
    """
    site = _Site()
    db = _Db([(site, _Run("success"), "laravel-site")])   # an INSTALL run, not the removal

    assert await ss.reconcile_installs(db, uuid.uuid4()) == 0
    assert db.deleted == [], "deleted a site on the strength of an unrelated run"
    assert site.status == "removing"
