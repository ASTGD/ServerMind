"""Caching PHP pages in nginx — Ploi's "FastCGI Cache".

Ploi's own warning is the honest one: this is the advanced option, and its failure mode is
"my edit is not showing". So it ships with an off switch and a purge.

But the thing that makes a cached site WRONG rather than slow is who gets served a stored
copy. A logged-in WordPress user handed a stranger's cached page, a basket showing somebody
else's items, a form POST answered from cache — those are the real risks, and they are what
these tests are about.

Run against real nginx AND real PHP-FPM, because "is this page cached" can only be answered
by asking twice and seeing whether the same PHP output comes back.
"""
import shutil
import subprocess

import pytest

from app.services import fastcgi_cache_service as fc


docker = pytest.mark.skipif(
    shutil.which("docker") is None
    or subprocess.run(["docker", "info"], capture_output=True).returncode != 0,
    reason="needs docker: whether a page is cached is nginx's answer, not our text's")

PROBE = r"""set -e
apt-get update -qq >/dev/null 2>&1
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nginx curl php-fpm >/dev/null 2>&1
mkdir -p /var/www/shop/public /stub /run/php
printf '<?php echo "TIME:".microtime(true);' > /var/www/shop/public/index.php
PHPV=$(ls /etc/php | head -1)
sed -i 's|^listen = .*|listen = /run/php/php-fpm.sock|' /etc/php/$PHPV/fpm/pool.d/www.conf
php-fpm$PHPV --daemonize 2>/dev/null || true
cat > /etc/nginx/sites-available/shop.conf <<'CFG'
server {
    listen 80 default_server;
    server_name shop.example.com;
    root /var/www/shop/public;
    index index.php;
    location / { try_files $uri $uri/ /index.php?$query_string; }
    location ~ \.php$ {
        include fastcgi_params;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        fastcgi_pass unix:/run/php/php-fpm.sock;
    }
}
CFG
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/shop.conf /etc/nginx/sites-enabled/shop.conf
printf '#!/bin/sh\nexit 0\n' > /stub/systemctl; chmod +x /stub/systemctl
export PATH=/stub:$PATH
nginx
bash /tmp/enable.sh >/dev/null 2>&1; echo "ENABLE=$?"
nginx -s reload 2>/dev/null; sleep 1
get () { curl -s -m5 ${2:+-b "$2"} -H 'Host: shop.example.com' "http://127.0.0.1${1:-/}"; }
A=$(get); B=$(get)
[ "$A" = "$B" ] && echo "CACHED=yes" || echo "CACHED=no"
L1=$(get / "wordpress_logged_in_x=1"); sleep 1; L2=$(get / "wordpress_logged_in_x=1")
[ "$L1" = "$L2" ] && echo "LOGGEDIN=cached" || echo "LOGGEDIN=fresh"
W1=$(get / "woocommerce_items_in_cart=1"); sleep 1; W2=$(get / "woocommerce_items_in_cart=1")
[ "$W1" = "$W2" ] && echo "BASKET=cached" || echo "BASKET=fresh"
Q1=$(get "/?x=1"); sleep 1; Q2=$(get "/?x=1")
[ "$Q1" = "$Q2" ] && echo "QUERY=cached" || echo "QUERY=fresh"
echo "ZONE=$([ -f /etc/nginx/conf.d/serverally-cache-shop.example.com.conf ] && echo yes || echo no)"
bash /tmp/purge.sh > /tmp/po 2>&1 || true; echo "PURGE=$(cat /tmp/po)"
bash /tmp/disable.sh >/dev/null 2>&1; echo "DISABLE=$?"
nginx -s reload 2>/dev/null; sleep 1
C=$(get); sleep 1; D=$(get)
[ "$C" = "$D" ] && echo "AFTEROFF=cached" || echo "AFTEROFF=fresh"
echo "ZONEAFTER=$([ -f /etc/nginx/conf.d/serverally-cache-shop.example.com.conf ] && echo yes || echo no)"
echo "LEFTOVERS=$(ls /etc/nginx/sites-available/ | grep -c serverally || true)"
"""


@pytest.fixture(scope="module")
def result(tmp_path_factory):
    """One container run; every assertion below reads from it."""
    if shutil.which("docker") is None:
        pytest.skip("no docker")
    tmp = tmp_path_factory.mktemp("cache")
    cfg = "/etc/nginx/sites-available/shop.conf"
    (tmp / "probe.sh").write_text(PROBE)
    (tmp / "enable.sh").write_text(fc.build_apply_command(cfg, "shop.example.com",
                                                          enabled=True, apache=False))
    (tmp / "disable.sh").write_text(fc.build_apply_command(cfg, "shop.example.com",
                                                           enabled=False, apache=False))
    (tmp / "purge.sh").write_text(fc.build_purge_command("shop.example.com"))
    proc = subprocess.run(
        ["docker", "run", "--rm",
         "-v", f"{tmp / 'probe.sh'}:/tmp/p.sh", "-v", f"{tmp / 'enable.sh'}:/tmp/enable.sh",
         "-v", f"{tmp / 'disable.sh'}:/tmp/disable.sh", "-v", f"{tmp / 'purge.sh'}:/tmp/purge.sh",
         "ubuntu:24.04", "bash", "/tmp/p.sh"],
        capture_output=True, text=True, timeout=1200)
    out = dict(ln.split("=", 1) for ln in proc.stdout.splitlines() if "=" in ln)
    assert out.get("ENABLE") == "0", proc.stdout + proc.stderr
    return out


@docker
def test_pages_really_are_cached(result):
    """Real PHP printing a timestamp: identical output twice can only mean a stored copy."""
    assert result["CACHED"] == "yes"


@docker
def test_a_logged_in_visitor_is_never_served_a_stored_page(result):
    """The one that matters. Without this a logged-in WordPress user gets handed whatever
    page was cached for a stranger — the site looks broken, or worse, looks like somebody
    else's."""
    assert result["LOGGEDIN"] == "fresh"


@docker
def test_a_basket_is_never_served_from_cache(result):
    """Same failure, more expensive: a shopper shown another shopper's items."""
    assert result["BASKET"] == "fresh"


@docker
def test_a_query_string_is_not_cached(result):
    """A query string usually means "something specific to me", not the cacheable page."""
    assert result["QUERY"] == "fresh"


@docker
def test_the_storage_declaration_goes_in_its_own_file(result):
    """`fastcgi_cache_path` is only legal in nginx's http block. In a vhost it makes nginx
    refuse to start — which on a shared server takes down every site, not just this one."""
    assert result["ZONE"] == "yes"


@docker
def test_clearing_the_cache_works(result):
    """The escape hatch for the failure Ploi warns about: an edit that will not appear."""
    assert "purged=" in result["PURGE"]


@docker
def test_turning_it_off_really_stops_the_caching(result):
    """An off switch that leaves pages cached is not an off switch."""
    assert result["DISABLE"] == "0"
    assert result["AFTEROFF"] == "fresh"
    assert result["ZONEAFTER"] == "no", "the storage declaration was left behind"
    assert result["LEFTOVERS"] == "0"


# ── Without a server ─────────────────────────────────────────────────────────

def test_apache_is_told_honestly_rather_than_half_supported():
    with pytest.raises(fc.CacheError) as exc:
        fc.build_apply_command("/x", "shop.example.com", enabled=True, apache=True)
    assert "nginx" in str(exc.value)


def test_a_site_without_php_is_refused_on_the_server():
    cmd = fc.build_apply_command("/x", "shop.example.com", enabled=True, apache=False)
    assert "does not run PHP" in cmd


def test_purging_can_only_ever_delete_this_sites_cache():
    """It ends in a delete, so the path is built from the domain here and never taken from
    a caller."""
    cmd = fc.build_purge_command("shop.example.com")
    assert fc.CACHE_DIR in cmd
    assert "Refusing that path" in cmd


def test_every_skip_rule_that_protects_a_person_is_present():
    """Named individually, because losing one of these is silent: the site keeps working
    and simply starts showing the wrong people the wrong pages."""
    block = fc.render_block("shop.example.com")
    for cookie in ("wordpress_logged_in", "woocommerce_items_in_cart", "PHPSESSID",
                   "laravel_session", "wp-postpass"):
        assert cookie in block, f"{cookie} is not excluded from caching"
    assert "$request_method != GET" in block
    assert "/wp-admin/" in block
