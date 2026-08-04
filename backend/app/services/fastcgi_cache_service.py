"""Cache PHP pages in nginx — Ploi's "FastCGI Cache".

Ploi's own warning is worth repeating, because it is the honest one: *"this feature is more
advanced and can trigger unexpected behaviour. For example a page change that is not coming
through because of the cache."* So this ships with an off switch and a purge, and both are
one click. A cache you cannot clear is a site you cannot edit.

**Two constraints shape the whole design.**

First, `fastcgi_cache_path` is only legal in nginx's `http` block — not inside a `server`.
So the storage lives in its own file under `conf.d`, and only the switches go in the site's
vhost. That split is not a preference; putting the path in the vhost makes nginx refuse to
start, which on a shared server takes every site down.

Second, and this is what makes cached sites go wrong rather than fast: **some requests must
never be cached, and some must never be SERVED from cache.** A logged-in WordPress user
would otherwise be handed a stranger's cached page, a POST would be answered from a copy,
and a shop's basket would show somebody else's items. The skip rules below are the feature;
the caching is the easy part.
"""
from __future__ import annotations

import shlex

CACHE_DIR = "/var/cache/nginx/serverally"
CONF_DIR = "/etc/nginx/conf.d"

BEGIN = "# --- ServerAlly page cache (managed) ---"
END = "# --- end ServerAlly page cache ---"


class CacheError(Exception):
    """Something we refuse to do, in words worth showing the customer."""


def zone_name(domain: str) -> str:
    """A zone name nginx accepts, unique per site."""
    return "sa_" + "".join(c if c.isalnum() else "_" for c in domain)[:48]


def zone_file(domain: str) -> str:
    return f"{CONF_DIR}/serverally-cache-{domain}.conf"


def render_zone(domain: str, size_mb: int = 128) -> str:
    """The storage declaration, which has to live in the `http` block.

    `inactive` is longer than `max_size` matters for: entries are evicted by size long
    before they expire, so the limit that actually applies is the disk one.
    """
    return (
        f"{BEGIN}\n"
        f"fastcgi_cache_path {CACHE_DIR}/{domain} levels=1:2 "
        f"keys_zone={zone_name(domain)}:16m max_size={size_mb}m inactive=60m use_temp_path=off;\n"
        f"{END}\n"
    )


def render_block(domain: str) -> str:
    """The switches for one site's PHP location.

    The skip rules come first and are the point. Each one is a real way a cached site
    misbehaves, not a precaution:

    * a POST answered from cache loses the form submission
    * a query string usually means "something specific", not the cacheable page
    * a logged-in WordPress or a filled basket handed a cached copy shows the wrong person's
      view — the cookie tests are what prevent that
    * wp-admin and the login page must never be cached at all
    """
    zone = zone_name(domain)
    return (
        f"{BEGIN}\n"
        f"    set $sa_skip 0;\n"
        f"    if ($request_method != GET) {{ set $sa_skip 1; }}\n"
        f"    if ($query_string != \"\") {{ set $sa_skip 1; }}\n"
        f"    if ($request_uri ~* \"/wp-admin/|/xmlrpc.php|/wp-.*.php|/feed/|sitemap(_index)?.xml\") "
        f"{{ set $sa_skip 1; }}\n"
        f"    if ($http_cookie ~* \"comment_author|wordpress_[a-f0-9]+|wp-postpass"
        f"|wordpress_logged_in|woocommerce_items_in_cart|woocommerce_cart_hash"
        f"|PHPSESSID|laravel_session\") {{ set $sa_skip 1; }}\n"
        f"    fastcgi_cache {zone};\n"
        f"    fastcgi_cache_valid 200 301 302 10m;\n"
        f"    fastcgi_cache_bypass $sa_skip;\n"
        f"    fastcgi_no_cache $sa_skip;\n"
        f"    fastcgi_cache_use_stale error timeout updating http_500 http_503;\n"
        f"    fastcgi_cache_background_update on;\n"
        f"    fastcgi_cache_lock on;\n"
        # So anyone can see whether a page came from the cache. Without it, "is the cache
        # on?" can only be answered by guessing at page speed.
        f"    add_header X-ServerAlly-Cache $upstream_cache_status always;\n"
        f"{END}\n"
    )


def build_apply_command(config_path: str, domain: str, *, enabled: bool,
                        apache: bool) -> str:
    """Turn the cache on or off, and undo it if the web server or the site objects."""
    if apache:
        raise CacheError(
            "Page caching here is an nginx feature. This site is served by Apache, so it "
            "is not offered — its own caching is configured differently.")

    zone = shlex.quote(render_zone(domain) if enabled else "")
    block = shlex.quote(render_block(domain) if enabled else "")
    cfg, dom = shlex.quote(config_path), shlex.quote(domain)
    zf = shlex.quote(zone_file(domain))
    cache_path = shlex.quote(f"{CACHE_DIR}/{domain}")

    # Inserted after `fastcgi_pass`, so the switches land inside the PHP location where they
    # belong. Putting them at server level would try to cache static files through a handler
    # that never runs for them.
    awk = (
        'BEGIN { while ((getline l < B) > 0) blk[++n] = l } '
        '$0 == BEGINM { skip = 1 } '
        'skip { if ($0 == ENDM) skip = 0; next } '
        '{ print } '
        '/^[ \\t]*fastcgi_pass[ \\t]/ { for (i = 1; i <= n; i++) print blk[i] }'
    )

    return (
        f'set -e; '
        f'CFG={cfg}; DOM={dom}; '
        f'[ -f "$CFG" ] || {{ echo "This site\'s configuration file is not there."; exit 3; }}; '
        f'grep -q "fastcgi_pass" "$CFG" || '
        f'  {{ echo "This site does not run PHP, so there is nothing to cache."; exit 6; }}; '
        f'mkdir -p {cache_path}; chown -R www-data:www-data {cache_path} 2>/dev/null '
        f'  || chown -R nginx:nginx {cache_path} 2>/dev/null || true; '
        # The storage declaration goes in its own file because `fastcgi_cache_path` is only
        # legal in the http block. In a vhost it makes nginx refuse to start — which on a
        # shared server takes every site down, not just this one.
        f'ZBK=""; [ -f {zf} ] && {{ ZBK={zf}.bak; cp -p {zf} "$ZBK"; }}; '
        f'printf %s {zone} > {zf}; [ -s {zf} ] || rm -f {zf}; '
        f'BK="$CFG.serverally.$(date +%s).bak"; cp -p "$CFG" "$BK"; '
        f'BLKF="$CFG.serverally.block.tmp"; NEW="$CFG.serverally.new.tmp"; '
        f'printf %s {block} > "$BLKF"; '
        f'awk -v B="$BLKF" -v BEGINM={shlex.quote(BEGIN)} -v ENDM={shlex.quote(END)} '
        f'  {shlex.quote(awk)} "$CFG" > "$NEW"; '
        f'cat "$NEW" > "$CFG"; rm -f "$NEW" "$BLKF"; '
        f'if ! nginx -t 2>/dev/null; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK"; '
        f'  rm -f {zf}; [ -n "$ZBK" ] && mv "$ZBK" {zf} || true; '
        f'  echo "The web server refused it."; exit 4; fi; '
        f'rm -f "$ZBK" 2>/dev/null || true; '
        f'systemctl reload nginx 2>/dev/null || true; '
        f'OK=no; for i in 1 2 3 4; do '
        f'  C="$(curl -s -o /dev/null -w "%{{http_code}}" --max-time 5 '
        f'      -H "Host: $DOM" http://127.0.0.1/ 2>/dev/null || echo 000)"; '
        f'  case "$C" in 2*|3*|401|403|404) OK=yes; break ;; esac; sleep 2; done; '
        f'if [ "$OK" != yes ]; then '
        f'  cp -p "$BK" "$CFG"; rm -f "$BK" {zf}; '
        f'  systemctl reload nginx 2>/dev/null || true; '
        f'  echo "The site stopped answering."; exit 5; fi; '
        f'rm -f "$BK"; echo "applied"'
    )


def build_purge_command(domain: str) -> str:
    """Throw the cached pages away.

    Deletes the site's own cache folder and nothing else — the path is built from the domain
    here, never taken from a caller, because this ends in `rm -rf`.
    """
    path = shlex.quote(f"{CACHE_DIR}/{domain}")
    return (
        f'set -e; P={path}; '
        f'case "$P" in {CACHE_DIR}/?*) : ;; *) echo "Refusing that path."; exit 4 ;; esac; '
        f'[ -d "$P" ] || {{ echo "nothing-cached"; exit 0; }}; '
        f'N="$(find "$P" -type f 2>/dev/null | wc -l)"; '
        f'find "$P" -mindepth 1 -delete 2>/dev/null || true; '
        f'echo "purged=$N"'
    )


_OUTCOMES: dict[int, str] = {
    3: "This site's configuration file could not be found on the server, so nothing changed.",
    4: ("The web server refused it, so it was undone. Your site and every other site on "
        "this server are unaffected."),
    5: ("The site stopped answering with caching on, so it was turned off again. Nothing is "
        "left changed."),
    6: "This site does not run PHP, so there are no pages to cache.",
}


def explain(code: int, output: str, *, enabled: bool) -> tuple[bool, str]:
    if code == 0:
        if not enabled:
            return True, "Page caching is off. Every visit now runs PHP again."
        return True, ("Page caching is on. Visitors get a stored copy of pages that do not "
                      "change per person — logged-in visitors, form posts, admin pages and "
                      "baskets are never cached. If an edit does not appear, clear the "
                      "cache.")
    if code in _OUTCOMES:
        return False, _OUTCOMES[code]
    tail = (output or "").strip().splitlines()
    return False, (tail[-1] if tail else "The cache setting could not be changed.")


def explain_purge(code: int, output: str) -> tuple[bool, str]:
    if code != 0:
        return False, "The cache could not be cleared."
    if "nothing-cached" in (output or ""):
        return True, "There was nothing cached."
    n = "".join(c for c in (output or "") if c.isdigit()) or "0"
    return True, f"Cleared. {n} cached page(s) removed — the next visit will rebuild them."
