"""Laravel queue workers — the settings that decide whether a job runs once, twice, or never.

Ploi gives this its own menu item with nine fields. Ours had a generic "Always running"
daemon, which will happily keep `queue:work` alive but says nothing about the numbers — and
the numbers are the entire feature. Every one of them decides a failure mode:

**The one that causes real damage is `--timeout` against `retry_after`.** Laravel's queue
puts a job back on the queue after `retry_after` seconds so a worker that died does not lose
it. If a worker is allowed to run a job for LONGER than that, the job is handed to a second
worker **while the first is still running it** — and the customer is charged twice, or emailed
twice, and nothing anywhere reports an error. So the two are compared before a worker is
created, and a worker that would do this is refused rather than warned about.

The others each have their own quiet failure:

* `--tries=0` means retry for ever, so one poisoned job blocks the queue behind it;
* `--sleep` decides how long an idle worker waits, which on a paid-per-second host is money;
* `--memory` is what stops a slow leak taking the machine down — the worker exits and
  systemd starts it again, which is the design working;
* **processes** is how many run at once, and each one is its own systemd unit so one dying
  does not take the others with it.

The unit itself is written by `site_daemon_service`, not here. That module already carries
the two lessons systemd punishes — `StartLimit*` belongs in `[Unit]`, and the command must
`exec` or stopping the service orphans the program — and a second thing writing units is a
second thing that has to remember them.
"""
from __future__ import annotations

import json
import re
import shlex

from app.services import app_registry, site_daemon_service as daemons

_S = "___SM_QUEUE___"

#: Laravel's own default when a connection does not say. Used only to compare against, and
#: only when the application could not be read — never to invent a number we then act on.
DEFAULT_RETRY_AFTER = 90

#: Bounds that are about not writing nonsense into a unit file, not about taste.
LIMITS = {
    "timeout": (5, 86_400),
    "sleep": (0, 300),
    "tries": (0, 100),
    "backoff": (0, 86_400),
    "memory": (32, 8192),
    "processes": (1, 20),
}

_NAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,40}$", re.I)


class QueueError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def valid_name(value: str, *, what: str) -> str:
    """A connection or queue name reaches a shell command and a unit name."""
    v = (value or "").strip()
    if not v:
        raise QueueError(f"Enter the {what}.")
    if not _NAME.match(v):
        raise QueueError(
            f"'{value}' is not a valid {what} — letters, numbers, dots, dashes and "
            f"underscores only.")
    return v


def check_number(value: int, field: str) -> int:
    low, high = LIMITS[field]
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise QueueError(f"{field} must be a whole number.") from None
    if not low <= n <= high:
        raise QueueError(f"{field} must be between {low} and {high}.")
    return n


def check_timeout(timeout: int, retry_after: int | None) -> None:
    """The check that stops a job being processed twice.

    Laravel returns a job to the queue after `retry_after` seconds, assuming the worker
    holding it has died. A worker allowed to run longer than that gets its job handed to a
    second worker **while it is still running** — so the work happens twice, and nothing
    reports an error because from the queue's point of view nothing went wrong.

    Refused rather than warned about: a warning on a screen is something somebody clicks
    past, and the consequence is a customer charged twice.
    """
    if retry_after is None:
        return
    if timeout >= retry_after:
        raise QueueError(
            f"A job is allowed {timeout} seconds here, but this connection puts a job back "
            f"on the queue after {retry_after} seconds. That means a job still running "
            f"would be handed to a second worker and done twice — charging a customer "
            f"twice, or sending the same email twice, with nothing reporting an error. "
            f"Set the time limit below {retry_after}, or raise `retry_after` in "
            f"config/queue.php."
        )


def build_command(*, php: str, connection: str, queue: str, timeout: int, sleep: int,
                  tries: int, backoff: int, memory: int, environment: str = "") -> str:
    """The `queue:work` command one worker runs."""
    parts = [
        shlex.quote(php or "php"), "artisan", "queue:work", shlex.quote(connection),
        f"--queue={shlex.quote(queue)}",
        f"--timeout={timeout}", f"--sleep={sleep}", f"--tries={tries}",
        f"--backoff={backoff}", f"--memory={memory}",
        # Without this a worker prints every job it handles into the journal, which on a
        # busy queue fills the disk faster than anything else on the server.
        "--no-interaction",
    ]
    if environment:
        parts.append(f"--env={shlex.quote(environment)}")
    return " ".join(parts)


def worker_name(queue: str, index: int) -> str:
    """What this worker is called on the daemons screen.

    Numbered, because several processes on one queue are several units — one dying must not
    take the others with it, which a single unit running N children cannot promise.
    """
    return f"queue-{valid_name(queue, what='queue name')}-{index}"


def plan(*, domain: str, queue: str, processes: int, **kw) -> list[dict]:
    """Every unit this worker turns into, ready for the daemon machinery to write."""
    n = check_number(processes, "processes")
    command = build_command(queue=queue, **kw)
    return [
        {"name": worker_name(queue, i), "command": command,
         "description": f"Laravel queue worker {i} for {queue} on {domain}"}
        for i in range(1, n + 1)
    ]


def build_probe_command(doc_root: str) -> str:
    """What the application itself says about its queues. Read-only.

    `retry_after` is read from the BOOTED application rather than from `config/queue.php`,
    because the file is frequently `env('QUEUE_RETRY_AFTER', 90)` and the value that
    actually applies lives in `.env`. Reading the file would give the default and be wrong
    exactly where it matters.
    """
    return app_registry.owner_prelude(doc_root, marker="artisan", sentinel=_S) + f"""
PHP_BIN=$(command -v php 2>/dev/null || true)
for _c in $(ls -d /usr/local/lsws/lsphp*/bin/php /usr/bin/php8* 2>/dev/null | sort -rV); do
  [ -x "$_c" ] && $RUNAS "$_c" "$APP_PATH/artisan" --version >/dev/null 2>&1 \\
    && {{ PHP_BIN="$_c"; break; }}
done
[ -n "$PHP_BIN" ] || {{ echo "{_S}|error|nophp"; exit 0; }}
echo "{_S}|php|$PHP_BIN"
echo "{_S}|path|$APP_PATH"
cd "$APP_PATH" || {{ echo "{_S}|error|noapp"; exit 0; }}
# Read by BOOTING the application in a one-off `php -r`, not by `artisan tinker`.
#
# tinker is psysh, and psysh writes a config directory under $HOME. Running as the site's
# own account that is /var/www, which it cannot write — so psysh printed
# "Writing to directory /var/www/.config/psysh is not allowed." **on stdout**, where the
# 2>/dev/null could not catch it, and that sentence was captured AS THE ANSWER. The screen
# showed it as the default connection, `connections` came back empty, and the retry_after
# guard — the one that stops a job being done twice — had nothing to compare against and
# silently skipped on EVERY Laravel site.
#
# Booting the app is what makes the answer right: `retry_after` usually comes from `.env`,
# so reading config/queue.php would give the default and be wrong exactly where it matters.
# And unlike tinker this writes NOTHING, which is the guarantee this probe is held to.
echo "{_S}|queue|$($RUNAS "$PHP_BIN" -r '
require "vendor/autoload.php";
$app = require "bootstrap/app.php";
$app->make(Illuminate\\Contracts\\Console\\Kernel::class)->bootstrap();
echo json_encode(["default" => config("queue.default"),
  "connections" => collect(config("queue.connections"))->map(fn($c) => [
    "driver" => $c["driver"] ?? "", "queue" => $c["queue"] ?? "default",
    "retry_after" => $c["retry_after"] ?? null])]);
' 2>/dev/null | tr -d '\\n' | tail -c 4000)"
"""


#: A queue connection name as Laravel writes one — an identifier, never a sentence.
_NAME = re.compile(r"^[A-Za-z0-9_.:-]{1,40}$")


def parse_probe(stdout: str) -> dict:
    fields: dict[str, str] = {}
    for line in (stdout or "").splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3 and parts[0] == _S:
            fields[parts[1]] = parts[2]

    if fields.get("error"):
        return {"ok": False, "reason": {
            "noapp": "This site does not look like a Laravel application.",
            "nophp": "No PHP on this server can run this application.",
            "nosudo": "We could not run commands as the account that owns this site.",
        }.get(fields["error"], "We could not read this application's queue settings.")}

    payload: dict = {}
    raw = fields.get("queue") or ""
    # The application's own output, so a broken value must degrade to "we do not know"
    # rather than take the page down — and "we do not know" then SKIPS the timeout guard
    # rather than inventing a number to enforce.
    try:
        start = raw.find("{")
        if start >= 0:
            payload = json.loads(raw[start:])
    except (ValueError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    connections = payload.get("connections") or {}
    if not isinstance(connections, dict):
        connections = {}

    # A connection name is an identifier. Anything else is the application talking to us
    # about something that went wrong — a warning, a stack trace — and presenting that as
    # the site's queue configuration is how a broken read looked like a working screen for
    # as long as it did. An unreadable value has to SAY it is unreadable.
    default = str(payload.get("default") or "").strip()
    if not _NAME.match(default):
        default = ""
    unreadable = bool(raw.strip()) and not payload

    return {
        "ok": True,
        "php": fields.get("php", ""),
        "path": fields.get("path", ""),
        "default": default,
        "unreadable": unreadable,
        "connections": [
            {"name": name,
             "driver": (info or {}).get("driver", ""),
             "queue": (info or {}).get("queue", "default"),
             "retry_after": (info or {}).get("retry_after")}
            for name, info in (connections or {}).items()
            if isinstance(info, dict)
        ],
    }


def retry_after_for(connections: list[dict], connection: str) -> int | None:
    """What this connection puts a job back after, or None when we genuinely do not know.

    None is a real answer and is why this is a function. Guessing a number and enforcing it
    would refuse a perfectly good worker on a site we simply could not read — so an unknown
    skips the check instead, and the screen says the check was skipped.
    """
    for c in connections or []:
        if c.get("name") == connection:
            value = c.get("retry_after")
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                return None
    return None


def build_units(*, domain: str, working_dir: str, run_as: str, queue: str,
                processes: int, **kw) -> list[tuple[str, str, str]]:
    """(unit, unit file, script) for each process — written by the daemon machinery.

    Deliberately delegated: `site_daemon_service` already carries the two lessons systemd
    punishes for, and a second module writing unit files is a second one that has to
    remember them.
    """
    out = []
    for item in plan(domain=domain, queue=queue, processes=processes, **kw):
        unit = daemons.unit_name(domain, item["name"])
        out.append((
            unit,
            daemons.build_unit(domain=domain, description=item["description"],
                               command=item["command"], working_dir=working_dir,
                               run_as=run_as, unit=unit),
            daemons.build_script(working_dir, item["command"]),
        ))
    return out


def restart_after_deploy_command(php: str, app_root: str, run_as: str) -> str:
    """Tell the running workers to finish their job and exit, so systemd starts them on the
    NEW code.

    Without this a deploy changes the site and the queue carries on running the previous
    release for hours — the classic "I deployed and the emails still say the old thing".
    """
    return (
        f'su -s /bin/bash {shlex.quote(run_as)} -c '
        f'{shlex.quote(f"cd {shlex.quote(app_root)} && {shlex.quote(php)} artisan queue:restart --no-ansi")} '
        f'2>&1 | tail -2'
    )
