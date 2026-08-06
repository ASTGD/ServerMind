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
import shlex
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

    # Apache: `-S` lists every vhost with the config file it came from.
    #
    # It prints them in three different shapes, and matching only one of them is how a
    # server with a SINGLE site reported having none — the first site on a fresh server,
    # which is the case that matters most:
    #
    #     *:80          shop.example.com (/etc/apache2/sites-enabled/shop.conf:2)
    #     default server shop.example.com (/etc/.../shop.conf:1)
    #     port 80 namevhost other.example.com (/etc/.../other.conf:1)
    #
    # The `namevhost` wording appears only once a port has SEVERAL name-based vhosts. What
    # every shape does share is the trailing `(/path/to/conf:LINE)`, so the name is taken as
    # the field before it. `is_real_domain` throws out anything that is not a hostname.
    apache = (
        f'for a in apachectl apache2ctl httpd; do '
        f'if command -v $a >/dev/null 2>&1; then '
        f'_t {_T} $a -S 2>/dev/null | awk \''
        f'{{ for (i = 2; i <= NF; i++) if ($i ~ /^\\(\\//) '
        f'{{ print "{_SENTINEL}|apache|" $(i-1) "||no"; break }} }}\'; '
        f'break; fi; done; '
    )

    # OpenLiteSpeed / CyberPanel keep one vhost conf per domain, named after the domain.
    ols = (
        f'if [ -d /usr/local/lsws/conf/vhosts ]; then '
        f'for v in /usr/local/lsws/conf/vhosts/*/; do d=$(basename "$v"); r=""; '
        # ASK the vhost where its files are, rather than guessing from the domain name. A
        # real production site here is served from /var/www/validemailverifier/public while
        # /home/<domain>/public_html also exists — so guessing recorded the wrong folder,
        # which then reported a Laravel application as a plain PHP site and put its Files,
        # Logs and application sections on a directory nobody serves.
        f'if [ -f "$v/vhost.conf" ]; then '
        f'r=$(grep -m1 -E "^[[:space:]]*docRoot" "$v/vhost.conf" 2>/dev/null | awk \'{{print $2}}\'); '
        # $VH_ROOT is LiteSpeed's own variable for the vhost home; left as-is it is a path
        # that does not exist.
        f'r=$(printf "%s" "$r" | sed "s|[\\$]VH_ROOT|/home/$d|"); fi; '
        # Only when the config did not say. The doc root is the DIRECTORY existing, not
        # index.php existing: requiring index.php lost the root for every Laravel site (it
        # serves from /public) and every static one, which then also lost app detection.
        f'if [ -z "$r" ] || [ ! -d "$r" ]; then '
        f'if [ -d "/home/$d/public_html" ]; then r="/home/$d/public_html"; '
        # A CyberPanel CHILD domain lives under its parent account —
        # /home/desktopit.net/news.rmp.gov.bd — not at /home/<domain>/public_html. Looking only
        # in the obvious place left a third of a real box's sites with no path and no detected
        # app. Same layout that made the malware scan miss whole sites in July 2026.
        f'else r=$(ls -d /home/*/"$d" 2>/dev/null | head -1); fi; fi; '
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
            # A scan may CONFIRM and UPDATE what it can see. It must never replace something
            # we know with something it could not determine — the three fields below are all
            # cases where it would, and each was wrong on a real server.
            row.aliases = site.aliases
            # Apache's `-S` reports no document root at all, so a scan of an Apache box
            # would blank the path we recorded when we built the site.
            if site.doc_root:
                row.doc_root = site.doc_root
            # `source` is PROVENANCE — did we build this site, or find it? — and no amount
            # of looking at the server can change the answer. Overwriting it relabelled our
            # own sites as "found on the server", which also revoked our right to remove
            # them, since that permission is exactly "we built it, so we know its layout".
            if row.source != "manual":
                row.source = site.source
            # `unknown` means "I could not tell", not "nothing is installed". Without a doc
            # root there is nothing to match an app against, so an Apache scan downgraded
            # every site it saw to Unknown.
            if site.app_type and site.app_type != "unknown":
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
        # Returned on every payload so the list can group live sites with their copies
        # without a second request per row.
        "environment": getattr(site, "environment", "production") or "production",
        "parent_site_id": (str(site.parent_site_id)
                           if getattr(site, "parent_site_id", None) else None),
        "no_index": bool(getattr(site, "no_index", False)),
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


def monitor_host(url: str) -> str:
    """The hostname a monitored URL points at, lowercased.

    Matching a site to its monitor on hostname is what lets the page show up/down and
    certificate expiry without storing either on the site row — one fact, one owner.
    """
    from urllib.parse import urlparse

    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:  # noqa: BLE001
        return ""


def should_watch(status: str | None, is_present: bool) -> bool:
    """Whether a site is real enough to check from outside.

    Only a site that exists can be up or down. Checking one that is still being built, or
    that failed to build, or that a scan can no longer find, produces a "down" that is
    true, useless, and can never recover — and an alarm nobody can clear is how people
    learn to ignore every alarm we send.
    """
    return status == "live" and bool(is_present)


async def settle_uptime_checks(db, user_id) -> int:
    """Keep each site's uptime check in step with whether the site is actually there.

    Deliberately scoped: a check is only touched when its hostname matches one of THIS
    user's own site rows. A domain somebody chose to watch by itself has no site row, so
    it is never turned off by us — which is the same reason deleting a site leaves its
    check alone.
    """
    from sqlalchemy import select

    from app.models.site import Site
    from app.models.uptime import UptimeMonitor

    sites = {
        row.domain.lower(): row for row in (await db.execute(
            select(Site).where(Site.user_id == user_id))).scalars().all()
    }
    if not sites:
        return 0

    changed = 0
    monitors = (await db.execute(
        select(UptimeMonitor).where(UptimeMonitor.user_id == user_id))).scalars().all()
    for monitor in monitors:
        site = sites.get(monitor_host(monitor.url))
        if site is None:
            continue
        wanted = should_watch(site.status, site.is_present)
        if monitor.is_active != wanted:
            monitor.is_active = wanted
            changed += 1
    if changed:
        await db.commit()
    return changed


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


# ── Staging ───────────────────────────────────────────────────────────────────
#
# A staging site is an ordinary site row with a parent. The rules below are pure so they can
# be tested directly, and because two of them are refusals that decide whether a copy is
# created at all.

#: What a staging domain is called by default. The customer can type anything.
STAGING_PREFIX = "staging."


def staging_domain_for(domain: str) -> str:
    """The domain to suggest for a copy of this site.

    A leading `www.` is stripped, because `staging.www.shop.com` is a name nobody wants and
    the certificate for it would have to cover a label that means nothing. A domain that is
    ALREADY a staging domain is returned unchanged rather than becoming
    `staging.staging.shop.com` — suggesting that would be a suggestion nobody accepts.
    """
    d = (domain or "").strip().lower().rstrip(".")
    if not d:
        raise SiteError("We do not know this site's domain.")
    if d.startswith("www."):
        d = d[4:]
    if d.startswith(STAGING_PREFIX):
        return d
    return f"{STAGING_PREFIX}{d}"


def is_staging(site) -> bool:
    """Whether this site is a copy of another one.

    Reads `environment` rather than the domain. A site called `staging.shop.com` that
    somebody created by hand is not staging in the sense that matters — nothing knows what
    it is a copy of, so nothing can safely promote it.
    """
    return (getattr(site, "environment", "") or "").lower() == "staging"


def check_staging_domain(parent, domain: str) -> str:
    """The domain a copy may be created at, or a refusal.

    The one case worth catching HERE is a copy at the parent's own domain: the duplicate
    rule downstream would report it as "already exists on this server", which reads as a
    system error rather than as what the customer actually asked for.
    """
    try:
        d = clean_domain(domain)
    except Exception as exc:                       # InvalidDomain, defined above
        raise SiteError(str(exc)) from exc
    if not is_real_domain(d):
        raise SiteError(f"'{domain}' does not look like a domain name.")
    if d == (getattr(parent, "domain", "") or "").lower():
        raise SiteError(
            f"A staging copy needs its own address. {parent.domain} is the live site — "
            f"give the copy a different domain, for example {staging_domain_for(parent.domain)}."
        )
    return d


def can_have_staging(site) -> tuple[bool, str | None]:
    """Whether a copy of this site can be made at all, and why not when it cannot.

    Refused rather than attempted in three cases, each because the copy would be a lie:

    * a site that is itself a copy — a staging of a staging has no meaning, and promoting it
      would have two possible destinations;
    * a site we have never actually seen serving, since there is nothing proven to copy;
    * a panel server, for the same reason every other site write refuses one — the panel owns
      the vhost and would revert what we wrote.
    """
    if is_staging(site):
        return False, ("This site is already a staging copy. Make the copy from the live "
                       "site instead.")
    if (getattr(site, "status", "") or "") == "installing":
        return False, "This site is still being set up. Wait for that to finish first."
    if not (getattr(site, "doc_root", None) or "").strip():
        return False, ("We do not know which folder holds this site, so there is nothing to "
                       "copy yet.")
    return True, None


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
        # NOT "unknown". This was the whole reason a Web application had no screen: the
        # registry deliberately shows nothing for a type it cannot identify, so recording
        # the one type we know for certain — because we just installed it — as "unknown"
        # hid the section from every site that had one.
        "app_type": "app", "extra": {"TAKEOVER": "no"},
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


#: Variables this feature decides and never asks about. They control whether an install may
#: overwrite what is already on the domain, so a form field for them would be handing the
#: customer a switch whose only safe setting we already know.
_DECIDED_HERE = frozenset({"TAKEOVER", "REPLACE"})


def occupied(site) -> bool:
    """Is something actually on this site, as opposed to it being an empty shell?

    Reads what was REQUESTED, never what a scan concluded. ``app_type`` is the scan's guess
    and it labels anything it cannot identify as ``unknown`` — a hand-built PHP app, a plain
    HTML site — so "unknown means empty" is exactly how an offer to install over somebody's
    real website gets onto the screen.

    A site we merely found is occupied by definition: it was there before we were.
    """
    if getattr(site, "source", None) != "manual":
        return True
    return (getattr(site, "requested_type", None) or "") not in ("", "static")


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
            if name in spec["extra"] or name in _DECIDED_HERE:
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


def install_variables(playbook, spec: dict, domain: str,
                      supplied: dict | None, *, takeover: bool,
                      replace: bool = False) -> dict:
    """Everything an installer script needs, assembled in one place.

    Pure, and shared by both paths that run one — creating a site and installing onto an
    existing one — because they were assembling it separately and drifted. Adding a site
    sends only a DOMAIN, so anything the script also needs has to come from the playbook's
    own declared defaults; when that link was missing, creating any site at all failed with
    *"This installer still needs WEB_ROOT"*.

    Order is the meaning: the playbook's defaults are the weakest, the customer's answers
    beat them, and the values this feature decides — the domain, what the chosen type
    fixes, whether an empty site may be replaced — beat everything, because they are not
    the customer's to override.
    """
    from app.services import playbook_service  # imported here, as elsewhere in this file

    return {
        **playbook_service.declared_defaults(playbook),
        **(supplied or {}),
        "DOMAIN": domain,
        **spec["extra"],
        **({"TAKEOVER": "yes"} if takeover else {}),
        # Stated on every run, never left to a default. An unsubstituted `{{REPLACE}}` reads
        # as a literal string in the shell, not as "no" — and the one thing this flag must
        # never be is accidentally true.
        "REPLACE": "yes" if replace else "no",
    }


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

    variables = install_variables(pb, spec, domain, variables, takeover=False)
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


async def install(db, server, user, site, *, site_type: str, variables: dict | None = None,
                  replace: bool = False):
    """Put an application onto a site that already exists.

    This is the second half of how a site is made: you add the domain, which builds an
    empty site, and then you choose what goes on it. Without this the catalogue could only
    ever create a site from nothing, so a site and its contents had to be decided in one
    breath — which is not how anyone arrives at the question.

    The installer is the SAME playbook the create path runs. It is handed ``TAKEOVER=yes``,
    which lets the shared site guards replace the empty site's own configuration — and only
    that: the guard additionally requires our marker in the existing config and refuses any
    folder that has anything in it, so this can never overwrite a site in use.

    ``replace`` is how someone deliberately starts a site over — putting WordPress on a
    domain that currently runs Laravel. It DELETES the site's files, so it carries its own
    refusals rather than being a wider reading of the flag above:

    * only a site ServerAlly created. One we merely found could be anything, laid out any
      way, with content nobody has a copy of;
    * only when something is actually there, so the word never appears on a screen where
      it would mean nothing;
    * the database is deliberately left behind. It costs nothing to keep and it is the only
      way back from a replacement someone regrets.
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
    if replace:
        if site.source != "manual":
            raise SiteError(
                f"{site.domain} was already on this server when ServerAlly found it, so it "
                f"is not replaced from here — we did not build it and cannot know what is "
                f"in it. Ask Ally if you need to change what it runs."
            )
        if not occupied(site):
            raise SiteError(
                f"There is nothing on {site.domain} to replace yet.")

    pb = (await db.execute(
        select(Playbook).where(Playbook.slug == spec["playbook"],
                               Playbook.is_official == True)  # noqa: E712
    )).scalar_one_or_none()
    if pb is None:
        raise SiteError(
            f"The installer for {spec['label']} is not available on this ServerAlly.")
    if not pb.script_bash:
        raise SiteError(f"The {spec['label']} installer has no script for this server.")

    variables = install_variables(pb, spec, site.domain, variables,
                                  takeover=True, replace=replace)
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


async def _look_where_an_install_just_finished(db, user_id) -> int:
    """Look at any server where an installer has finished but nothing has SEEN the site yet.

    A site becomes live because a scan sees it on the server, never because the installer
    exited 0 — that rule is the whole point, and it stays. What was missing is that nothing
    ran the scan when an install ended, so three sites installed successfully and sat on
    "Setting up" until somebody happened to press "Look for sites" five minutes later. The
    work had finished; the screen simply never said so.

    Costs nothing in the ordinary case: the query returns no rows unless an install has just
    succeeded, which is a state that lasts seconds.

    Best-effort by construction. A server we cannot reach leaves its site ``installing`` —
    which is the honest answer, because we genuinely have not seen it — and never breaks the
    page that was only asking for a list.
    """
    from sqlalchemy import select

    from app.models.playbook import PlaybookRun
    from app.models.server import Server
    from app.models.site import Site

    servers = (await db.execute(
        select(Server).distinct()
        .join(Site, Site.server_id == Server.id)
        .join(PlaybookRun, Site.install_run_id == PlaybookRun.id)
        .where(Site.user_id == user_id,
               Site.status == "installing",
               PlaybookRun.status == "success")
    )).scalars().all()

    looked = 0
    for server in servers:
        try:
            found, _truncated, error = await discover(server)
            if error:
                logger.info("Could not look at %s after an install: %s", server.name, error)
                continue
            await sync(db, server, found)
            looked += 1
        except Exception:                                    # noqa: BLE001
            logger.info("Look-after-install failed on %s", server.name, exc_info=True)
    return looked



async def reconcile_installs(db, user_id) -> int:
    """Conclude the runs that decide what a site currently is, and leave each site's uptime
    check matching whether the site is really there.

    An INSTALL only concludes on failure. A run that exited 0 does NOT make a site live —
    that happens when a scan sees it on the server, because an installer reporting success
    while the site does not serve is exactly the failure mode this product exists to catch.

    A REMOVAL is the opposite: its success is what we were waiting for, and the row goes
    then. Nothing did that, so pressing Remove ran the removal, removed the site from the
    server, and left the row on screen for ever — the customer's whole view of it was that
    nothing had happened. The scan cannot finish the job either: it deliberately never
    buries a row that is not ``live``, which is the rule that stops a site being marked
    missing halfway through its own install.

    The uptime step rides along rather than sitting in its own function called from three
    places: the last two bugs in this area were both a correct routine that some call site
    forgot to invoke.
    """
    from sqlalchemy import select

    from app.models.playbook import Playbook, PlaybookRun
    from app.models.site import Site

    # First: go and LOOK where an installer has just finished, so a site that really is
    # there stops claiming to be building. This rides along here rather than sitting in the
    # Celery task or in a fourth caller, for the reason stated below — the last three bugs
    # in this area were each a correct routine that some call site forgot to invoke.
    await _look_where_an_install_just_finished(db, user_id)

    rows = (await db.execute(
        select(Site, PlaybookRun, Playbook.slug)
        .join(PlaybookRun, Site.install_run_id == PlaybookRun.id)
        .outerjoin(Playbook, PlaybookRun.playbook_id == Playbook.id)
        .where(Site.user_id == user_id, Site.status.in_(("installing", "removing")))
    )).all()

    changed = 0
    for site, run, slug in rows:
        failed = (run.status or "").lower() in ("failed", "error")
        if site.status == "removing":
            # The run has to BE the removal. This row previously kept pointing at the
            # original install, so a finished install was read as a finished removal — and
            # a site that had just been asked to go was put back to "Setup failed".
            # Concluding from the wrong run is worse than concluding late, so an
            # unexpected one is left alone rather than acted on.
            if slug != "site-remove":
                continue
            if failed:
                # Still on the server, and the customer has to be told why rather than
                # left with a row that quietly went back to looking normal.
                site.status = "remove_failed"
                site.install_error = (
                    (run.failure_reason or "The removal did not finish.").strip()[:500])
                changed += 1
            elif (run.status or "").lower() == "success":
                await db.delete(site)
                changed += 1
        elif failed:
            site.status = "failed"
            site.install_error = (
                (run.failure_reason or "The installer did not finish.").strip()[:500])
            changed += 1
    if changed:
        await db.commit()
    await settle_uptime_checks(db, user_id)
    return changed


# --- What this one site actually is -------------------------------------------------------
#
# The fleet scan answers "which domains does this server serve" and has to stay cheap — it
# runs across every site on the box. These are the facts you want when looking at ONE site:
# who owns its files, where they are, which PHP it runs, how much disk it uses. `du` on a
# large site is slow enough that asking it for seventy sites at once would make the list
# crawl, so it is asked here, for one site, when its page is open.

_DETAIL_SENTINEL = "___SM_SITEDETAIL___"


def build_detail_command(domain: str, doc_root: str | None) -> str:
    """One read-only round trip for a single site's facts.

    The domain is used only to find its config file, and is quoted. Every path acted on is
    read back OUT of that config rather than built from the domain, so a site whose files
    live somewhere unusual reports the truth instead of a guess.
    """
    d = shlex.quote(domain)
    root_hint = shlex.quote(doc_root or "")
    s = _DETAIL_SENTINEL
    return f"""
_t() {{ local n=$1; shift; if command -v timeout >/dev/null 2>&1; then timeout "$n" "$@"; else "$@"; fi; }}
CONF=$(grep -rl -- {d} /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null | head -1)
ROOT=""
if [ -n "$CONF" ]; then
  echo "{s}|config|$CONF"
  # The document root as the WEB SERVER sees it — the only authority on where a site lives.
  ROOT=$(sed -nE 's/^[[:space:]]*(root|DocumentRoot)[[:space:]]+"?([^";]+)"?;?.*/\\2/p' \\
         "$CONF" 2>/dev/null | head -1 | tr -d ' ')
fi
[ -z "$ROOT" ] && ROOT={root_hint}
[ -n "$ROOT" ] && echo "{s}|public|$ROOT"
# Laravel and friends serve from public/; the SITE is the folder above it.
SITE="$ROOT"
case "$ROOT" in */public) SITE=$(dirname "$ROOT") ;; esac
if [ -n "$SITE" ] && [ -d "$SITE" ]; then
  echo "{s}|path|$SITE"
  # Who owns the files is read, never assumed — it is what an upload has to be writable by.
  echo "{s}|user|$(stat -c%U "$SITE" 2>/dev/null)"
  # Bounded: du over a very large tree is the slowest thing here, and -k is everywhere
  # while -b is not.
  echo "{s}|sizekb|$(_t 15 du -sk "$SITE" 2>/dev/null | cut -f1)"
fi
# The PHP THIS site runs, from the socket its own config points at — not the server
# default, which is a different number on a box with three PHP versions installed.
if [ -n "$CONF" ]; then
  SOCK=$(grep -oE 'unix:[^;"]*php[^;"]*\\.sock' "$CONF" 2>/dev/null | head -1)
  [ -n "$SOCK" ] && echo "{s}|php|$(echo "$SOCK" | grep -oE '[0-9]+\\.[0-9]+' | head -1)"
fi
true
"""


def parse_detail(stdout: str) -> dict:
    """Turn the probe's lines into the facts the Information block shows."""
    out: dict = {"config_path": None, "server_path": None, "public_path": None,
                 "system_user": None, "size_kb": None, "php_version": None}
    keys = {"config": "config_path", "path": "server_path", "public": "public_path",
            "user": "system_user", "php": "php_version"}
    for line in (stdout or "").splitlines():
        line = line.strip()
        if not line.startswith(_DETAIL_SENTINEL):
            continue
        parts = line.split("|", 2)
        if len(parts) < 3:
            continue
        kind, value = parts[1], parts[2].strip()
        if not value:
            continue
        if kind == "sizekb":
            try:
                out["size_kb"] = int(value)
            except ValueError:
                pass
        elif kind in keys:
            out[keys[kind]] = value
    return out


async def probe_details(server, site) -> dict:
    """One site's facts. Never raises — an unreachable server returns empty fields, which
    the page shows as "not known" rather than as an error nobody can act on."""
    try:
        stdout, _stderr, _code = await connection_manager.execute(
            server, build_detail_command(site.domain, site.doc_root))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Site detail probe failed for %s: %s", site.domain, exc)
        return {"reachable": False}
    return {**parse_detail(stdout), "reachable": True}
