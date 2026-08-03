"""An install that finished should not still say "Setting up".

Found live. Three sites were created on a real server; all three installers succeeded; and
all three sat on "Setting up" for five minutes until the owner pressed "Look for sites".

The rule underneath is right and stays: a site becomes live because a scan SEES it, never
because the installer exited 0 — that is what stops a green installer reporting a site
that does not serve. What was missing is that nothing ran the scan when an install ended.
"""
import pytest

from app.services import site_service


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    """Answers the two queries reconcile makes, in order."""

    def __init__(self, servers, rows=()):
        self._answers = [_Result(servers), _Result(list(rows))]
        self.commits = 0

    async def execute(self, _stmt):
        return self._answers.pop(0) if self._answers else _Result([])

    async def commit(self):
        self.commits += 1


class _Server:
    id, name, user_id = "s1", "TestServer", "u1"


@pytest.mark.asyncio
async def test_it_looks_at_a_server_whose_install_just_finished(monkeypatch):
    """The fix. Without this the site stays 'installing' until somebody presses a button."""
    looked = {}

    async def _discover(server):
        looked["server"] = server.name
        return ([], False, "")

    async def _sync(_db, server, found):
        looked["synced"] = (server.name, found)
        return {}

    monkeypatch.setattr(site_service, "discover", _discover)
    monkeypatch.setattr(site_service, "sync", _sync)

    n = await site_service._look_where_an_install_just_finished(_Db([_Server()]), "u1")
    assert n == 1
    assert looked["server"] == "TestServer"
    assert "synced" in looked, "it looked but never recorded what it saw"


@pytest.mark.asyncio
async def test_nothing_to_settle_costs_nothing(monkeypatch):
    """The ordinary case — every page load. If this ever starts reaching for SSH when there
    is no install outstanding, every list becomes as slow as the slowest server."""
    async def _boom(*_a, **_k):
        raise AssertionError("it went to the server with nothing to settle")

    monkeypatch.setattr(site_service, "discover", _boom)
    assert await site_service._look_where_an_install_just_finished(_Db([]), "u1") == 0


@pytest.mark.asyncio
async def test_an_unreachable_server_leaves_the_site_installing(monkeypatch):
    """Honest, not optimistic. We have not seen the site, so it must not be called live —
    and a page that is merely listing sites must not break because one server is down."""
    async def _discover(_server):
        return ([], False, "Connection refused")

    # RECORDED, not raised. The function deliberately catches everything so a broken server
    # cannot break a page — which means an AssertionError from inside a fake is swallowed
    # too, and the test can never fail. Mutation testing caught exactly that: deleting the
    # error check let `sync` run on a server we never reached, and this test still passed.
    synced = []

    async def _sync(_db, server, found):
        synced.append(server.name)
        return {}

    monkeypatch.setattr(site_service, "discover", _discover)
    monkeypatch.setattr(site_service, "sync", _sync)
    assert await site_service._look_where_an_install_just_finished(_Db([_Server()]), "u1") == 0
    assert synced == [], "it recorded a result it never obtained"


@pytest.mark.asyncio
async def test_a_crash_while_looking_never_breaks_the_list(monkeypatch):
    async def _discover(_server):
        raise RuntimeError("ssh exploded")

    monkeypatch.setattr(site_service, "discover", _discover)
    assert await site_service._look_where_an_install_just_finished(_Db([_Server()]), "u1") == 0


def test_it_only_looks_where_an_installer_actually_SUCCEEDED():
    """A failed install must not trigger a look — the reconciler already concludes those,
    and a site whose installer failed is not going to appear on the server."""
    import inspect
    src = inspect.getsource(site_service._look_where_an_install_just_finished)
    assert 'PlaybookRun.status == "success"' in src
    assert 'Site.status == "installing"' in src


@pytest.mark.asyncio
async def test_the_reconciler_does_the_looking_itself(monkeypatch):
    """One entry point, exercised. The three read endpoints call `reconcile_installs`; if
    the look sat beside it instead of inside it, it becomes a fourth thing to remember —
    which is exactly how the last three bugs in this area happened."""
    called = {}

    async def _look(_db, user_id):
        called["user"] = user_id
        return 0

    monkeypatch.setattr(site_service, "_look_where_an_install_just_finished", _look)
    await site_service.reconcile_installs(_Db([], []), "u1")
    assert called.get("user") == "u1", "reconcile_installs no longer looks"
