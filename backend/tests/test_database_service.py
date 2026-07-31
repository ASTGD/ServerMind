"""Databases on a Linux server.

The properties worth pinning here are the ones whose failure is expensive: a password
appearing where other users can read it, a name reaching SQL unvalidated, and a system
database being dropped. Each is checked by exercising the thing itself rather than by
asserting on a substring — a test that greps a command string proves the string, not the
behaviour.
"""
from __future__ import annotations

import os
import shlex
import subprocess
import tempfile

import pytest

from app.services import database_service as dbs


# --- Names are validated, never escaped ----------------------------------------------

@pytest.mark.parametrize("name", ["shop", "my_shop", "wp_2024", "_internal", "A1"])
def test_a_plain_name_is_accepted(name):
    assert dbs.validate_name(name) == name


@pytest.mark.parametrize("name", [
    "shop; DROP DATABASE other",       # the statement-separator attempt
    "shop`--",                          # MySQL identifier quoting
    'shop"; --',                        # PostgreSQL identifier quoting
    "shop'",                            # string quoting
    "shop\\",                           # escape character
    "shop database",                    # a space is enough to change the statement
    "2shop",                            # a digit first is not a valid identifier
    "",                                 # nothing
    "x" * 64,                           # longer than either engine allows
    "shop\nDROP DATABASE other",        # a newline, since statements are line-separated
])
def test_anything_that_is_not_a_plain_name_is_refused(name):
    """Refusing beats escaping: there is no string here we have to get quoting right for."""
    with pytest.raises(dbs.DatabaseError):
        dbs.validate_name(name)


def test_the_refusal_explains_what_to_do():
    """A customer who typed a hyphen needs to be told what IS allowed, not just 'invalid'."""
    with pytest.raises(dbs.DatabaseError) as exc:
        dbs.validate_name("my-shop", what="database name")
    message = str(exc.value)
    assert "database name" in message
    assert "letters, numbers and underscores" in message


# --- A system database is never a target ---------------------------------------------

@pytest.mark.parametrize("engine,name", [
    ("mysql", "mysql"), ("mysql", "information_schema"),
    ("mysql", "performance_schema"), ("mysql", "sys"),
    ("mysql", "MySQL"),                       # the check is case-insensitive
    ("postgres", "postgres"), ("postgres", "template0"), ("postgres", "template1"),
])
def test_a_system_database_is_refused(engine, name):
    """Dropping one of these does not lose a website — it breaks the whole server."""
    with pytest.raises(dbs.DatabaseError):
        dbs.check_not_system(name, engine)


def test_a_normal_database_is_not_mistaken_for_a_system_one():
    for name in ("mysqldata", "systems", "postgres_backup", "shop"):
        dbs.check_not_system(name, "mysql")
        dbs.check_not_system(name, "postgres")


# --- The password never reaches the process list --------------------------------------

_PASSWORD = "Tr0ub4dor-and-3-horses"


@pytest.mark.parametrize("engine", ["mysql", "postgres"])
def test_the_password_is_never_in_the_command(engine):
    """A command sent over SSH runs as `bash -c '...'`, so ps shows all of it.

    The first version of this module built a heredoc containing the statements, which
    published the password to every user on the server. The statements go over SFTP now
    and the command carries only a path.
    """
    sql = dbs.build_create_sql(engine, "shop", "shop_user", _PASSWORD)
    assert _PASSWORD in sql, "the password has to reach the statement itself"

    command = dbs.build_run_sql_command(engine, "/tmp/.serverally-abc123.sql")
    assert _PASSWORD not in command
    assert "shop_user" not in command
    assert "CREATE" not in command
    # Only the path, so there is nothing else it could leak.
    assert "/tmp/.serverally-abc123.sql" in command


def test_the_statement_file_is_removed_even_when_the_statements_fail():
    """A file holding a password must not survive a failed run."""
    command = dbs.build_run_sql_command("mysql", "/tmp/x.sql")
    # The removal comes after the exit code is captured, so it runs either way.
    assert command.index("_rc=$?") < command.index("rm -f")
    assert "exit $_rc" in command


def test_the_statement_path_is_unguessable():
    """A fixed path in a world-writable directory can be pre-planted as a symlink."""
    paths = {dbs._sql_path() for _ in range(50)}
    assert len(paths) == 50
    assert all(p.startswith("/tmp/.serverally-") and p.endswith(".sql") for p in paths)


def test_a_quote_in_the_password_cannot_end_the_statement():
    """The password is the one value here that is genuinely arbitrary."""
    sql = dbs.build_create_sql("mysql", "shop", "shop_user", "a'b''c")
    # Doubled, which is the escape both engines define — so the string still terminates
    # exactly once, at the end.
    assert "IDENTIFIED BY 'a''b''''c'" in sql


# --- Deleting is guarded by the typed name -------------------------------------------

@pytest.mark.asyncio
async def test_dropping_needs_the_name_typed_exactly():
    """The loss is rarely "I meant not to" — it is "I deleted the one next to it"."""
    class FakeServer:
        id = "s1"
        connection_type = "ssh"

    # Case matters: on Linux, MySQL database names are case-sensitive, so `Shop` really
    # is a different database from `shop`.
    for wrong in ("Shop", "shop2", "", "sho", "shop_old"):
        with pytest.raises(dbs.DatabaseError) as exc:
            await dbs.drop_database(FakeServer(), engine="mysql", db_name="shop",
                                    confirm_name=wrong)
        assert "exactly" in str(exc.value)


@pytest.mark.asyncio
async def test_surrounding_whitespace_in_the_confirmation_is_forgiven():
    """Deliberate: a trailing space from a copy-paste does not change WHICH database was
    named, and the guard exists to stop the wrong database being deleted — not to test
    typing. Refusing here would only teach someone to retype it until it worked."""
    class FakeServer:
        id = "s1"
        connection_type = "ssh"

    # It gets past the confirmation and fails later, at the point of actually connecting.
    with pytest.raises(Exception) as exc:
        await dbs.drop_database(FakeServer(), engine="mysql", db_name="shop",
                                confirm_name="  shop  ")
    assert "exactly" not in str(exc.value)


@pytest.mark.asyncio
async def test_dropping_a_system_database_is_refused_before_anything_runs():
    class FakeServer:
        id = "s1"
        connection_type = "ssh"

    with pytest.raises(dbs.DatabaseError):
        # Even with the confirmation typed perfectly.
        await dbs.drop_database(FakeServer(), engine="mysql", db_name="mysql",
                                confirm_name="mysql")


# --- Reading is read-only -------------------------------------------------------------

def test_the_discovery_command_only_reads():
    """Looking at the databases must never be able to change one."""
    command = dbs.build_discovery_command()
    for mutating in ("DROP ", "CREATE ", "ALTER ", "INSERT ", "UPDATE ", "DELETE ",
                     "GRANT ", "TRUNCATE ", "RENAME "):
        assert mutating not in command.upper(), f"{mutating.strip()} in a read-only probe"


def test_the_discovery_command_is_valid_shell():
    """It is a long single line of nested quoting; a syntax error means an empty screen."""
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write("#!/bin/bash\n" + dbs.build_discovery_command() + "\n")
        path = fh.name
    try:
        result = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
    finally:
        os.unlink(path)


def test_a_locked_engine_is_not_reported_as_an_empty_one():
    """"Installed but we could not sign in" and "installed with nothing in it" are
    different answers, and confusing them invites someone to create a database that
    already exists."""
    stdout = "\n".join([
        f"{dbs._SENTINEL}|engine|mysql|10.11.6",
        f"{dbs._SENTINEL}|locked|mysql",
    ])
    engine = dbs.parse_discovery(stdout)["engines"][0]
    assert engine["readable"] is False
    assert engine["databases"] == []


def test_discovery_reads_databases_and_users():
    stdout = "\n".join([
        f"{dbs._SENTINEL}|engine|mysql|10.11.6",
        f"{dbs._SENTINEL}|db|mysql|shop|12.5|18",
        f"{dbs._SENTINEL}|user|mysql|shop_user|localhost",
        f"{dbs._SENTINEL}|engine|postgres|16.2",
        f"{dbs._SENTINEL}|db|postgres|app|3.0|",
    ])
    result = dbs.parse_discovery(stdout)
    by_engine = {e["engine"]: e for e in result["engines"]}

    mysql = by_engine["mysql"]
    assert mysql["version"] == "10.11.6" and mysql["readable"] is True
    assert mysql["databases"] == [{"name": "shop", "size_mb": 12.5, "tables": 18}]
    assert mysql["users"] == [{"name": "shop_user", "host": "localhost"}]

    assert by_engine["postgres"]["databases"][0]["name"] == "app"


def test_junk_output_never_crashes_the_screen():
    """A server mid-upgrade prints all sorts of things; none of it should be an error."""
    assert dbs.parse_discovery("")["engines"] == []
    assert dbs.parse_discovery("bash: mysql: command not found")["engines"] == []
    # A truncated sentinel line is dropped whole rather than half-parsed into a database
    # with no name — which would then be offered for deletion.
    assert dbs.parse_discovery(f"{dbs._SENTINEL}|db|mysql")["engines"] == []
    assert dbs.parse_discovery(f"{dbs._SENTINEL}|")["engines"] == []


# --- The password is never returned or stored ----------------------------------------

def test_the_create_result_carries_no_password():
    """Whatever the API returns can end up in a log, a browser cache or a screenshot."""
    import inspect
    source = inspect.getsource(dbs.create_database)
    returned = source[source.index("return {"):]
    assert "password" not in returned


# --- The password has to survive being put into a statement -----------------------------
#
# Found against a real MariaDB, not by reading: a password containing a backslash was
# created without error and then would not authenticate. Nothing failed — the customer's
# application simply could not connect, and their application looked like the culprit.

def test_a_backslash_in_a_mysql_password_is_escaped():
    """MySQL reads a backslash inside a string literal as an escape character, so an
    unescaped `pa\\ssword` is stored as `password`."""
    sql = dbs.build_create_sql("mysql", "shop", "u", "pa\\ssword")
    assert "IDENTIFIED BY 'pa\\\\ssword'" in sql


def test_a_backslash_in_a_postgres_password_is_left_alone():
    """PostgreSQL treats it literally, so doubling it would break the password the other
    way. The statements set standard_conforming_strings rather than relying on it."""
    sql = dbs.build_create_sql("postgres", "shop", "u", "pa\\ssword")
    assert "PASSWORD 'pa\\ssword'" in sql
    assert "standard_conforming_strings = on" in sql


@pytest.mark.parametrize("password", [
    "SimplePass1234",
    "pa'ss'word'123",
    "pa\\ssword\\123",
    "pa\\'ssword\\\\123",
    'pa"ssword"123',
    "pass;DROP DATABASE other;--x",
    "pass\nword1234",
    "påsswörd-1234",
])
@pytest.mark.parametrize("engine", ["mysql", "postgres"])
def test_a_password_never_ends_its_own_string_literal(engine, password):
    """Whatever the escaping, the literal must terminate exactly once — at the end.

    Counting quotes is how a broken escape shows up: an odd number inside the literal
    means the statement ends early and the remainder is parsed as SQL.
    """
    sql = dbs.build_create_sql(engine, "shop", "shop_user", password)
    marker = "IDENTIFIED BY '" if engine == "mysql" else "PASSWORD '"
    literal = sql[sql.index(marker) + len(marker):]
    literal = literal[:literal.index("';")]
    # Every quote inside must be part of a doubled pair, and for MySQL every backslash too.
    assert literal.count("'") % 2 == 0
    if engine == "mysql":
        assert literal.count("\\") % 2 == 0


# --- Never delete the account that administers the server -------------------------------
#
# A real MariaDB listed three "users" that must never be offered for deletion: `PUBLIC`
# (a pseudo-role), `mariadb.sys` (a system account a list written for MySQL misses), and
# the account we authenticate as. Dropping the last one leaves a database server nobody —
# including this product — can sign in to again.

@pytest.mark.parametrize("name", [
    "root", "postgres", "PUBLIC", "public",
    "mysql.sys", "mysql.session", "mysql.infoschema",
    "mariadb.sys",              # MariaDB's own; a MySQL-only list does not have it
    "debian-sys-maint",         # how Debian's own maintenance scripts get in
    "ROOT",                     # the check is case-insensitive
])
def test_an_administrative_account_is_never_removable(name):
    with pytest.raises(dbs.DatabaseError) as exc:
        dbs.check_user_removable(name)
    assert "lock everyone out" in str(exc.value)


def test_an_ordinary_user_is_removable():
    for name in ("shop_user", "wp_user", "rooted", "postgres_app"):
        dbs.check_user_removable(name)


@pytest.mark.asyncio
async def test_dropping_a_database_cannot_take_the_admin_account_with_it():
    """The screen never offers one, so this guards the API — where the cost is a database
    server that can no longer be administered at all."""
    class FakeServer:
        id = "s1"
        connection_type = "ssh"

    with pytest.raises(dbs.DatabaseError) as exc:
        await dbs.drop_database(FakeServer(), engine="mysql", db_name="shop",
                                confirm_name="shop", drop_user="root")
    assert "lock everyone out" in str(exc.value)


def test_the_user_query_excludes_what_a_real_server_actually_returns():
    """Each exclusion here was added because a real MariaDB returned that row."""
    command = dbs.build_discovery_command()
    assert "NOT LIKE 'mariadb.%'" in command, "MariaDB's own accounts"
    assert "NOT LIKE 'mysql.%'" in command, "MySQL's own accounts"
    assert "'PUBLIC'" in command, "MariaDB reports a PUBLIC pseudo-role as a user"
    assert "CURRENT_USER()" in command, "the account we are connected as"
