"""The databases on a Linux server — what exists, and adding or removing one.

A site installer creates a database and then it disappears from view: the customer cannot
see it, add a second one, or find out which user owns it. Their data lives there and the
product has never shown it to them.

Three rules shape everything here.

**Identifiers are validated, not escaped.** A database or user name reaches a SQL
statement, and quoting it correctly for MySQL *and* PostgreSQL — each with its own
escape rules and its own identifier quoting — is harder to get right than refusing
anything that is not a plain name. The legitimate set is small (letters, digits and
underscores), so anything else is an error the customer can read rather than a string we
try to make safe.

**A password never reaches the process list.** `CREATE USER ... IDENTIFIED BY '...'`
puts the password in the statement itself, and a command sent over SSH is run as
``bash -c '...'`` — so anything inside it shows up in ``ps`` for every user on that
server, and in root's shell history. The statements are therefore uploaded over SFTP to
a file only their owner can read, and the command carries nothing but the path. The
first version of this module got that wrong, writing the statements into the command via
a heredoc; it looked careful and published the password to exactly the people the
password exists to keep out.

**A system database is never a target.** Dropping `mysql` or `template1` does not lose a
website, it breaks the whole server, and the names are close enough to a real one that a
mis-click is plausible. That is a refusal, not a warning.
"""
from __future__ import annotations

import logging
import re
import secrets
import shlex

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_SENTINEL = "___SM_DB___"

# Letters, digits and underscores, starting with a letter or underscore. This is the
# intersection of what MySQL and PostgreSQL accept unquoted, which is what lets the same
# validated name be dropped into either one's syntax without escaping.
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,62}$")

# Deleting one of these does not lose a website — it breaks the server.
_MYSQL_SYSTEM = frozenset({"mysql", "information_schema", "performance_schema", "sys"})
_POSTGRES_SYSTEM = frozenset({"postgres", "template0", "template1"})

# Accounts that must never be dropped. `root` and `postgres` are how anything — including
# this product — administers the server; removing one is not a lost website, it is a
# database server nobody can get into again, with no way back from this screen. The
# `mariadb.*` names are not a duplicate of the `mysql.*` ones: MariaDB's internal account
# is `mariadb.sys`, which a list written against MySQL does not cover, and a real MariaDB
# server is what showed that. `PUBLIC` is a pseudo-role MariaDB reports as a user.
_PROTECTED_USERS = frozenset({
    "root", "postgres", "public",
    "mysql.sys", "mysql.session", "mysql.infoschema", "mariadb.sys",
    "debian-sys-maint",
})

ENGINES = ("mysql", "postgres")

# Long enough that a database reachable from the internet is not guessable. Short
# passwords are the reason a fresh install gets found by a scanner within the hour.
_MIN_PASSWORD = 12


class DatabaseError(Exception):
    """Something the customer can read and act on."""


def validate_name(name: str, *, what: str = "name") -> str:
    """Refuse anything that is not a plain identifier, with a message that says why."""
    name = (name or "").strip()
    if not name:
        raise DatabaseError(f"Enter a {what}.")
    if not _NAME.match(name):
        raise DatabaseError(
            f"'{name}' cannot be used as a {what}. Use letters, numbers and underscores "
            f"only, starting with a letter — for example my_shop."
        )
    return name


LOCAL_ONLY = "localhost"


def validate_host(host: str) -> str:
    """Which machine a database user may sign in from.

    The default is this machine only, which is what every database created before this
    existed used, and what a site on the same server needs.

    A dedicated database server is the other case: the application is on a different
    machine, so the user has to be allowed from that machine's address — the firewall
    lets the packet through, and then MySQL refuses it unless the user says so too.

    **`%` — meaning "from anywhere" — is refused.** It is one character away from the
    correct answer and it is how a database ends up open to the internet; a panel that
    quietly uses it is trading the customer's safety for one less question. A hostname is
    refused too: MySQL resolves it by reverse DNS at connection time, which is slow and
    fails in ways nobody can debug from this screen.
    """
    host = (host or "").strip()
    if not host or host == LOCAL_ONLY:
        return LOCAL_ONLY
    if host in ("%", "0.0.0.0") or "%" in host or "_" in host:
        raise DatabaseError(
            "A database user cannot be allowed from anywhere. Give the address of the "
            "server that will connect, or leave it as this machine only.")
    if not re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        raise DatabaseError(
            f"“{host}” is not an IP address. Give the address of the server that will "
            f"connect to this database.")
    for part in host.split("."):
        if int(part) > 255:
            raise DatabaseError(f"“{host}” is not a valid IP address.")
    return host



def check_not_system(name: str, engine: str) -> None:
    """A system database is never a valid target for creation or deletion."""
    system = _MYSQL_SYSTEM if engine == "mysql" else _POSTGRES_SYSTEM
    if name.lower() in system:
        raise DatabaseError(
            f"'{name}' is one of the database server's own databases. Changing it would "
            f"break {'MySQL' if engine == 'mysql' else 'PostgreSQL'} itself, so it is not "
            f"something this screen will touch."
        )


def check_user_removable(name: str) -> None:
    """Refuse to delete an account the server itself depends on.

    The screen only ever offers users that are already filtered out of this set, so this
    guards the API rather than the button — but the cost of getting it wrong is a database
    server that nobody, including this product, can sign in to again. There is no recovery
    from that anywhere in this system, which makes it a refusal rather than a warning.
    """
    if name.lower() in _PROTECTED_USERS:
        raise DatabaseError(
            f"'{name}' is the account used to administer this database server. Deleting "
            f"it would lock everyone out, including ServerAlly, so it is not something "
            f"this screen will remove."
        )


def validate_password(password: str) -> str:
    """A password we are about to set has to be worth setting."""
    if not password:
        raise DatabaseError("Enter a password for the database user.")
    if len(password) < _MIN_PASSWORD:
        raise DatabaseError(
            f"That password is too short. Use at least {_MIN_PASSWORD} characters — a "
            f"database user is often reachable from the internet."
        )
    return password


# --- Reading -------------------------------------------------------------------------

def build_discovery_command() -> str:
    """One round trip: which engines are installed, and what is in them.

    Read-only by construction — every statement is a SHOW or a SELECT written here, never
    assembled from anything the customer typed. Each line is tagged so a missing engine
    simply produces no lines instead of an error to interpret.

    Reached as the local superuser over the unix socket, which is how both engines are
    configured on a normal server. If that is not available the engine reports itself as
    present but unreadable, which is a different and more useful answer than "no databases".
    """
    my_sys = ",".join(f"'{n}'" for n in sorted(_MYSQL_SYSTEM))
    pg_sys = ",".join(f"'{n}'" for n in sorted(_POSTGRES_SYSTEM))

    mysql = (
        'if command -v mysql >/dev/null 2>&1; then '
        f'echo "{_SENTINEL}|engine|mysql|$(mysqld --version 2>/dev/null | head -1 | '
        'grep -oE "[0-9]+\\.[0-9]+\\.[0-9]+" | head -1)"; '
        'if mysql -N -B -e "SELECT 1" >/dev/null 2>&1; then '
        # Size comes from information_schema in the same query — a second round trip per
        # database would make a server with thirty of them noticeably slow.
        'mysql -N -B -e "'
        'SELECT s.schema_name, COALESCE(ROUND(SUM(t.data_length+t.index_length)/1048576,1),0), '
        'COALESCE(COUNT(t.table_name),0) '
        'FROM information_schema.schemata s '
        'LEFT JOIN information_schema.tables t ON t.table_schema = s.schema_name '
        f'WHERE s.schema_name NOT IN ({my_sys}) '
        'GROUP BY s.schema_name ORDER BY s.schema_name" 2>/dev/null | '
        f'while IFS=$\'\\t\' read -r n mb tbl; do echo "{_SENTINEL}|db|mysql|$n|$mb|$tbl"; done; '
        # Three exclusions, each learned from a real server rather than assumed:
        #   - `mysql.%` / `mariadb.%` are the server's own internal accounts. MariaDB's is
        #     `mariadb.sys`, which a list written for MySQL misses entirely.
        #   - `PUBLIC` is a pseudo-role MariaDB reports here; it is not a login.
        #   - CURRENT_USER is the account WE are connected as. Offering it for deletion
        #     offers to lock us out of the database server for good.
        'mysql -N -B -e "SELECT DISTINCT user, host FROM mysql.user '
        'WHERE user NOT IN (\'root\',\'PUBLIC\',\'debian-sys-maint\') '
        'AND user NOT LIKE \'mysql.%\' AND user NOT LIKE \'mariadb.%\' '
        'AND user <> SUBSTRING_INDEX(CURRENT_USER(), \'@\', 1) '
        'AND user <> \'\' ORDER BY user" 2>/dev/null | '
        f'while IFS=$\'\\t\' read -r u h; do echo "{_SENTINEL}|user|mysql|$u|$h"; done; '
        f'else echo "{_SENTINEL}|locked|mysql"; fi; fi'
    )

    postgres = (
        'if command -v psql >/dev/null 2>&1; then '
        f'echo "{_SENTINEL}|engine|postgres|$(psql --version 2>/dev/null | '
        'grep -oE "[0-9]+\\.[0-9]+" | head -1)"; '
        'if su - postgres -c "psql -tAc \'SELECT 1\'" >/dev/null 2>&1; then '
        'su - postgres -c "psql -tAF\'|\' -c \\"'
        'SELECT datname, ROUND(pg_database_size(datname)/1048576.0,1) FROM pg_database '
        f'WHERE datname NOT IN ({pg_sys}) AND NOT datistemplate ORDER BY datname\\"" 2>/dev/null | '
        f'while IFS="|" read -r n mb; do [ -n "$n" ] && echo "{_SENTINEL}|db|postgres|$n|$mb|"; done; '
        'su - postgres -c "psql -tAc \\"SELECT rolname FROM pg_roles '
        'WHERE rolcanlogin AND rolname NOT LIKE \'pg_%\' AND rolname <> \'postgres\' '
        'ORDER BY rolname\\"" 2>/dev/null | '
        f'while read -r u; do [ -n "$u" ] && echo "{_SENTINEL}|user|postgres|$u|"; done; '
        f'else echo "{_SENTINEL}|locked|postgres"; fi; fi'
    )

    return f"{mysql}; {postgres}; true"


def parse_discovery(stdout: str) -> dict:
    """Turn the sentinel lines into engines, each with its databases and users."""
    engines: dict[str, dict] = {}

    def engine(name: str) -> dict:
        return engines.setdefault(name, {
            "engine": name,
            "label": "MySQL / MariaDB" if name == "mysql" else "PostgreSQL",
            "version": None,
            "readable": True,
            "databases": [],
            "users": [],
        })

    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_SENTINEL):
            continue
        parts = line.split("|")
        if len(parts) < 3:
            continue
        kind, name = parts[1], parts[2]

        if kind == "engine":
            e = engine(name)
            e["version"] = (parts[3].strip() or None) if len(parts) > 3 else None
        elif kind == "locked":
            # Installed, but we could not authenticate. Saying "no databases" here would
            # be a lie that invites someone to create one that already exists.
            engine(name)["readable"] = False
        elif kind == "db" and len(parts) >= 5:
            e = engine(name)
            e["databases"].append({
                "name": parts[3],
                "size_mb": _as_float(parts[4]),
                "tables": _as_int(parts[5]) if len(parts) > 5 else None,
            })
        elif kind == "user" and len(parts) >= 4:
            e = engine(name)
            host = parts[4].strip() if len(parts) > 4 else ""
            e["users"].append({"name": parts[3], "host": host or "localhost"})

    return {"engines": [engines[k] for k in sorted(engines)]}


def _as_float(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _as_int(value: str) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def list_databases(server: Server) -> dict:
    """What database engines are on this server, and what is in them.

    Never raises: a server that cannot be reached returns no engines, which the screen
    shows as "we could not look" rather than as an empty server.
    """
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_discovery_command())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Database discovery failed for %s: %s", server.id, exc)
        return {"engines": [], "reachable": False}
    result = parse_discovery(stdout)
    result["reachable"] = True
    return result


# --- Writing -------------------------------------------------------------------------

def _quote_password(engine: str, password: str) -> str:
    """Put a password into a SQL string literal so it survives exactly as typed.

    The two engines differ, and getting this wrong is silent: the user is created, and
    then the password does not work. Nothing errors — the customer's application simply
    cannot connect, and the obvious suspect is their application.

    MySQL and MariaDB treat a backslash inside a string literal as an escape character,
    so ``pa\\ssword`` is stored as ``password``. Both halves have to be escaped there.
    PostgreSQL, with standard_conforming_strings on, treats a backslash literally — so
    doubling it would break the password in the opposite direction. That setting is a
    runtime option rather than a guarantee, so the statements set it themselves rather
    than hoping.

    A real MariaDB is what showed this: the quote cases all passed and the backslash case
    created the user, reported success, and then refused the password.
    """
    if engine == "mysql":
        return password.replace("\\", "\\\\").replace("'", "''")
    return password.replace("'", "''")


def build_create_sql(engine: str, db_name: str, user: str, password: str,
                     host: str = LOCAL_ONLY) -> str:
    """The statements that create one database and a user with rights to only that one.

    Every identifier here has already been through :func:`validate_name`, so it contains
    nothing that needs escaping. The password is the one genuinely arbitrary value, and it
    goes through :func:`_quote_password`.

    Rights are granted on this database alone. A user with server-wide rights is how one
    compromised website reaches every other database on the machine.
    """
    pw = _quote_password(engine, password)
    if engine == "mysql":
        return "\n".join([
            f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;",
            f"CREATE USER '{user}'@'{host}' IDENTIFIED BY '{pw}';",
            f"GRANT ALL PRIVILEGES ON `{db_name}`.* TO '{user}'@'{host}';",
            "FLUSH PRIVILEGES;",
        ])
    # PostgreSQL has no host on the role itself — which machines may connect is decided
    # entirely by pg_hba.conf, written by the database-server playbook for each address it
    # was told to allow. So `host` genuinely changes nothing here, and pretending otherwise
    # would be worse than saying so.
    return "\n".join([
        # Set rather than assumed: with this off, a backslash in the password would be
        # read as an escape and the stored password would not be the one that was typed.
        "SET standard_conforming_strings = on;",
        f"CREATE ROLE \"{user}\" LOGIN PASSWORD '{pw}';",
        f'CREATE DATABASE "{db_name}" OWNER "{user}" ENCODING \'UTF8\';',
        f'GRANT ALL PRIVILEGES ON DATABASE "{db_name}" TO "{user}";',
    ])


def build_run_sql_command(engine: str, path: str) -> str:
    """Run the statements already uploaded to ``path``.

    The command carries the PATH and nothing else. This is the whole reason the file is
    uploaded separately: a command is executed by the remote shell as ``bash -c '...'``,
    so anything inside it is visible in ``ps`` to every user on that server — and lands
    in root's shell history besides. Writing the statements into the command, even via a
    heredoc, would publish the password to exactly the people it is meant to keep out.

    The file is removed here as well as by the caller, so it does not survive a lost
    connection between the command finishing and the cleanup running.
    """
    quoted = shlex.quote(path)
    if engine == "mysql":
        run = f"mysql < {quoted}"
    else:
        # psql runs as the postgres account, which needs to read the file for the moment
        # it is used. It stays mode 600 and is removed immediately afterwards.
        run = (f"chown postgres {quoted} 2>/dev/null; "
               f"su - postgres -c 'psql -v ON_ERROR_STOP=1 -f {quoted}'")
    return f"{run}; _rc=$?; rm -f {quoted}; exit $_rc"


def _sql_path() -> str:
    """An unguessable path for one set of statements.

    Random because the file is created in a world-writable directory: a fixed name could
    be pre-created as a symlink by another user on the server, pointing our write at a
    file of their choosing. It is opened exclusively as well, so a pre-existing path is
    an error rather than something we follow.
    """
    return f"/tmp/.serverally-{secrets.token_hex(12)}.sql"


async def _run_sql(server: Server, engine: str, sql: str) -> tuple[str, str, int]:
    """Upload the statements over SFTP, run them, and remove them.

    Permissions are set while the file is still empty, so there is no moment at which the
    password exists in a readable file.
    """
    from app.services import file_service

    path = _sql_path()
    await file_service.write_private(server, path, sql)
    try:
        return await connection_manager.execute(
            server, build_run_sql_command(engine, path))
    finally:
        # The command removes it too; this covers the case where the command never ran.
        try:
            await file_service.delete_path(server, path)
        except Exception:  # noqa: BLE001 — best effort, the command already removed it
            pass


def build_drop_sql(engine: str, db_name: str, drop_user: str | None,
                   host: str = LOCAL_ONLY) -> str:
    """Remove a database, and optionally the user that owned it."""
    if engine == "mysql":
        lines = [f"DROP DATABASE `{db_name}`;"]
        if drop_user:
            # The host is part of the identity: a user created for another machine is a
            # DIFFERENT account from the same name on localhost, and dropping the wrong
            # one fails while looking like it worked.
            lines.append(f"DROP USER '{drop_user}'@'{host}';")
        lines.append("FLUSH PRIVILEGES;")
        return "\n".join(lines)
    lines = [f'DROP DATABASE "{db_name}";']
    if drop_user:
        lines.append(f'DROP ROLE "{drop_user}";')
    return "\n".join(lines)


def _friendly(engine: str, output: str) -> str:
    """Turn the database server's own error into something worth reading.

    A raw driver error tells an owner nothing they can act on, and these four are almost
    all of what actually goes wrong.
    """
    low = (output or "").lower()
    if "access denied" in low or "peer authentication" in low or "role \"postgres\"" in low:
        return ("We could not sign in to the database server on this machine. It is "
                "installed, but not reachable with the usual administrator access.")
    if "database exists" in low or "already exists" in low:
        return "Something with that name already exists on this server. Choose another name."
    if "command not found" in low:
        engine_name = "MySQL or MariaDB" if engine == "mysql" else "PostgreSQL"
        return f"{engine_name} is not installed on this server."
    detail = (output or "").strip().splitlines()
    return detail[-1][:300] if detail else "The database server rejected the change."


async def create_database(server: Server, *, engine: str, db_name: str,
                          user: str, password: str, host: str = LOCAL_ONLY) -> dict:
    """Create one database and a user with rights to it alone."""
    if engine not in ENGINES:
        raise DatabaseError("Choose MySQL/MariaDB or PostgreSQL.")
    db_name = validate_name(db_name, what="database name")
    user = validate_name(user, what="user name")
    validate_password(password)
    check_not_system(db_name, engine)
    check_not_system(user, engine)
    host = validate_host(host)

    sql = build_create_sql(engine, db_name, user, password, host)
    stdout, stderr, code = await _run_sql(server, engine, sql)
    if code != 0:
        raise DatabaseError(_friendly(engine, stderr or stdout))
    # The password is deliberately not returned and not stored: the customer typed it,
    # and it is not this screen's job to keep a second copy of it anywhere.
    return {"engine": engine, "name": db_name, "user": user, "host": host}


async def drop_database(server: Server, *, engine: str, db_name: str,
                        confirm_name: str, drop_user: str | None = None,
                        host: str = LOCAL_ONLY) -> dict:
    """Delete a database. There is no undo anywhere in this system.

    The typed name has to match, because the loss here is rarely "I meant not to" — it is
    "I deleted the one next to it". Comparing against what the customer typed is what
    makes that mistake impossible rather than merely discouraged.
    """
    if engine not in ENGINES:
        raise DatabaseError("Choose MySQL/MariaDB or PostgreSQL.")
    db_name = validate_name(db_name, what="database name")
    check_not_system(db_name, engine)
    if (confirm_name or "").strip() != db_name:
        raise DatabaseError(
            f"Type the database name exactly — '{db_name}' — to confirm. Deleting a "
            f"database cannot be undone, and there is no copy of it here."
        )
    if drop_user:
        drop_user = validate_name(drop_user, what="user name")
        check_not_system(drop_user, engine)
        check_user_removable(drop_user)

    sql = build_drop_sql(engine, db_name, drop_user, validate_host(host))
    stdout, stderr, code = await _run_sql(server, engine, sql)
    if code != 0:
        raise DatabaseError(_friendly(engine, stderr or stdout))
    return {"engine": engine, "name": db_name, "dropped_user": drop_user}
