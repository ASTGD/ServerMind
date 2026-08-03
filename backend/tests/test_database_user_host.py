"""Which machine a database user may sign in from.

Until now every user was created as `'name'@'localhost'` — same machine only. That is
right for a site sitting on the same server, and it is why a Database Server could be
installed, firewalled correctly, and then refuse every connection from the web server it
exists to serve.

The dangerous fix is the easy one. `'name'@'%'` means "from anywhere", it is one character
from the correct answer, and combined with an open port it is how a database ends up owned.
So the host is validated, not accepted.
"""
import pytest

from app.services import database_service as d


# ── Nothing changes for a database on the same machine ───────────────────────

def test_the_default_is_still_this_machine_only():
    """Every database ever created here used localhost. That must keep working, and keep
    being what happens when nobody says otherwise."""
    sql = d.build_create_sql("mysql", "shop", "shopuser", "pw")
    assert "'shopuser'@'localhost'" in sql
    assert "@'%'" not in sql


def test_an_empty_host_means_this_machine():
    assert d.validate_host("") == "localhost"
    assert d.validate_host("   ") == "localhost"
    assert d.validate_host(None) == "localhost"


# ── The reason the feature exists ────────────────────────────────────────────

def test_a_user_can_be_allowed_from_another_server():
    sql = d.build_create_sql("mysql", "shop", "shopuser", "pw", "10.0.0.5")
    assert "CREATE USER 'shopuser'@'10.0.0.5'" in sql
    assert "TO 'shopuser'@'10.0.0.5'" in sql, "granted to a different account than it made"


def test_the_grant_and_the_user_always_match():
    """Two statements, one identity. If they drift the user exists and has no rights —
    which reads to the customer as a wrong password."""
    for host in ("localhost", "10.0.0.5", "192.168.1.44"):
        sql = d.build_create_sql("mysql", "shop", "u", "pw", host)
        assert sql.count(f"'u'@'{host}'") == 2, sql


# ── The one that must never be allowed ───────────────────────────────────────

@pytest.mark.parametrize("everywhere", ["%", "10.%.%.%", "%.example.com", "10.0.0.%", "_"])
def test_from_anywhere_is_refused(everywhere):
    """The whole point. A panel that quietly uses `%` trades the customer's safety for one
    less question; combined with an open port it is the crypto-miner story."""
    with pytest.raises(d.DatabaseError) as exc:
        d.validate_host(everywhere)
    assert "anywhere" in str(exc.value).lower()


def test_the_everyone_address_is_refused():
    with pytest.raises(d.DatabaseError):
        d.validate_host("0.0.0.0")


@pytest.mark.parametrize("bad", ["db.example.com", "localhost.localdomain", "10.0.0",
                                 "999.1.1.1", "10.0.0.5; DROP DATABASE x", "10.0.0.5'"])
def test_anything_that_is_not_a_plain_address_is_refused(bad):
    """The host lands inside `CREATE USER 'u'@'<here>'`. Validated rather than escaped,
    the same rule the names follow."""
    with pytest.raises(d.DatabaseError):
        d.validate_host(bad)


def test_a_refused_host_never_reaches_the_sql():
    """Belt and braces: the validation is in create_database, so prove nothing crafted can
    arrive at the statement builder through it."""
    import inspect
    src = inspect.getsource(d.create_database)
    assert "validate_host(host)" in src
    assert src.index("validate_host") < src.index("build_create_sql")


# ── Removing one ─────────────────────────────────────────────────────────────

def test_dropping_a_user_uses_the_host_it_was_created_with():
    """In MySQL the host is part of the identity: 'u'@'10.0.0.5' and 'u'@'localhost' are
    two different accounts. Dropping the wrong one fails while looking like it worked."""
    sql = d.build_drop_sql("mysql", "shop", "shopuser", "10.0.0.5")
    assert "DROP USER 'shopuser'@'10.0.0.5';" in sql


def test_dropping_still_defaults_to_this_machine():
    assert "DROP USER 'shopuser'@'localhost';" in d.build_drop_sql("mysql", "shop", "shopuser")


# ── PostgreSQL is honest about doing nothing here ────────────────────────────

def test_postgres_roles_have_no_host_and_the_code_says_so():
    """PostgreSQL decides who may connect in pg_hba.conf, which the database-server
    playbook writes. Inventing a host on the role would be pretending."""
    plain = d.build_create_sql("postgres", "shop", "shopuser", "pw")
    scoped = d.build_create_sql("postgres", "shop", "shopuser", "pw", "10.0.0.5")
    assert plain == scoped
    assert "10.0.0.5" not in scoped
    import inspect
    assert "pg_hba" in inspect.getsource(d.build_create_sql)


# ── The endpoint only accepts the customer's own servers ─────────────────────

class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _Rows(self._rows)


class _Srv:
    def __init__(self, host="", name="x", sid="other"):
        self.host, self.name, self.id = host, name, sid


class _User:
    id = "u1"


@pytest.mark.asyncio
async def test_only_the_customers_own_servers_may_be_allowed():
    """Exercised, not read.

    The first version of this test asserted on the router's SOURCE — and a mutation that
    deleted the actual comparison left both strings it looked for in place, so it passed
    while any address on earth was accepted. Mutation testing caught it; this calls the
    function.
    """
    from fastapi import HTTPException

    from app.routers import databases as router

    db = _FakeDb([_Srv("10.0.0.5", "web1"), _Srv("10.0.0.6", "web2")])
    me, here = _User(), _Srv("10.0.0.1", "dbsrv", "self")

    assert await router._check_reachable(here, "10.0.0.5", me, db) == "10.0.0.5"
    assert await router._check_reachable(here, "", me, db) == "localhost"
    assert await router._check_reachable(here, "localhost", me, db) == "localhost"

    with pytest.raises(HTTPException) as exc:
        await router._check_reachable(here, "203.0.113.9", me, db)
    assert exc.value.status_code == 422
    assert "not one of your servers" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_a_customer_with_no_other_servers_gets_localhost_only():
    from fastapi import HTTPException

    from app.routers import databases as router

    db = _FakeDb([])
    with pytest.raises(HTTPException):
        await router._check_reachable(_Srv(), "10.0.0.5", _User(), db)
    assert await router._check_reachable(_Srv(), "", _User(), db) == "localhost"


def test_the_endpoint_runs_the_check_before_creating_anything():
    import inspect

    from app.routers import databases as router
    create = inspect.getsource(router.create_database)
    assert create.index("_check_reachable") < create.index("dbs.create_database")
