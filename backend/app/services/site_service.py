"""Finding the websites a server actually serves.

An agency thinks in **sites**, not servers. When a client rings to say *"acmeshop.com is
broken"*, nobody should have to remember which of forty servers it lives on. Every competitor
puts a Sites list front and centre, and it is the one thing in that list which is genuinely
our job — see [POSITIONING-CATEGORY.md](../../../docs/POSITIONING-CATEGORY.md) §8.

**Discover and operate, never create and provision.** Writing a vhost, switching a PHP
version or issuing a cert is a control panel's work, and five free products do it. Knowing
what is running, whether it is up, whether it is safe and where its logs are — that is the
job we sell.

The ground truth for "what domains does this server serve" is the **web server's own
config**, not the directory layout. A folder in ``/var/www`` tells you a path; ``server_name``
tells you a domain. So the probe reads nginx, Apache, OpenLiteSpeed and the CyberPanel CLI,
and treats web roots only as a fallback.

Same discipline as the metrics, security, threat and log probes:

- a **fixed** bundle, authored here — never assembled from user input and never chosen by the
  AI, so there is nothing to inject into;
- **read-only** — a test asserts no mutating verb appears anywhere in it;
- **never reads application config contents.** We detect that ``wp-config.php`` exists; we do
  not read it. It holds database credentials, and a site inventory has no business carrying
  them.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

_SENTINEL = "___SM_SITE___"

# Bounded so one server with hundreds of vhosts cannot produce an unbounded payload. The cap
# is reported rather than silently applied — a truncated list that looks complete is worse
# than a short one that says so.
MAX_SITES = 200

# Timeouts per probe. `_t` falls back to running unbounded when coreutils `timeout` is absent,
# because a missing binary emitting nothing would read as "this server has no sites".
_T = 20

# nginx's catch-all and other non-domains that appear in a `server_name`. Without this the
# inventory fills up with entries nobody can visit.
_NOT_A_DOMAIN = {
    "_", "localhost", "localhost.localdomain", "default", "default_server",
    "*", "0.0.0.0", "127.0.0.1", "::1", "",
}

_DOMAIN_RE = re.compile(r"^(?:\*\.)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


@dataclass
class DiscoveredSite:
    domain: str
    aliases: list[str] = field(default_factory=list)
    doc_root: str = ""
    source: str = "unknown"
    app_type: str = "unknown"
    app_version: str = ""
    has_ssl: bool = False


def is_real_domain(name: str) -> bool:
    """Would a visitor be able to type this?

    Rejects nginx's ``_`` catch-all, localhost, bare IPs and anything that is not shaped like
    a hostname. A site inventory full of entries nobody can visit is worse than no inventory.
    """
    value = (name or "").strip().lower().rstrip(".")
    if value in _NOT_A_DOMAIN or len(value) > 253:
        return False
    return bool(_DOMAIN_RE.match(value))


def build_discovery_command() -> str:
    """The fixed, read-only probe. One SSH round trip.

    Every line it emits is exactly ``SENTINEL|source|domains|docroot|ssl`` — five fields, the
    same for every source. That uniformity is the point: the parser understands ITS format,
    not four config dialects. (An earlier version let the fragments drift to three different
    shapes, and an nginx line's doc root was read out of the ssl column.)
    """
    t = f'_t() {{ local s=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$s" "$@"; else "$@"; fi; }}; '

    # nginx: `-T` dumps the whole resolved config, so included files and per-site drop-ins are
    # covered without guessing where a distribution puts them.
    nginx = (
        f'if command -v nginx >/dev/null 2>&1; then '
        f'_t {_T} nginx -T 2>/dev/null | awk \''
        f'/^[[:space:]]*server[[:space:]]*{{/ {{ d=""; r=""; s="no"; depth=1; next }} '
        f'/^[[:space:]]*server_name[[:space:]]/ {{ for(i=2;i<=NF;i++){{ gsub(/;/,"",$i); '
        f'if(d=="") d=$i; else d=d","$i }} }} '
        f'/^[[:space:]]*root[[:space:]]/ {{ r=$2; gsub(/;/,"",r) }} '
        f'/ssl_certificate[[:space:]]/ {{ s="yes" }} '
        f'/^[[:space:]]*}}/ {{ if(d!="") print "{_SENTINEL}|nginx|" d "|" r "|" s; d="" }}\'; fi; '
    )

    # Apache: `-S` lists every vhost with its config file and ServerName.
    apache = (
        f'for a in apachectl apache2ctl httpd; do '
        f'if command -v $a >/dev/null 2>&1; then '
        f'_t {_T} $a -S 2>/dev/null | grep -oE "namevhost [^ ]+" | awk \'{{print "{_SENTINEL}|apache|" $2 "||no"}}\'; '
        f'break; fi; done; '
    )

    # OpenLiteSpeed / CyberPanel keep one vhost conf per domain, named after the domain.
    ols = (
        f'if [ -d /usr/local/lsws/conf/vhosts ]; then '
        f'for v in /usr/local/lsws/conf/vhosts/*/; do d=$(basename "$v"); '
        # The doc root is the DIRECTORY existing, not index.php existing. Requiring index.php
        # lost the root for every Laravel site (it serves from /public) and every static one,
        # which then also lost app detection because that matches on the root.
        f'if [ -d "/home/$d/public_html" ]; then r="/home/$d/public_html"; '
        # A CyberPanel CHILD domain lives under its parent account —
        # /home/desktopit.net/news.rmp.gov.bd — not at /home/<domain>/public_html. Looking only
        # in the obvious place left a third of a real box's sites with no path and no detected
        # app. Same layout that made the malware scan miss whole sites in July 2026.
        f'else r=$(ls -d /home/*/"$d" 2>/dev/null | head -1); fi; '
        # A cert directory for the domain is the only HTTPS signal available from this source.
        # Without it every CyberPanel site reported "no HTTPS", which is a false negative on a
        # box where nearly all of them have it.
        f'[ -d "/etc/letsencrypt/live/$d" ] && c=yes || c=no; '
        f'echo "{_SENTINEL}|openlitespeed|$d|$r|$c"; done 2>/dev/null; fi; '
    )

    # CyberPanel's own list is authoritative on a CyberPanel box, including child domains.
    cyberpanel = (
        f'if [ -x /usr/bin/cyberpanel ]; then '
        f'_t {_T} /usr/bin/cyberpanel listWebsitesJson 2>/dev/null '
        f'| tr "," "\\n" | grep -oE \'"domain": *"[^"]+"\' '
        f'| sed -E \'s/.*: *"([^"]+)"/{_SENTINEL}|cyberpanel|\\1||no/\'; fi; '
    )

    # What each site RUNS. Presence only — never the contents of wp-config.php, which holds
    # database credentials.
    apps = (
        f'_t {_T} find /home /var/www /usr/local/lsws/*/html -maxdepth 4 -name wp-includes '
        f'-type d 2>/dev/null | head -{MAX_SITES} | while read -r inc; do d=$(dirname "$inc"); '
        f'v=$(grep -m1 "wp_version *=" "$inc/version.php" 2>/dev/null '
        f'| sed -E "s/.*\'([^\']+)\'.*/\\1/"); '
        f'echo "{_SENTINEL}APP|$d|wordpress|$v"; done; '
        f'_t {_T} find /home /var/www -maxdepth 4 -name artisan -type f 2>/dev/null '
        f'| head -{MAX_SITES} | while read -r a; do '
        f'echo "{_SENTINEL}APP|$(dirname "$a")|laravel|"; done; '
    )

    return t + nginx + apache + ols + cyberpanel + apps


def parse_discovery(output: str) -> tuple[list[DiscoveredSite], bool]:
    """Turn probe output into sites. Pure, so every config dialect is testable offline.

    Returns ``(sites, truncated)``. A site found by more than one source is merged rather than
    duplicated — a CyberPanel box reports the same domain through the CLI *and* nginx, and
    showing it twice would make the inventory look wrong.
    """
    by_domain: dict[str, DiscoveredSite] = {}
    apps: dict[str, tuple[str, str]] = {}   # doc_root -> (app_type, version)

    for raw in (output or "").splitlines():
        line = raw.strip()
        if line.startswith(f"{_SENTINEL}APP|"):
            parts = line.split("|")
            if len(parts) >= 4:
                apps[parts[1].rstrip("/")] = (parts[2], parts[3])
            continue
        if not line.startswith(f"{_SENTINEL}|"):
            continue

        parts = line.split("|")
        # SENTINEL|source|domains|docroot|ssl — positional, because every fragment emits the
        # same five fields. Anything shorter is a truncated line from a dropped connection.
        if len(parts) < 5:
            continue
        source = parts[1]
        names = [n.strip().lower().rstrip(".") for n in parts[2].split(",") if n.strip()]
        doc_root = parts[3].strip().rstrip("/")
        has_ssl = parts[4].strip() == "yes"

        real = [n for n in names if is_real_domain(n)]
        if not real:
            continue
        primary, aliases = real[0], real[1:]

        existing = by_domain.get(primary)
        if existing is None:
            by_domain[primary] = DiscoveredSite(
                domain=primary, aliases=aliases, doc_root=doc_root,
                source=source, has_ssl=has_ssl,
            )
        else:
            # Merge: keep the first source, fill in anything it did not know.
            existing.doc_root = existing.doc_root or doc_root
            existing.has_ssl = existing.has_ssl or has_ssl
            for alias in aliases:
                if alias not in existing.aliases and alias != existing.domain:
                    existing.aliases.append(alias)

    # Attach what each site runs, matched on document root.
    for site in by_domain.values():
        if not site.doc_root:
            continue
        found = apps.get(site.doc_root)
        if found is None:
            # A doc root of /home/x/public_html may hold the app one level down.
            for path, value in apps.items():
                if path.startswith(site.doc_root + "/") or site.doc_root.startswith(path + "/"):
                    found = value
                    break
        if found:
            site.app_type, site.app_version = found[0], found[1]
        elif site.doc_root:
            site.app_type = "php"

    ordered = sorted(by_domain.values(), key=lambda s: s.domain)
    return ordered[:MAX_SITES], len(ordered) > MAX_SITES


async def discover(server: Server) -> tuple[list[DiscoveredSite], bool, str]:
    """Run the probe on ``server``. Returns ``(sites, truncated, error)``.

    Never raises: a server that is offline, or not Linux, simply reports nothing so the rest
    of a fleet scan keeps working.
    """
    if server.connection_type not in ("ssh",):
        return [], False, "Site discovery needs SSH access to the server."
    try:
        # (stdout, stderr, exit_code) — the exit code is deliberately ignored: the probe runs
        # several optional checks, so a missing nginx or apachectl makes it non-zero while the
        # sites it DID find are still valid.
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_discovery_command()
        )
    except Exception as exc:  # noqa: BLE001
        logger.info("Site discovery failed on %s: %s", server.name, exc)
        return [], False, f"Could not reach {server.name}: {exc}"
    sites, truncated = parse_discovery(stdout or "")
    return sites, truncated, ""


# ── Storing what a scan found ────────────────────────────────────────────────

async def sync(db, server: Server, found: list[DiscoveredSite]) -> dict:
    """Write a scan's results for one server. Returns a summary of what changed.

    Upserts rather than replaces, and marks a vanished site ``is_present=False`` rather than
    deleting it — so "when did this disappear?" stays answerable, and a scan that reached the
    server but found nothing (a stopped web server, a config error) cannot silently empty
    somebody's inventory.
    """
    from datetime import datetime, timezone

    from sqlalchemy import select

    from app.models.site import Site

    now = datetime.now(tz=timezone.utc)
    existing = {
        row.domain: row for row in (await db.execute(
            select(Site).where(Site.server_id == server.id)
        )).scalars().all()
    }
    seen: set[str] = set()
    added = updated = 0

    for site in found:
        seen.add(site.domain)
        row = existing.get(site.domain)
        if row is None:
            db.add(Site(
                user_id=server.user_id, server_id=server.id,
                domain=site.domain, aliases=site.aliases, doc_root=site.doc_root or None,
                source=site.source, app_type=site.app_type,
                app_version=site.app_version or None, has_ssl=site.has_ssl,
                is_present=True, first_seen=now, last_seen=now,
                # Found on the server, so it exists — that is what live means.
                status="live",
            ))
            added += 1
        else:
            row.aliases = site.aliases
            row.doc_root = site.doc_root or None
            row.source = site.source
            row.app_type = site.app_type
            row.app_version = site.app_version or None
            row.has_ssl = site.has_ssl
            row.last_seen = now
            # A site that came back is present again — a restored config or a fixed web server.
            row.is_present = True
            # THIS is what makes an install real. A site we created becomes live because a
            # scan has now SEEN it on the server, not because the installer exited 0 — the
            # same "content, not status" rule the mission verification gate follows. A
            # `failed` row that turns up is also live: the customer fixed it by hand, or a
            # step we thought had failed had actually worked.
            if row.status in ("installing", "failed"):
                row.status = "live"
                row.install_error = None
            updated += 1

    gone = 0
    for domain, row in existing.items():
        # A site being built has NOT disappeared — it has not arrived yet. Without this, a
        # scan running in the seconds between "create" and the vhost existing would mark a
        # site the customer just asked for as gone, which reads as a broken product.
        # `failed` is skipped for the same reason: it never arrived, so it cannot vanish.
        if domain not in seen and row.is_present and row.status == "live":
            row.is_present = False
            gone += 1

    await db.commit()
    return {"found": len(found), "added": added, "updated": updated, "gone": gone}


def serialize(site, *, server_name: str | None = None, uptime: dict | None = None) -> dict:
    """A site for the API.

    ``uptime`` carries what the monitor already knows — up/down and certificate expiry, checked
    from OUTSIDE the server where a visitor is. That is the whole value of the Sites page: one
    place that joins what we already collect, rather than a new kind of data.
    """
    return {
        "id": str(site.id),
        "domain": site.domain,
        "aliases": list(site.aliases or []),
        # Nullable now — a site added by hand has no server, and str(None)
        # would send the literal text "None" to the browser.
        "server_id": str(site.server_id) if site.server_id else None,
        "server_name": server_name,
        "doc_root": site.doc_root,
        "source": site.source,
        "app_type": site.app_type,
        "app_version": site.app_version,
        "has_ssl": site.has_ssl,
        "is_present": site.is_present,
        # A site is now created, not only found, so its state has to reach the UI — without
        # these three the whole of P2 is invisible to the customer: they would see a row
        # appear with no sign it is still being built or why it failed.
        "status": getattr(site, "status", "live"),
        "install_error": getattr(site, "install_error", None),
        "requested_type": getattr(site, "requested_type", None),
        "first_seen": site.first_seen.isoformat() if site.first_seen else None,
        "last_seen": site.last_seen.isoformat() if site.last_seen else None,
        "uptime": uptime,
    }


def app_label(app_type: str, version: str | None = None) -> str:
    """What this site runs, in words. Used by the UI and by Ally's context."""
    names = {"wordpress": "WordPress", "laravel": "Laravel", "php": "PHP",
             "static": "Static files", "unknown": "Unknown"}
    label = names.get(app_type, app_type)
    return f"{label} {version}" if version else label


# ── sites the customer tells us about, and watching them ──────────────────────
#
# Discovery answers "what is on my servers". This answers "what do I care about" — and
# those are not the same list. A customer's most important website is often on a host we
# do not manage at all: a client's old cPanel, a Shopify store, a site another agency
# built. No competitor can track that, because every one of them only knows about servers
# they provisioned themselves.

_HOST_RE = re.compile(r"^(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$")


class InvalidDomain(ValueError):
    """Not something we can watch."""


def clean_domain(value: str) -> str:
    """A bare hostname, from whatever the customer pasted.

    People paste a full address, with or without a scheme, sometimes with a path. Taking
    the hostname out is kinder than refusing, and it is unambiguous — but anything that is
    still not a hostname is refused rather than guessed at, because we are about to make
    HTTP requests to it.
    """
    raw = (value or "").strip().lower()
    if not raw:
        raise InvalidDomain("Type the website address.")
    raw = re.sub(r"^[a-z][a-z0-9+.-]*://", "", raw)     # scheme
    raw = raw.split("/")[0].split("?")[0]               # path, query
    raw = raw.split("@")[-1]                            # user:pass@
    raw = raw.split(":")[0]                             # port
    raw = raw.rstrip(".")
    if raw.startswith("www."):
        # Keep the address people actually type; the monitor follows redirects anyway.
        pass
    if len(raw) > 253 or not _HOST_RE.match(raw):
        raise InvalidDomain(
            f"“{value}” does not look like a website address. Try something like "
            "example.com or shop.example.com.")
    if not is_real_domain(raw):
        raise InvalidDomain(
            f"“{raw}” is not a public website address, so we could not check it from "
            "outside.")
    return raw


def monitor_defaults(domain: str, *, https: bool = True) -> dict:
    """How a newly watched site gets checked.

    Deliberately plain: address, 200, five minutes, two failures before we call it down.
    A keyword check is better but only the customer can supply the words, so it is offered
    later rather than guessed at now — a wrong keyword would report a healthy site as down,
    which destroys trust in every other alert we send.
    """
    return {
        "name": domain,
        "url": f"{'https' if https else 'http'}://{domain}",
        "method": "GET",
        "expected_status": 200,
        "interval_seconds": 300,
        "timeout_seconds": 15,
        "failure_threshold": 2,
        "is_active": True,
    }


# ── Creating a site ───────────────────────────────────────────────────────────
#
# Until now a site could only be FOUND. The installer wrote a vhost and the site turned up
# minutes later when the next scan ran — with nothing in between recording what was asked
# for, whether it worked, or why it did not. That is what made creating a website feel
# bolted on, and it is what this section fixes.

#: What the customer can ask for, and which installer builds it.
#:
#: A map rather than a chain of ifs, because adding a type should be one line here plus a
#: playbook — that is the whole point of the catalogue this feeds.
SITE_TYPES: dict[str, dict] = {
    # ── Websites: files a web server reads ──────────────────────────────────
    "static": {
        "popular": True, "group": "websites", "playbook": "create-site", "label": "Empty website",
        "blurb": "A folder and an address. For your own files or a Git deploy.",
        "app_type": "static", "extra": {"WITH_PHP": "no", "TAKEOVER": "no"},
    },
    "php": {
        "popular": True, "group": "websites", "playbook": "create-site", "label": "PHP website",
        "blurb": "An empty site with PHP switched on, ready for an installer.",
        "app_type": "php", "extra": {"WITH_PHP": "yes", "TAKEOVER": "no"},
    },
    "wordpress": {
        "popular": True, "group": "websites", "playbook": "wordpress-site", "label": "WordPress",
        "blurb": "A full WordPress install with its own database.",
        "app_type": "wordpress", "extra": {"TAKEOVER": "no"},
    },
    "laravel": {
        "popular": True, "group": "websites", "playbook": "laravel-site", "label": "Laravel",
        "blurb": "A fresh Laravel install with its database and keys. Needs PHP 8.3+.",
        "app_type": "laravel", "extra": {"TAKEOVER": "no"},
    },

    # ── Applications: a program that keeps running ──────────────────────────
    "app": {
        "popular": True, "group": "applications", "playbook": "create-app", "label": "Web application",
        "blurb": "Node, Next.js, Python or Go — we point the domain at your program "
                 "and keep it alive across crashes and reboots.",
        "app_type": "unknown", "extra": {"TAKEOVER": "no"},
    },

    # ── Ready-made apps ─────────────────────────────────────────────────────
    #
    # ONLY the ones that already answer on a real domain. Gitea, n8n, Uptime Kuma,
    # Vaultwarden and Portainer install on a PORT — offering them here would mean a
    # customer types a domain and gets something at an IP and a port number instead.
    # They join this group in P4, once they are wrapped with a reverse proxy.
    "nextcloud": {
        "popular": True, "group": "apps", "playbook": "nextcloud", "label": "Nextcloud",
        "blurb": "Your own file storage and sharing, like Dropbox.",
        "app_type": "php", "extra": {"TAKEOVER": "no"},
    },
    "ghost": {
        "popular": True, "group": "apps", "playbook": "ghost-cms", "label": "Ghost",
        "blurb": "A modern blog and newsletter platform.",
        "app_type": "unknown", "extra": {"TAKEOVER": "no"},
    },

    # These five install as containers on a port. They can be offered as SITES because the
    # installer now also puts a domain in front of that port (P4) — before that, choosing one
    # here would have meant typing a domain and getting an IP and a port number instead.
    "gitea": {
        "group": "apps", "playbook": "gitea", "label": "Gitea",
        "blurb": "Your own Git hosting, like a private GitHub.",
        "app_type": "unknown", "extra": {"PORT": "3000", "TAKEOVER": "no"},
    },
    "n8n": {
        "popular": True, "group": "apps", "playbook": "n8n", "label": "n8n",
        "blurb": "Automate work between your apps, without code.",
        "app_type": "unknown", "extra": {"PORT": "5678", "TAKEOVER": "no"},
    },
    "uptime-kuma": {
        "group": "apps", "playbook": "uptime-kuma", "label": "Uptime Kuma",
        "blurb": "A status page and uptime monitor you host yourself.",
        "app_type": "unknown", "extra": {"PORT": "3001", "TAKEOVER": "no"},
    },
    "vaultwarden": {
        "group": "apps", "playbook": "vaultwarden", "label": "Vaultwarden",
        "blurb": "A password manager for your team, Bitwarden-compatible.",
        "app_type": "unknown", "extra": {"PORT": "8080", "TAKEOVER": "no"},
    },
    "portainer": {
        "group": "apps", "playbook": "portainer", "label": "Portainer",
        "blurb": "A web interface for the Docker containers on this server.",
        "app_type": "unknown", "extra": {"PORT": "9443", "TAKEOVER": "no"},
    },
}

#: The order the groups are shown in, and what to call them.
SITE_GROUPS = (
    ("websites", "Sites", "A site your visitors browse."),
    ("applications", "Applications", "A program you wrote, running behind your domain."),
    ("apps", "Ready-made apps", "Well-known software, installed and configured for you."),
)


def takes_over() -> frozenset[str]:
    """Which installers can be run against a site that already exists.

    Read from the playbook definitions rather than from the row handed in, so the answer
    cannot depend on what shape the caller passed — and so an installer earns its place by
    actually being able to do the job, not by being named in a list here.
    """
    from app.services.playbook_service import OFFICIAL_PLAYBOOKS, _script_for

    return frozenset(
        item["slug"] for item in OFFICIAL_PLAYBOOKS
        if "TAKEOVER" in (_script_for(item) or "")
    )


def catalogue(playbooks_by_slug: dict) -> list[dict]:
    """What can be installed here, with the questions each one needs.

    The fields come from the PLAYBOOK's own variable list rather than being written out
    again here. Two copies of "what does WordPress ask for" would drift the first time one
    was edited, and the form would then send a variable the script does not read — or miss
    one it does.

    A type whose playbook is missing from this deployment is left out entirely. Offering a
    button that cannot work is worse than not offering it: the customer has already decided
    to trust it by the time it fails.
    """
    from app.services.secret_vars import is_secret

    out: list[dict] = []
    for type_id, spec in SITE_TYPES.items():
        pb = playbooks_by_slug.get(spec["playbook"])
        if pb is None:
            continue
        # An installer is offered here only if it can take over the empty site it is being
        # installed into. One that cannot would write a SECOND web-server entry for a domain
        # that already has one — two configs fighting over one address.
        if spec["playbook"] not in takes_over():
            continue

        fields = []
        for var in (getattr(pb, "variables", None) or []):
            name = var.get("name") if isinstance(var, dict) else None
            if not name or name == "DOMAIN":
                continue  # the domain is always asked for, separately
            if name in spec["extra"]:
                continue  # decided by the choice of type, not by the customer
            fields.append({
                "name": name,
                "label": (var.get("label") or name).strip(),
                "default": var.get("default") or "",
                "required": bool(var.get("required", True)),
                # Reuses the same rule that decides what gets encrypted at rest, so a field
                # stored as a secret is never displayed in clear text on the way in.
                "secret": is_secret(name),
            })

        out.append({
            "id": type_id,
            "group": spec["group"],
            "label": spec["label"],
            "blurb": spec["blurb"],
            # Which few are offered before "show everything". Decided here rather than in
            # the browser: it is a statement about what people actually put on a server,
            # and it belongs with the list it describes — a copy in the frontend would
            # drift the first time a type was added.
            "popular": bool(spec.get("popular")),
            "est_seconds": getattr(pb, "est_runtime_sec", None),
            "fields": fields,
        })
    return out


class SiteError(Exception):
    """Something the customer can read and act on."""


async def create(db, server, user, *, domain: str, site_type: str,
                 variables: dict | None = None):
    """Record the request, then start the installer that fulfils it.

    Order matters: the row is written and committed BEFORE the background job starts. If it
    were the other way round, an installer that finished quickly could look for a site that
    did not exist yet — and a crash between the two would leave work running with nothing
    to attribute it to.
    """
    from sqlalchemy import select

    from app.models.playbook import Playbook, PlaybookRun
    from app.models.site import Site
    from app.services import playbook_service
    from app.services.secret_vars import encrypt_variables

    spec = SITE_TYPES.get(site_type)
    if spec is None:
        raise SiteError(
            f"'{site_type}' is not something we can install. Choose one of: "
            + ", ".join(sorted(SITE_TYPES)) + "."
        )

    # clean_domain raises its own InvalidDomain with a message already written for a
    # customer ("try something like example.com"). Re-raise it as a SiteError so the router's
    # single handler turns it into a 422 — otherwise it escapes as a 500 and the customer is
    # told "Internal Server Error" for typing a domain with a space in it.
    try:
        domain = clean_domain(domain)
    except Exception as exc:  # InvalidDomain, defined in this module
        raise SiteError(str(exc)) from exc
    if not is_real_domain(domain):
        raise SiteError(f"'{domain}' does not look like a domain name.")

    # Refuse a duplicate rather than letting two installers fight over one vhost. Includes
    # `installing` rows, so double-clicking Create cannot start the same build twice.
    dup = (await db.execute(
        select(Site).where(Site.server_id == server.id, Site.domain == domain)
    )).scalar_one_or_none()
    if dup is not None:
        state = {"installing": "is already being set up",
                 "failed": "already exists here (the last attempt failed — remove it first)"}
        raise SiteError(f"{domain} {state.get(dup.status, 'already exists on this server')}.")

    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == spec["playbook"],
                               Playbook.is_official == True)  # noqa: E712
    )).scalar_one_or_none()
    if pb is None:
        raise SiteError(
            f"The installer for {spec['label']} is not available on this ServerAlly.")

    variables = {**(variables or {}), "DOMAIN": domain, **spec["extra"]}
    raw = pb.script_bash
    if not raw:
        raise SiteError(f"The {spec['label']} installer has no script for this server.")
    script = playbook_service.substitute_variables(raw, variables)

    run = PlaybookRun(server_id=server.id, user_id=user.id, playbook_id=pb.id,
                      variables_used=encrypt_variables(variables),
                      status="running")
    db.add(run)
    await db.flush()

    site = Site(
        user_id=user.id, server_id=server.id, domain=domain,
        aliases=[], doc_root=None, source="manual",
        app_type=spec["app_type"], requested_type=site_type,
        has_ssl=False, is_present=True,
        # Not live. Nothing has been observed yet — see STATUSES.
        status="installing", install_run_id=run.id,
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site, str(run.id), script


async def install(db, server, user, site, *, site_type: str, variables: dict | None = None):
    """Put an application onto a site that already exists.

    This is the second half of how a site is made: you add the domain, which builds an
    empty site, and then you choose what goes on it. Without this the catalogue could only
    ever create a site from nothing, so a site and its contents had to be decided in one
    breath — which is not how anyone arrives at the question.

    The installer is the SAME playbook the create path runs. It is handed ``TAKEOVER=yes``,
    which lets the shared site guards replace the empty site's own configuration — and only
    that: the guard additionally requires our marker in the existing config and refuses any
    folder that has anything in it, so this can never overwrite a site in use.
    """
    from sqlalchemy import select

    from app.models.playbook import Playbook, PlaybookRun
    from app.services import playbook_service
    from app.services.secret_vars import encrypt_variables

    spec = SITE_TYPES.get(site_type)
    if spec is None:
        raise SiteError(
            f"'{site_type}' is not something we can install. Choose one of: "
            + ", ".join(sorted(SITE_TYPES)) + "."
        )
    if site.status == "installing":
        raise SiteError(
            f"{site.domain} is still being set up. Wait for that to finish before "
            f"installing something else on it."
        )

    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == spec["playbook"],
                               Playbook.is_official == True)  # noqa: E712
    )).scalar_one_or_none()
    if pb is None:
        raise SiteError(
            f"The installer for {spec['label']} is not available on this ServerAlly.")
    if not pb.script_bash:
        raise SiteError(f"The {spec['label']} installer has no script for this server.")

    variables = {**(variables or {}), "DOMAIN": site.domain, **spec["extra"],
                 "TAKEOVER": "yes"}
    script = playbook_service.substitute_variables(pb.script_bash, variables)

    run = PlaybookRun(server_id=server.id, user_id=user.id, playbook_id=pb.id,
                      variables_used=encrypt_variables(variables),
                      status="running")
    db.add(run)
    await db.flush()

    # Back to installing, and the old failure cleared — this attempt is the current truth.
    site.status = "installing"
    site.install_error = None
    site.install_run_id = run.id
    site.requested_type = site_type
    site.app_type = spec["app_type"]
    await db.commit()
    await db.refresh(site)
    return site, str(run.id), script


async def reconcile_installs(db, user_id) -> int:
    """Move sites out of ``installing`` once their run has actually finished.

    Only FAILURE is concluded here. A run that exited 0 does NOT make a site live — that
    happens when a scan sees it on the server, because an installer reporting success while
    the site does not serve is exactly the failure mode this product exists to catch.
    """
    from sqlalchemy import select

    from app.models.playbook import PlaybookRun
    from app.models.site import Site

    rows = (await db.execute(
        select(Site, PlaybookRun)
        .join(PlaybookRun, Site.install_run_id == PlaybookRun.id)
        .where(Site.user_id == user_id, Site.status == "installing")
    )).all()

    changed = 0
    for site, run in rows:
        if (run.status or "").lower() in ("failed", "error"):
            site.status = "failed"
            site.install_error = (
                (run.failure_reason or "The installer did not finish.").strip()[:500])
            changed += 1
    if changed:
        await db.commit()
    return changed
