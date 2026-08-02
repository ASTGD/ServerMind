"""The background processes that belong to one site.

A daemon here is a systemd unit, deliberately the same shape the "Web application"
installer already writes: same crash-loop protection, same `exec`, same restart policy. A
second mechanism (supervisor is on the box too) would mean two places to look when
something is not running, and the server's own Services screen only knows about systemd.

Two things in that shape are load-bearing and were both learned the hard way, so they are
asserted by tests rather than left to a reader noticing:

* ``StartLimitBurst`` and ``StartLimitIntervalSec`` live in ``[Unit]``. Under ``[Service]``
  systemd ignores them with a warning nobody reads, so the crash-loop protection looks
  present and does nothing — a killed service restarted 12 times with no limit applied.
* ``ExecStart`` runs ``exec``. Without it bash stays the main process and the real program
  is only its child, so stopping the service ORPHANS the program; it keeps holding its
  port, and the next start fails with "address already in use".

The command itself goes into a small script rather than onto the ``ExecStart`` line. It was
inline at first, wrapped in single quotes — and a command containing a quote of its own,
``--queue='high,default'``, closed that wrapping early: systemd handed bash three words
instead of one and the daemon ran ``queue:work --queue=`` with the queue names silently
dropped. Real systemd is what showed it; the test had asserted the command TEXT appeared
in the file, which it did. A command is a line of shell, so the faithful place for it is a
line in a shell script, where nothing has to be escaped through two layers of quoting.
"""
from __future__ import annotations

import re
import shlex

#: Our units are named so they can be told apart from the machine's own at a glance, and
#: so a site's daemons can be listed without reading every unit file on the server.
PREFIX = "serverally-site-"

_NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,30}$")
_SLUG = re.compile(r"[^a-z0-9]+")

#: A daemon that dies this many times inside the window is left stopped rather than
#: restarted forever. A process that cannot start is not fixed by starting it again, and a
#: tight loop of failed starts is its own outage — it fills the disk with logs and takes
#: the CPU with it.
MAX_STARTS = 5
START_WINDOW = 60

#: Ours, and only ours. Kept out of /etc/systemd so nothing here can be mistaken for a
#: unit file, and so the pair are removed together.
SCRIPT_DIR = "/etc/serverally/daemons"


class DaemonError(Exception):
    """Something the customer can act on."""


def valid_name(name: str) -> str:
    """Refuse anything that is not a plain name, with a message that says why.

    Validated rather than escaped: this becomes part of a filename in /etc/systemd, and a
    name that needs quoting to be safe there is a name we should not accept at all.
    """
    name = (name or "").strip().lower()
    if not name:
        raise DaemonError("Give this background job a name.")
    if not _NAME.match(name):
        raise DaemonError(
            f"“{name}” cannot be used as a name. Use lowercase letters, numbers and "
            f"hyphens — for example queue-worker.")
    return name


def _slug(domain: str) -> str:
    return _SLUG.sub("-", (domain or "").lower()).strip("-")[:40] or "site"


def unit_name(domain: str, name: str) -> str:
    """The unit file this site's daemon lives in.

    The domain is in the name so two sites can both have a "queue-worker" without one
    quietly replacing the other's.

    Separated by a DOUBLE hyphen, because a single one is ambiguous: `shop.example.com`
    and `shop.example.com.au` are different sites, and with one hyphen the first one's
    page owned the second one's daemons — it could stop and delete them. A slug can never
    contain `--`, since it is built by collapsing every run of punctuation into one.
    """
    return f"{PREFIX}{_slug(domain)}--{valid_name(name)}.service"


def owns(unit: str, domain: str) -> bool:
    """Whether this unit is one of THIS site's.

    The guard on every write. Without it the page is a systemd editor reached from a site,
    where a wrong name stops nginx — or the database every other site on the box uses.
    """
    return (unit.startswith(f"{PREFIX}{_slug(domain)}--")
            and unit.endswith(".service"))


def script_path(unit: str) -> str:
    return f"{SCRIPT_DIR}/{unit}.sh"


def build_script(working_dir: str, command: str) -> str:
    """The command, as a line of shell — which is what it is.

    Nothing is escaped and nothing needs to be: the whole line is the command. `exec` makes
    the program replace this shell, so systemd watches the program itself.
    """
    if not command.strip():
        raise DaemonError("Enter the command to keep running.")
    if not working_dir:
        raise DaemonError("We do not know where this site's files are.")
    return (
        "#!/bin/bash\n"
        "# Written by ServerAlly. Edited here, it is what the daemon runs.\n"
        f"cd {shlex.quote(working_dir)} || exit 1\n"
        f"exec {command.strip()}\n"
    )


def build_unit(*, domain: str, description: str, command: str, working_dir: str,
               run_as: str, unit: str) -> str:
    """The unit file. Same shape as the Web application installer writes."""
    if not command.strip():
        raise DaemonError("Enter the command to keep running.")
    if not working_dir:
        raise DaemonError("We do not know where this site's files are.")
    if not run_as:
        raise DaemonError("We could not tell which account should run this.")
    return (
        "[Unit]\n"
        f"Description={description}\n"
        "After=network.target\n"
        # In [Unit], where systemd actually reads them — see the module docstring.
        f"StartLimitBurst={MAX_STARTS}\n"
        f"StartLimitIntervalSec={START_WINDOW}\n"
        "\n"
        "[Service]\n"
        "Type=simple\n"
        f"User={run_as}\n"
        f"WorkingDirectory={working_dir}\n"
        # The command lives in a script — see the module docstring. -l keeps a login
        # shell so PATH-managed runtimes (nvm, pyenv, rbenv) resolve.
        f"ExecStart=/bin/bash -l {script_path(unit)}\n"
        "Restart=always\n"
        "RestartSec=5\n"
        "StandardOutput=journal\n"
        "StandardError=journal\n"
        "\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )


def build_install_command(unit: str, content: str, script: str) -> str:
    """Write the unit, start it, and say honestly whether it stayed up.

    "Started" is not the same as "running": a command with a typo in it starts, exits
    immediately, and systemd reports the start as successful. So this waits and looks.
    """
    u = shlex.quote(unit)
    return (
        f"set -e; U={u}; "
        f"mkdir -p {SCRIPT_DIR}; "
        f"cat > {SCRIPT_DIR}/$U.sh <<'SM_CMD_EOF'\n{script}SM_CMD_EOF\n"
        f"chmod 0755 {SCRIPT_DIR}/$U.sh; "
        f"cat > /etc/systemd/system/$U <<'SM_UNIT_EOF'\n{content}SM_UNIT_EOF\n"
        "systemctl daemon-reload; "
        "systemctl enable \"$U\" >/dev/null 2>&1 || true; "
        "systemctl restart \"$U\" || true; "
        "sleep 3; "
        "if systemctl is-active --quiet \"$U\"; then echo 'SM_DAEMON_OK'; "
        "else echo 'SM_DAEMON_DOWN'; "
        # Its own log is the only thing that says why, and it is what the customer needs.
        "  journalctl -u \"$U\" -n 15 --no-pager 2>/dev/null | tail -15; fi"
    )


def build_remove_command(unit: str) -> str:
    """Stop it, forget it, and delete the file. In that order."""
    u = shlex.quote(unit)
    return (
        f"U={u}; "
        "systemctl stop \"$U\" >/dev/null 2>&1 || true; "
        "systemctl disable \"$U\" >/dev/null 2>&1 || true; "
        "rm -f /etc/systemd/system/\"$U\"; "
        f"rm -f {SCRIPT_DIR}/\"$U\".sh; "
        "systemctl daemon-reload; echo removed"
    )


def build_action_command(unit: str, action: str) -> str:
    if action not in ("start", "stop", "restart"):
        raise DaemonError("That is not something we can do to a background job.")
    return f"systemctl {action} {shlex.quote(unit)} 2>&1; systemctl is-active {shlex.quote(unit)} 2>&1 || true"


_LIST_SENTINEL = "___SM_DAEMON___"


def build_list_command(domain: str) -> str:
    """This site's daemons, with what each one is actually doing."""
    pattern = f"/etc/systemd/system/{PREFIX}{_slug(domain)}--*.service"
    return (
        f'for f in {pattern}; do [ -f "$f" ] || continue; '
        'u="$(basename "$f")"; '
        'st="$(systemctl is-active "$u" 2>/dev/null)"; '
        'en="$(systemctl is-enabled "$u" 2>/dev/null)"; '
        # Read back from the script on disk rather than from anything we remember, and
        # from the line that actually runs — the file is what the daemon does.
        f'cmd="$(grep -m1 "^exec " {SCRIPT_DIR}/"$u".sh 2>/dev/null | cut -d" " -f2-)"; '
        'desc="$(grep -m1 "^Description=" "$f" | cut -d= -f2-)"; '
        f'echo "{_LIST_SENTINEL}|$u|$st|$en|$desc|$cmd"; '
        "done 2>/dev/null; true"
    )


def parse_list(stdout: str) -> list[dict]:
    out = []
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(f"{_LIST_SENTINEL}|"):
            continue
        parts = line.split("|", 5)
        if len(parts) < 6:
            continue
        _, unit, state, enabled, desc, command = parts
        out.append({
            "unit": unit,
            "name": unit[len(PREFIX):].rsplit(".service", 1)[0].split("--", 1)[-1],
            "running": state == "active",
            "state": state or "unknown",
            "at_boot": enabled == "enabled",
            "description": desc,
            "command": command,
        })
    return sorted(out, key=lambda d: d["unit"])


def suggested(app_type: str, app_root: str) -> dict | None:
    """The daemon this application typically needs.

    Laravel only. A Node, Python or Go site installed as a Web application already HAS its
    service — that installer made one — and offering a second copy of it would give the
    site two processes fighting over the same port.
    """
    if app_type != "laravel" or not app_root:
        return None
    return {
        "name": "queue-worker",
        "command": "php artisan queue:work --sleep=3 --tries=3 --max-time=3600",
        "title": "Run Laravel's queue worker",
        "why": ("Work this app pushes onto a queue — sending email, processing an upload, "
                "talking to a payment provider — only happens while this is running. "
                "Without it the jobs pile up and nothing tells you."),
    }
