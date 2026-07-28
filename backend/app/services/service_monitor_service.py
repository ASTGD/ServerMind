"""Service monitoring — notice when nginx, MySQL or a queue worker stops.

Alerts today can only fire on CPU, RAM and disk. A server can sit at 5% CPU with its
database dead, and we say nothing. Uptime monitoring catches that *if* it takes a
website down; a cache, a queue worker or a mail daemon dying is invisible.

Three properties carry this feature.

**Checking is read-only, restarting is the single exception.** The probe is a fixed
``systemctl is-active`` bundle authored here — never a user string, never AI-chosen —
in the same spirit as the metrics, security and threat probes. Restart is the one
mutating action, it is opt-in per service, and it is bounded (see below).

**Alerting is on state CHANGE, not per check.** One message when a service goes down,
one when it comes back. A service down for six hours does not send seventy-two emails.

**Restart is bounded, and that bound is the whole point.** The classic failure of
auto-healing is a service that crashes on startup: something restarts it, it dies,
repeat — hammering the box, filling the logs, and hiding the real fault behind a
service that looks like it keeps recovering. ``restart_decision`` allows at most
``max_restarts`` attempts inside ``restart_window_seconds`` and then STOPS and escalates
to a human. A monitor that has given up is a louder signal than one that never tried.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# systemd reports plenty of states; these are the ones that mean "not serving".
_DOWN_STATES = {"inactive", "failed", "deactivating", "not-found"}
_UP_STATES = {"active", "activating"}

# A unit name has a narrow shape. Anything else is refused rather than escaped, because
# the safest thing to put in a shell command is a string that was never user-controlled
# in the first place. Allows "nginx", "mysql.service", "php8.2-fpm", "redis-server".
_UNIT_OK = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.@")

MAX_UNITS = 40          # one probe, one round trip — keep it bounded
SENTINEL = "___SM_SVC___"


class InvalidUnit(ValueError):
    """The unit name is not a plausible systemd unit."""


@dataclass
class ServiceState:
    unit: str
    state: str                    # active | inactive | failed | not-found | unknown
    ok: bool
    detail: str = ""


@dataclass
class RestartDecision:
    should_restart: bool
    reason: str
    give_up: bool = False         # tried enough; a human is needed now


def valid_unit(unit: str) -> str:
    """Return the unit name, or raise if it is not one.

    Refusing beats quoting here. These names go into a command we build, and the set of
    legitimate unit names is small and well defined, so anything outside it is either a
    mistake or an attempt — neither of which should reach a server.
    """
    u = (unit or "").strip()
    if not u or len(u) > 128:
        raise InvalidUnit("A service name is required (up to 128 characters).")
    bad = set(u) - _UNIT_OK
    if bad:
        raise InvalidUnit(
            f"“{unit}” isn’t a valid service name — remove: {''.join(sorted(bad))}"
        )
    return u


def build_probe(units: list[str]) -> str:
    """One read-only command reporting the state of every watched unit.

    Sentinel-delimited so the output parses without ambiguity, and `2>/dev/null` because
    `is-active` exits non-zero for a stopped unit — which is information, not an error.
    """
    safe = [valid_unit(u) for u in units[:MAX_UNITS]]
    parts = []
    for u in safe:
        q = shlex.quote(u)
        # The existence check is NOT optional. Found live: `systemctl is-active nginx`
        # answers "inactive" on a box with no nginx installed — byte-identical to a
        # genuinely stopped service. Without this field we would have offered MySQL and
        # Redis for watching on servers that have neither, then alerted that they were
        # down. `systemctl cat` succeeds only when a unit file actually exists.
        parts.append(
            f'echo "{SENTINEL}|{u}|$(systemctl is-active {q} 2>/dev/null || true)'
            f'|$(systemctl is-enabled {q} 2>/dev/null || true)'
            f'|$(systemctl cat {q} >/dev/null 2>&1 && echo yes || echo no)"'
        )
    return "; ".join(parts)


def parse_probe(output: str, units: list[str]) -> dict[str, ServiceState]:
    """Turn probe output into a state per unit.

    A unit that produced no line is ``unknown``, never ``down``: we did not learn it was
    stopped, we learned nothing. Reporting that as an outage would be a false alarm, and
    one false alarm costs more trust than a missed check.
    """
    found: dict[str, ServiceState] = {}
    for line in (output or "").splitlines():
        line = line.strip()
        if not line.startswith(SENTINEL):
            continue
        bits = line.split("|")
        if len(bits) < 3:
            continue
        unit, active = bits[1].strip(), bits[2].strip().lower()
        enabled = bits[3].strip().lower() if len(bits) > 3 else ""
        exists = bits[4].strip().lower() if len(bits) > 4 else "yes"

        # Not installed is not an outage. Checked before the state, because systemd
        # reports an absent unit as "inactive" and we would otherwise call it stopped.
        if exists == "no":
            found[unit] = ServiceState(unit=unit, state="not-found", ok=False,
                                       detail="No such service on this server.")
            continue

        if active in _UP_STATES:
            state, ok, detail = "active", True, ""
        elif active in _DOWN_STATES:
            state, ok = ("not-found", False) if active == "not-found" else (active, False)
            detail = {
                "failed": "The service crashed or failed to start.",
                "inactive": "The service is stopped.",
                "deactivating": "The service is shutting down.",
                "not-found": "No such service on this server.",
            }.get(active, "The service is not running.")
            # A unit that is stopped AND disabled was almost certainly turned off on
            # purpose. Still reported, but named differently so nobody is paged at 3am
            # for a decision they made themselves.
            if active == "inactive" and enabled == "disabled":
                detail = "The service is stopped, and set not to start on boot."
        else:
            state, ok, detail = "unknown", True, "Could not read this service's state."
            # ok=True on purpose: unknown must not trip an alert. See the docstring.

        found[unit] = ServiceState(unit=unit, state=state, ok=ok, detail=detail)

    for u in units:
        found.setdefault(u, ServiceState(
            unit=u, state="unknown", ok=True,
            detail="No answer for this service in the last check."))
    return found


def next_state(
    *, current_status: str, consecutive_failures: int, ok: bool, failure_threshold: int
) -> tuple[str, int, bool]:
    """Fold one check into the monitor's state.

    Same shape as the uptime monitor deliberately — one streak rule in the product, not
    two. Returns ``(status, failures, changed)``; ``changed`` marks a real transition
    worth announcing, so a service that stays down keeps quiet.
    """
    threshold = max(1, failure_threshold)
    if ok:
        return "up", 0, current_status != "up" and current_status in ("down", "unknown")
    failures = consecutive_failures + 1
    status = "down" if failures >= threshold else current_status
    if status == "unknown" and failures >= threshold:
        status = "down"
    return status, failures, status != current_status and status == "down"


def restart_decision(
    *,
    auto_restart: bool,
    status: str,
    restart_count: int,
    window_started: datetime | None,
    max_restarts: int,
    restart_window_seconds: int,
    now: datetime | None = None,
) -> RestartDecision:
    """Decide whether to restart a stopped service. Pure — no I/O.

    The bound is the reason this function exists. A service that crashes on startup will
    be restarted, die, and be restarted again forever unless something counts. After
    ``max_restarts`` inside the window we stop trying and say so, which turns a hidden
    crash-loop into a visible "this needs a person" — the outcome that actually helps.

    Fails CLOSED at every ambiguity: not opted in, not known-down, or a nonsensical
    limit all mean no restart.
    """
    if not auto_restart:
        return RestartDecision(False, "Automatic restart is off for this service.")
    if status != "down":
        return RestartDecision(False, "The service is not down.")
    if max_restarts <= 0:
        return RestartDecision(False, "No restart attempts are allowed.")

    now = now or datetime.now(timezone.utc)
    window = timedelta(seconds=max(60, restart_window_seconds))

    # A window that has elapsed starts fresh — a service that failed once last week and
    # once today is not crash-looping.
    if window_started is None or (now - window_started) > window:
        return RestartDecision(True, "Restarting — first attempt in this window.")

    if restart_count >= max_restarts:
        return RestartDecision(
            False,
            f"Tried {restart_count} restarts in "
            f"{int(window.total_seconds() // 60)} minutes and it keeps stopping. "
            "Not trying again — this needs a person.",
            give_up=True,
        )
    return RestartDecision(
        True, f"Restarting — attempt {restart_count + 1} of {max_restarts}.")


def build_restart(unit: str) -> str:
    """The one mutating command this feature issues.

    `restart`, not `start`: a half-dead unit that is technically "activating" needs
    cycling, and restart is correct for a stopped unit too. The verification read is
    appended so the same round trip tells us whether it actually worked — checking
    later, in another connection, would report on a different moment.
    """
    q = shlex.quote(valid_unit(unit))
    return f"systemctl restart {q}; sleep 2; systemctl is-active {q} 2>/dev/null || true"


def restart_worked(output: str) -> bool:
    """Did the restart actually bring it up? Trust the read, not the exit code."""
    return (output or "").strip().splitlines()[-1].strip().lower() in _UP_STATES \
        if (output or "").strip() else False


# Services worth offering, in plain language. Owners do not know that "the database" is
# called mariadb, so discovery matches on any of the aliases and shows the friendly name.
COMMON_SERVICES: list[dict] = [
    {"label": "Web server (nginx)",     "units": ["nginx"]},
    {"label": "Web server (Apache)",    "units": ["apache2", "httpd"]},
    {"label": "Web server (OpenLiteSpeed)", "units": ["lshttpd", "lsws"]},
    {"label": "Database (MySQL/MariaDB)", "units": ["mysql", "mysqld", "mariadb"]},
    {"label": "Database (PostgreSQL)",  "units": ["postgresql"]},
    {"label": "PHP",                    "units": ["php-fpm", "php8.3-fpm", "php8.2-fpm",
                                                  "php8.1-fpm", "php7.4-fpm"]},
    {"label": "Cache (Redis)",          "units": ["redis", "redis-server"]},
    {"label": "Cache (Memcached)",      "units": ["memcached"]},
    {"label": "Mail (Postfix)",         "units": ["postfix"]},
    {"label": "Firewall (UFW)",         "units": ["ufw"]},
    {"label": "Brute-force protection (Fail2Ban)", "units": ["fail2ban"]},
    {"label": "Docker",                 "units": ["docker"]},
    {"label": "SSH",                    "units": ["ssh", "sshd"]},
    {"label": "Scheduled tasks (cron)", "units": ["cron", "crond"]},
]


def discovery_probe() -> str:
    """Read-only: which of the services we know about exist on this server.

    Offered as a list to pick from because an owner does not know their database unit is
    called ``mariadb`` — asking them to type a unit name is asking them to already know
    the answer they came here for.
    """
    units = sorted({u for s in COMMON_SERVICES for u in s["units"]})
    return build_probe(units)


def discovered(output: str) -> list[dict]:
    """Group probe output into the friendly list, dropping anything not installed."""
    units = sorted({u for s in COMMON_SERVICES for u in s["units"]})
    states = parse_probe(output, units)
    out = []
    for svc in COMMON_SERVICES:
        for u in svc["units"]:
            st = states.get(u)
            if st and st.state != "not-found" and st.state != "unknown":
                out.append({"label": svc["label"], "unit": u,
                            "state": st.state, "running": st.ok})
                break
    return out
