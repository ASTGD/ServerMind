"""Turning a blank server into a working one, in a single step.

Every competitor's customer does this first: connect a fresh machine and press one button.
Ploi runs a fixed 26-task recipe — watched end to end on a real machine, then read back
over SSH to see what it actually did, not what its task names claimed. We had the pieces
but nothing that ran them in order, so a customer had to know which ones to pick and in
which sequence. That is exactly the knowledge they are paying us to not need.

That benchmark also showed what we were MISSING, and the gap had a sharp edge: without
Composer and Node, our own deploy pipeline could not build a PHP or JavaScript app on a
server our own wizard had just finished. Those, plus Supervisor (background jobs), Redis
and Memcached (caching), raised PHP upload limits, and automatic security updates, are
now part of the recipe.

**Two doors, one engine.** A form starts this, and so does Ally ("get this server ready for
a WordPress site"). Neither does the work: both choose a recipe and start the same runner.
Ally's real value here is not running the steps — it is understanding the request, and
adapting when the server turns out not to be blank.

**The guards are the interesting part**, because "set up this server" is destructive in a
way that does not look destructive:

- **A server with a control panel is refused.** CyberPanel, cPanel and Plesk manage their
  own web server, PHP and database. Installing ours alongside breaks both, and the customer
  loses live websites. This is the single most likely way to ruin someone's day here.
- **A server already serving websites is refused** unless they insist, for the same reason.
- **The firewall step is given the port SSH is really on.** The installer defaults to 22.
  On a server whose SSH listens on 2222, enabling a firewall that only allows 22 ends every
  future connection — the same lockout the firewall screen refuses, arriving through a
  different door.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class SetupRefused(Exception):
    """Running this now would break something that already works."""


@dataclass
class Step:
    slug: str                    # playbook slug
    label: str                   # plain language, shown to the customer
    variables: dict = field(default_factory=dict)
    seconds: int = 60
    # A step that fails without ending the setup. Monitoring is nice to have; a web server
    # is not — stopping halfway through a stack leaves a machine in a state nobody can
    # reason about, whereas stopping before it starts is clean.
    optional: bool = False


@dataclass
class Recipe:
    key: str
    title: str
    description: str
    steps: list[Step] = field(default_factory=list)

    @property
    def seconds(self) -> int:
        return sum(s.seconds for s in self.steps)


# What the server is FOR, in the customer's words — never "which stack".
PURPOSES = {
    # Named as SERVER ROLES rather than activities, because the buyer is an agency and
    # "Docker Server" is the phrase they already use. The bracket is the "is this mine?"
    # signal — somebody scanning for Laravel or Next.js should find it without reading on.
    #
    # It says MariaDB because that is what `lemp-stack` actually installs. It said MySQL
    # for months; they are close cousins but not the same thing, and an agency whose
    # client genuinely needs MySQL would only find out after the machine was built.
    "websites": ("Web Server (HTML, PHP, WordPress, Laravel)",
                 "Nginx, PHP and MariaDB — what most websites need."),
    "nodejs":   ("Node.js Server (Express, Next.js, NestJS)",
                 "Node.js and PM2 to keep the app running."),
    "docker":   ("Docker Server",
                 "Docker and Docker Compose."),
    # For the customer whose application outgrew one machine: the database moves to its
    # own server, and several web servers can share it.
    "database": ("Database Server (MariaDB, MySQL, PostgreSQL)",
                 "Just the database, reachable only from your own servers."),
}


# What the customer may choose for a web server, and the ONE place that decides it. The
# screen draws its dropdowns from here and the endpoint validates against here, so an
# option can never be offered that the backend then refuses.
#
# `eol` is not decoration. An agency keeps a client on an old PHP for real reasons, so the
# version is offered — but a version that stopped getting security fixes must SAY so at the
# moment of choosing, which is the only moment anyone is thinking about it.
PHP_CHOICES: tuple[dict, ...] = (
    {"value": "default", "label": "Whatever this system ships", "note": "Safe choice", "eol": False},
    {"value": "8.4", "label": "PHP 8.4", "note": "", "eol": False},
    {"value": "8.3", "label": "PHP 8.3", "note": "", "eol": False},
    {"value": "8.2", "label": "PHP 8.2", "note": "", "eol": False},
    {"value": "8.1", "label": "PHP 8.1", "note": "No longer gets security fixes", "eol": True},
    {"value": "8.0", "label": "PHP 8.0", "note": "No longer gets security fixes", "eol": True},
    {"value": "7.4", "label": "PHP 7.4", "note": "No longer gets security fixes", "eol": True},
)

# MySQL is deliberately NOT offered on Debian: Debian packages MariaDB only, so the
# installer would have to either fail or substitute — and substituting is what made the
# old screen say MySQL for months while installing MariaDB.
DB_CHOICES: tuple[dict, ...] = (
    {"value": "mariadb", "label": "MariaDB", "note": "Works with WordPress and Laravel", "not_on": ()},
    {"value": "mysql", "label": "MySQL", "note": "Not available on Debian", "not_on": ("debian",)},
    {"value": "postgres", "label": "PostgreSQL", "note": "Common with Laravel and Django", "not_on": ()},
    {"value": "none", "label": "No database", "note": "You have one on another server", "not_on": ()},
)


def php_values() -> set[str]:
    return {c["value"] for c in PHP_CHOICES}


def db_values() -> set[str]:
    return {c["value"] for c in DB_CHOICES}


def check_choices(php_version: str, db_engine: str, os_type: str = "",
                  purpose: str = "websites") -> None:
    """Refuse a combination the installer cannot honour, at the moment it is asked for.

    A refusal here costs the customer one click. The same refusal discovered halfway
    through an install costs them a rebuilt server.
    """
    if php_version not in php_values():
        raise SetupRefused(f"“{php_version}” is not a PHP version we install.")
    if db_engine not in db_values():
        raise SetupRefused(f"“{db_engine}” is not a database we install.")
    # "No database" is a sensible answer for a web server whose data lives elsewhere. On a
    # DATABASE server it is a contradiction, and the machine would finish setup with
    # nothing on it — so it is refused here rather than at the end of an install.
    if purpose == "database" and db_engine == "none":
        raise SetupRefused("A database server needs a database. Choose MariaDB, "
                           "MySQL or PostgreSQL.")
    family = (os_type or "").strip().lower()
    for choice in DB_CHOICES:
        if choice["value"] == db_engine and family in choice["not_on"]:
            raise SetupRefused(
                f"{choice['label']} is not available on {family.title()} — it packages "
                f"MariaDB only. Choose MariaDB, or use Ubuntu if you need real MySQL.")


def _base(ssh_port: int, timezone: str, login_user: str, auth_type: str) -> list[Step]:
    """What every server gets, whatever it is for.

    Order matters. Hardening and the firewall come first so the machine is not sitting
    exposed while a long stack install runs — a fresh public VPS starts being probed
    within minutes.
    """
    return [
        Step("full-update", "Installing system updates", seconds=120),
        # Patching must keep happening after today. A server set up once and never
        # updated again is the most common way a managed machine ends up compromised.
        Step("auto-updates", "Turning on automatic security updates",
             seconds=45, optional=True),
        Step("set-timezone", "Setting the clock", {"TIMEZONE": timezone}, seconds=10),
        Step("swap-file", "Adding swap space", {"SWAP_SIZE": "2G"}, seconds=30),
        # The real port, not the installer's default of 22.
        # How ServerAlly itself signs in travels with the step: hardening that turns off
        # the door we came through cannot be undone without the provider's console.
        Step("initial-hardening", "Securing the login",
             {"SSH_PORT": str(ssh_port), "LOGIN_USER": login_user,
              "AUTH_TYPE": auth_type}, seconds=120),
        Step("ufw-setup", "Turning on the firewall",
             {"SSH_PORT": str(ssh_port), "ALLOW_HTTP": "yes", "ALLOW_HTTPS": "yes"},
             seconds=60),
        Step("fail2ban", "Blocking password guessers",
             {"BAN_TIME": "3600", "MAX_RETRY": "5"}, seconds=60),
    ]


def build_recipe(purpose: str, *, ssh_port: int = 22, timezone: str = "UTC",
                 monitoring: bool = True, login_user: str = "root",
                 auth_type: str = "password", php_version: str = "default",
                 db_engine: str = "mariadb", allow_from: str = "") -> Recipe:
    """The ordered list of steps for what this server is for."""
    if purpose not in PURPOSES:
        raise SetupRefused(f"“{purpose}” is not something we know how to set up.")
    title, description = PURPOSES[purpose]
    steps = _base(ssh_port, timezone, login_user, auth_type)

    if purpose == "database":
        # Nothing else goes on it. A database server exists to do one job, and every extra
        # package on it is another thing that can be attacked on a machine holding the
        # customer's data.
        steps += [
            Step("database-server", "Installing the database",
                 {"DB_ENGINE": db_engine, "ALLOW_FROM": allow_from}, seconds=120),
        ]
        return Recipe(purpose, title, description, steps)

    if purpose == "websites":
        # Order: the stack first, then everything that needs PHP to already exist.
        # All of the extras are optional — each one is genuinely useful, but none of
        # them makes the machine incoherent by its absence, and halting a whole server
        # build over a cache daemon would be the wrong trade. A skipped step still
        # shows in the checklist with its reason, so nothing goes missing quietly.
        steps += [
            # The two choices ride on this one step. Defaults reproduce exactly what the
            # setup did before they existed, so an unchanged caller gets an unchanged build.
            Step("lemp-stack", "Installing the web server, PHP and database",
                 {"PHP_VERSION": php_version, "DB_ENGINE": db_engine}, seconds=180),
            # PHP ships allowing 2 MB uploads. That single default is why a brand-new
            # server cannot accept a photo or install a plugin.
            Step("php-limits", "Allowing larger uploads",
                 {"UPLOAD_MAX": "64M", "MEMORY_LIMIT": "256M", "MAX_EXECUTION": "120"},
                 seconds=20, optional=True),
            # Composer and Node are what our OWN deploy pipeline runs to build a site.
            # Without them, deploying to a server we just built fails.
            Step("composer", "Installing Composer", seconds=45, optional=True),
            Step("nodejs-pm2", "Installing Node.js", {"NODE_VERSION": "20"},
                 seconds=60, optional=True),
            Step("redis-cache", "Installing Redis and Memcached", seconds=60,
                 optional=True),
            Step("supervisor", "Setting up background jobs", seconds=45, optional=True),
            # No HTTPS step here on purpose. A certificate is issued for a domain, and at
            # setup time this server has no sites — the step could only ever fail, and a
            # step that cannot succeed is worse than no step. Turning on HTTPS belongs to
            # the site, where there is a real domain to secure; that path installs certbot
            # itself when it needs it.
        ]
    elif purpose == "nodejs":
        steps += [Step("nodejs-pm2", "Installing Node.js", seconds=60)]
    elif purpose == "docker":
        steps += [Step("docker", "Installing Docker", seconds=120)]

    if monitoring:
        # Last, and optional: a server without a dashboard still works.
        steps.append(Step("netdata", "Turning on monitoring", seconds=120, optional=True))

    return Recipe(key=purpose, title=title, description=description, steps=steps)


# ── the guards ────────────────────────────────────────────────────────────────
def check_server(server, *, installed: dict | None = None, force: bool = False) -> str:
    """Empty string if it is safe to set this server up. Otherwise, why not.

    `installed` is what we already know is on the machine (from OS detection and the
    Installed tab). Read rather than guessed: refusing on a hunch would block the main
    path, and allowing on a hunch would destroy a live server.
    """
    if getattr(server, "connection_type", "") != "ssh":
        raise SetupRefused("Setting up a server needs an SSH connection to it.")

    panel = (getattr(server, "panel_type", "") or "").strip()
    if panel and not force:
        raise SetupRefused(
            f"This server runs {panel}, which manages its own web server, PHP and "
            "database. Installing ours alongside would break both and take its websites "
            "offline. Add websites through the Hosting tab instead.")

    facts = installed or {}
    if not force:
        panels = facts.get("panels") or []
        if panels:
            raise SetupRefused(
                f"This server already runs {', '.join(panels)}. Setting it up again would "
                "fight with it. Nothing has been changed.")
        sites = facts.get("sites") or []
        if sites:
            raise SetupRefused(
                f"This server is already serving {len(sites)} website"
                f"{'' if len(sites) == 1 else 's'}. Setting it up would reconfigure the "
                "web server and could take them offline. If you are sure it is safe, "
                "choose “set it up anyway”.")

    os_type = (getattr(server, "os_type", "") or "").lower()
    if os_type and os_type not in ("ubuntu", "debian", "almalinux", "rocky", "centos",
                                   "fedora", "rhel"):
        raise SetupRefused(
            f"Automatic setup covers Ubuntu, Debian and the RHEL family. This server "
            f"reports “{os_type}”, so it needs setting up by hand — ask Ally and it will "
            "work through it with you.")
    return ""


def progress(steps_done: int, total: int) -> dict:
    """The numbers the waiting screen shows. A customer's only question is how much longer."""
    total = max(total, 1)
    return {"done": steps_done, "total": total,
            "percent": min(100, round(steps_done * 100 / total))}


def summarise(recipe: Recipe) -> dict:
    """What the customer is agreeing to, before they press the button."""
    return {
        "key": recipe.key, "title": recipe.title, "description": recipe.description,
        "minutes": max(1, round(recipe.seconds / 60)),
        "steps": [{"label": s.label, "optional": s.optional} for s in recipe.steps],
    }
