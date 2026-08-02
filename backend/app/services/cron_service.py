"""The server's own scheduled jobs — its crontab.

This is deliberately not the same thing as ServerAlly's scheduled tasks. Those run from
here, over SSH, and we keep their history. A crontab entry runs on the server itself,
whether or not this product is up — which is what Laravel's scheduler and WordPress's
cron actually need, and what every other tool that has touched this server has been
writing into. Today all of that is invisible.

Two rules carry the feature.

**Never lose an entry we did not write.** A crontab is a shared file. Installers write to
it, and so do people over SSH. Editing means reading the whole file and writing it back,
so a change made in between would be silently destroyed — and the thing destroyed is
somebody's backup job, which nobody notices until they need it. Every write therefore
carries a fingerprint of the file it was based on, and is refused if the file moved on.

**A schedule is validated by a real parser, not a regex.** A wrong expression either
never runs or runs every minute forever, and both look identical in a listing. The parser
that APScheduler already uses answers this properly, so it is what decides.
"""
from __future__ import annotations

import hashlib
import logging
import re
import shlex

from app.models.server import Server
from app.services import connection_manager, safety_service

logger = logging.getLogger(__name__)

_SENTINEL = "___SM_CRON___"

# A crontab line we wrote carries this, so the UI can tell the customer's own jobs from
# whatever was already on the server. It is a comment, so cron ignores it entirely.
_TAG = "# ServerAlly"

# A username, as the system defines one. Refused rather than escaped, for the same reason
# as everywhere else here: the legitimate set is small.
_USER = re.compile(r"^[a-z_][a-z0-9_-]{0,31}\$?$")

_MAX_COMMAND = 500


class CronError(Exception):
    """Something the customer can read and act on."""


# --- Schedules -------------------------------------------------------------------------

_PRESETS: dict[str, str] = {
    "* * * * *": "Every minute",
    "*/5 * * * *": "Every 5 minutes",
    "*/10 * * * *": "Every 10 minutes",
    "*/15 * * * *": "Every 15 minutes",
    "*/30 * * * *": "Every 30 minutes",
    "0 * * * *": "Every hour",
    "0 0 * * *": "Every day at midnight",
    "0 2 * * *": "Every day at 2:00 am",
    "0 3 * * *": "Every day at 3:00 am",
    "0 4 * * 0": "Every Sunday at 4:00 am",
    "0 0 1 * *": "The first day of every month",
    "@reboot": "When the server starts",
    "@daily": "Every day at midnight",
    "@hourly": "Every hour",
    "@weekly": "Every week",
    "@monthly": "Every month",
}

_DAYS = {"0": "Sunday", "1": "Monday", "2": "Tuesday", "3": "Wednesday",
         "4": "Thursday", "5": "Friday", "6": "Saturday", "7": "Sunday"}


def describe(expression: str) -> str:
    """Say what a schedule means, for someone who does not read cron.

    Common shapes get a real sentence. Anything else is shown as-is rather than described
    badly — a wrong description of when a job runs is worse than no description, because
    it will be believed.
    """
    expr = " ".join((expression or "").split())
    if expr in _PRESETS:
        return _PRESETS[expr]

    parts = expr.split()
    if len(parts) != 5:
        return expr
    minute, hour, dom, month, dow = parts

    def at_time() -> str | None:
        if not minute.isdigit() or not hour.isdigit():
            return None
        h, m = int(hour), int(minute)
        if not (0 <= h < 24 and 0 <= m < 60):
            return None
        suffix = "am" if h < 12 else "pm"
        h12 = h % 12 or 12
        return f"{h12}:{m:02d} {suffix}"

    time_of_day = at_time()
    if time_of_day and dom == "*" and month == "*":
        if dow == "*":
            return f"Every day at {time_of_day}"
        if dow in _DAYS:
            return f"Every {_DAYS[dow]} at {time_of_day}"
    if time_of_day and month == "*" and dow == "*" and dom.isdigit():
        return f"Day {int(dom)} of every month at {time_of_day}"
    if (minute.startswith("*/") and minute[2:].isdigit()
            and hour == dom == month == dow == "*"):
        return f"Every {int(minute[2:])} minutes"
    if minute.isdigit() and hour == "*" and dom == month == dow == "*":
        return f"Every hour, at {int(minute)} minutes past"
    return expr


def validate_schedule(expression: str) -> str:
    """Refuse a schedule that would never run, or would run far more than intended."""
    expr = " ".join((expression or "").split())
    if not expr:
        raise CronError("Choose when this should run.")

    if expr.startswith("@"):
        if expr not in {"@reboot", "@yearly", "@annually", "@monthly", "@weekly",
                        "@daily", "@midnight", "@hourly"}:
            raise CronError(
                f"'{expr}' is not a schedule cron understands. Use one of @reboot, "
                f"@hourly, @daily, @weekly, @monthly — or five fields like '0 2 * * *'."
            )
        return expr

    parts = expr.split()
    if len(parts) != 5:
        raise CronError(
            f"A schedule has five parts — minute, hour, day, month, weekday — and this "
            f"has {len(parts)}. For example '0 2 * * *' means every day at 2 am."
        )

    # The parser APScheduler already relies on, rather than a regex of our own: it knows
    # ranges, steps, names and the field bounds, and it is what will actually run this.
    try:
        from apscheduler.triggers.cron import CronTrigger
        CronTrigger.from_crontab(expr)
    except Exception as exc:  # noqa: BLE001 — its message names the offending field
        raise CronError(f"'{expr}' is not a valid schedule: {exc}") from exc
    return expr


def validate_command(command: str, os_family: str = "linux") -> str:
    """A crontab command runs unattended, so it goes through the same safety check as
    anything else — and a refusal matters more here, not less: nobody is watching."""
    command = (command or "").strip()
    if not command:
        raise CronError("Enter the command to run.")
    if len(command) > _MAX_COMMAND:
        raise CronError(f"That command is too long (limit {_MAX_COMMAND} characters).")
    if "\n" in command or "\r" in command:
        raise CronError(
            "A scheduled command has to be a single line — a crontab treats each line as "
            "a separate job."
        )
    verdict = safety_service.validate_command(command, os_family)
    if verdict.status == "blocked":
        raise CronError(
            "That command is refused — it is on the list of things that can destroy a "
            "server, and a scheduled job would run it over and over with nobody watching."
        )
    return command


def validate_user(user: str) -> str:
    user = (user or "").strip()
    if not user:
        raise CronError("Choose which user this job runs as.")
    if not _USER.match(user):
        raise CronError(f"'{user}' is not a valid user name on this server.")
    return user


# --- Reading ---------------------------------------------------------------------------

def build_list_command(users: list[str]) -> str:
    """Read the crontab of each named user in one round trip.

    ``crontab -l`` is a read. It exits non-zero when a user has no crontab at all, which
    is normal rather than an error, so each is allowed to fail quietly.
    """
    parts = []
    for user in users:
        u = shlex.quote(user)
        parts.append(
            f'echo "{_SENTINEL}|user|{user}"; '
            f'crontab -l -u {u} 2>/dev/null | sed "s|^|{_SENTINEL}|line|{user}||" || true'
        )
    return "; ".join(parts) + "; true"


def build_read_command(user: str) -> str:
    """The whole crontab of one user, exactly as it is stored.

    Used before a write, because a change has to be applied to the current file rather
    than to what the screen was showing a minute ago.
    """
    return f"crontab -l -u {shlex.quote(user)} 2>/dev/null || true"


def build_user_list_command() -> str:
    """Which accounts on this server could plausibly own a scheduled job.

    Read-only, from three sources.

    root, plus any account with a real login shell — which is what a site user looks like
    on a panel server, and excludes the several dozen system accounts nobody schedules
    anything as.

    And then every account that ACTUALLY HAS a crontab, whatever its shell or its uid.
    That third source is not a nicety: on a plain Ubuntu server the websites run as
    ``www-data``, which has uid 33 and ``/usr/sbin/nologin``, so the first two rules miss
    it twice over. Its jobs were on the server, running every minute, and invisible here —
    including one added moments earlier through this very screen.
    """
    spools = "/var/spool/cron/crontabs /var/spool/cron"
    return (
        f'echo "{_SENTINEL}|user|root"; '
        "getent passwd 2>/dev/null | "
        "awk -F: '$3 >= 1000 && $3 < 65534 && $7 !~ /(nologin|false|sync)$/ {print $1}' | "
        f'while read -r u; do echo "{_SENTINEL}|user|$u"; done; '
        f'for _d in {spools}; do '
        '  for _f in "$_d"/*; do '
        f'    [ -f "$_f" ] && echo "{_SENTINEL}|user|${{_f##*/}}"; '
        "  done; "
        "done 2>/dev/null; true"
    )


def parse_crontab(text: str) -> list[dict]:
    """Turn a crontab into jobs, keeping the raw line for every one of them.

    The raw line is what makes an edit safe: a removal matches the exact text that was
    read, so it can never take out the line next to it — and a line we cannot parse is
    still listed, because a job we do not understand is still a job the customer has.
    """
    jobs: list[dict] = []
    pending_comment: str | None = None

    for raw in (text or "").splitlines():
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            pending_comment = None
            continue

        if stripped.startswith("#"):
            # Our own marker, or a human's note about the job below it.
            if stripped.startswith(_TAG):
                # The em dash is the one we write in compose_add; without it here the
                # note reads back as "— nightly backup".
                pending_comment = stripped[len(_TAG):].strip(" :-—") or None
            else:
                pending_comment = stripped.lstrip("#").strip() or None
            continue

        # An environment assignment (PATH=..., MAILTO=...) is not a job.
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", stripped):
            pending_comment = None
            continue

        schedule, command = _split_line(stripped)
        if command is None:
            # Not something we recognise; still shown, so nothing is hidden.
            jobs.append({"raw": line, "schedule": "", "command": stripped,
                         "description": "", "note": pending_comment, "parsed": False})
        else:
            jobs.append({"raw": line, "schedule": schedule, "command": command,
                         "description": describe(schedule), "note": pending_comment,
                         "parsed": True})
        pending_comment = None

    return jobs


def _split_line(line: str) -> tuple[str, str | None]:
    """Separate the schedule from the command."""
    if line.startswith("@"):
        parts = line.split(None, 1)
        if len(parts) == 2:
            return parts[0], parts[1]
        return line, None
    parts = line.split(None, 5)
    if len(parts) < 6:
        return "", None
    return " ".join(parts[:5]), parts[5]


def fingerprint(text: str) -> str:
    """Identify the exact contents an edit was based on.

    Compared before a write. If it no longer matches, something else changed the crontab
    since it was read, and writing back would delete that change without saying so.
    """
    return hashlib.sha256((text or "").encode("utf-8", "replace")).hexdigest()[:16]


async def list_jobs(server: Server) -> dict:
    """Every scheduled job on this server, grouped by the account that owns it."""
    try:
        users_out, _e, _c = await connection_manager.execute(
            server, build_user_list_command())
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cron user discovery failed for %s: %s", server.id, exc)
        return {"users": [], "reachable": False}

    users, seen = [], set()
    for line in (users_out or "").splitlines():
        if line.strip().startswith(f"{_SENTINEL}|user|"):
            name = line.strip().split("|", 2)[2].strip()
            if name and name not in seen and _USER.match(name):
                seen.add(name)
                users.append(name)

    out = []
    for user in users[:20]:  # a server with hundreds of accounts is not a cron screen
        try:
            text, _e, _c = await connection_manager.execute(
                server, build_read_command(user))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not read crontab for %s: %s", user, exc)
            continue
        jobs = parse_crontab(text)
        # An account with nothing scheduled is only worth showing if someone might add
        # one there, which is true of root and of the account a site runs as.
        if jobs or user == "root":
            out.append({"user": user, "jobs": jobs, "fingerprint": fingerprint(text)})

    return {"users": out, "reachable": True}


# --- Writing ---------------------------------------------------------------------------

def build_write_command(user: str, path: str) -> str:
    """Install a crontab from an uploaded file, then remove the file."""
    u, p = shlex.quote(user), shlex.quote(path)
    return f"crontab -u {u} {p}; _rc=$?; rm -f {p}; exit $_rc"


def compose_add(current: str, schedule: str, command: str, note: str = "") -> str:
    """The new crontab, with one job appended.

    Appended rather than merged anywhere clever: the order of a crontab does not affect
    when things run, and inserting into the middle risks separating an existing job from
    the comment above it that explains what it is for.
    """
    body = (current or "").rstrip("\n")
    tag = _TAG + (f" — {note}" if note else "")
    addition = f"{tag}\n{schedule} {command}"
    return (f"{body}\n{addition}\n" if body else f"{addition}\n")


def compose_remove(current: str, raw_line: str) -> str:
    """The new crontab with one exact line removed, and its ServerAlly comment with it.

    Matching the whole line, not the command inside it, is what stops a site with two
    jobs that differ only by schedule losing the wrong one.
    """
    lines = (current or "").splitlines()
    target = raw_line.rstrip()
    try:
        index = next(i for i, line in enumerate(lines) if line.rstrip() == target)
    except StopIteration:
        raise CronError(
            "That job is no longer in this crontab — it looks like it was already "
            "removed, or changed. Reload to see what is there now."
        ) from None

    drop = {index}
    # The comment we wrote above it goes too, so removing a job does not leave a trail of
    # orphaned markers. A human's own note is left alone; it may refer to more than this.
    if index > 0 and lines[index - 1].strip().startswith(_TAG):
        drop.add(index - 1)

    kept = [line for i, line in enumerate(lines) if i not in drop]
    body = "\n".join(kept).rstrip("\n")
    return f"{body}\n" if body else ""


async def _install(server: Server, user: str, content: str) -> None:
    """Upload the new crontab and install it.

    Over SFTP rather than in the command, for the same reason as everywhere else: the
    command is visible in ``ps``, and a scheduled command can contain a token or a
    database password.
    """
    import secrets

    from app.services import file_service

    path = f"/tmp/.serverally-cron-{secrets.token_hex(12)}"
    await file_service.write_private(server, path, content)
    try:
        stdout, stderr, code = await connection_manager.execute(
            server, build_write_command(user, path))
    finally:
        try:
            await file_service.delete_path(server, path)
        except Exception:  # noqa: BLE001 — the command removes it too
            pass
    if code != 0:
        raise CronError(
            (stderr or stdout or "").strip()[:300]
            or "The server refused the new schedule."
        )


async def add_job(server: Server, *, user: str, schedule: str, command: str,
                  note: str = "", expect: str | None = None) -> dict:
    """Add one scheduled job to a user's crontab."""
    user = validate_user(user)
    schedule = validate_schedule(schedule)
    command = validate_command(command, _os_family(server))

    current, _e, _c = await connection_manager.execute(server, build_read_command(user))
    _check_unchanged(current, expect)

    await _install(server, user, compose_add(current, schedule, command, note))
    return {"user": user, "schedule": schedule, "command": command,
            "description": describe(schedule)}


async def remove_job(server: Server, *, user: str, raw_line: str,
                     expect: str | None = None) -> dict:
    """Remove one scheduled job, matched by its exact line."""
    user = validate_user(user)
    current, _e, _c = await connection_manager.execute(server, build_read_command(user))
    _check_unchanged(current, expect)

    await _install(server, user, compose_remove(current, raw_line))
    return {"user": user, "removed": raw_line.strip()}


def _check_unchanged(current: str, expect: str | None) -> None:
    """Refuse to write over a crontab that changed since it was read.

    Without this, an entry added by an installer — or by someone over SSH — between the
    screen loading and the button being pressed is deleted, with nothing said. The thing
    deleted is usually a backup job, and nobody finds out until they need it.
    """
    if expect and fingerprint(current) != expect:
        raise CronError(
            "Something else changed this server's scheduled jobs since this page was "
            "loaded, so the change was not applied — saving it now would have deleted "
            "whatever was added. Reload to see the current list, then try again."
        )


def _os_family(server: Server) -> str:
    return "windows" if getattr(server, "connection_type", "") == "winrm" else "linux"


# --- Presets ---------------------------------------------------------------------------
#
# The two jobs that a site genuinely does not work properly without, offered as one click
# rather than as documentation the customer has to go and find.

PRESETS = [
    {
        "id": "laravel",
        "label": "Laravel scheduler",
        "blurb": "Laravel needs this to run its scheduled work — queues, cleanups, "
                 "reminders. Without it, nothing the application schedules ever happens.",
        "schedule": "* * * * *",
        "command": "cd {path} && php artisan schedule:run >> /dev/null 2>&1",
        "needs_path": "The folder the site is in, for example /var/www/shop.example.com",
    },
    {
        "id": "wp-cron",
        "label": "WordPress scheduled tasks",
        "blurb": "By default WordPress runs its scheduled work during a visitor's page "
                 "load, which makes the site slower and unreliable on a quiet site. This "
                 "runs it properly on a timer instead.",
        "schedule": "*/5 * * * *",
        "command": "cd {path} && php -q wp-cron.php >> /dev/null 2>&1",
        "needs_path": "The folder the site is in, for example /var/www/shop.example.com",
    },
]


def jobs_for_site(users: list[dict], domain: str, doc_root: str | None) -> list[dict]:
    """The scheduled jobs that belong to one site.

    A crontab is the server's, not a site's — so this is a filter, not a separate list.
    A job counts as this site's when it mentions the site's folder or its domain, which is
    how the two jobs that matter are always written: Laravel's scheduler runs `cd <folder>
    && php artisan schedule:run`, and WordPress's cron runs its own wp-cron.php.

    Matching on the FOLDER first is what keeps it honest. Matching on the domain alone
    would claim `curl https://other-site.com/ping?from=shop.example.com` as this site's,
    and would miss every job written with a path and no domain in it at all.
    """
    needles = []
    if doc_root:
        site_dir = doc_root.rstrip("/")
        needles.append(site_dir)
        if site_dir.endswith("/public"):
            needles.append(site_dir[: -len("/public")])
    needles.append(domain)

    out: list[dict] = []
    for entry in users:
        for job in entry.get("jobs", []):
            command = job.get("command", "")
            if any(n and n in command for n in needles):
                out.append({**job, "user": entry["user"], "fingerprint": entry["fingerprint"]})
    return out
