"""Playbook service — seed data and execution helpers."""
from __future__ import annotations

import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook

logger = logging.getLogger(__name__)


# ── Failure-reason extraction ─────────────────────────────────────────────────
_ERROR_MARKER = re.compile(r"^>{0,3}\s*(?:ERROR|FATAL|FAILED)\s*[:\-]\s*(.+)$", re.IGNORECASE)
_NOISE_PREFIXES = ("⏹", "⟳", "▶", "✓", ">>> ")


def _cap(text: str, limit: int = 240) -> str:
    """Collapse to a single trimmed line, capped in length for inline display."""
    one_line = " ".join(text.split())
    return one_line if len(one_line) <= limit else one_line[: limit - 1].rstrip() + "…"


def extract_failure_reason(output: "str | list[str] | None") -> str | None:
    """Pull a short, human-readable reason from a failed/stalled run's output.

    Prefers an explicit error line (e.g. a pre-flight ``>>> ERROR: ...``); otherwise
    falls back to the last meaningful line. Returns None for empty output. The result
    is a single capped line so the UI can show it inline on a run row."""
    if not output:
        return None
    text = output if isinstance(output, str) else "\n".join(output)
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return None
    # Prefer the last explicit ERROR/FATAL line (skip the generic exit-code note).
    for ln in reversed(lines):
        m = _ERROR_MARKER.match(ln)
        if m and "command exited with status" not in m.group(1).lower():
            return _cap(m.group(1))
    # Otherwise the last meaningful line that isn't a progress/status marker.
    for ln in reversed(lines):
        if not ln.startswith(_NOISE_PREFIXES):
            return _cap(ln)
    return _cap(lines[-1])

# ── Docker dependency preamble ────────────────────────────────────────────────
# Docker-based playbooks shouldn't fail just because Docker isn't installed yet —
# a non-technical user shouldn't need to know about that dependency. Any playbook
# flagged ``"needs_docker": True`` gets this idempotent block injected right after
# its ``set -euo pipefail`` line: it installs Docker first if missing, otherwise
# prints the existing version and moves on.
_ENSURE_DOCKER = (
    "ensure_docker() {\n"
    "  if command -v docker >/dev/null 2>&1; then\n"
    '    echo ">>> Docker already installed: $(docker --version)"\n'
    "    return 0\n"
    "  fi\n"
    '  echo ">>> Docker not found — installing it first (this can take a minute)..."\n'
    "  curl -fsSL https://get.docker.com | sh\n"
    "  systemctl enable --now docker\n"
    '  echo ">>> Docker ready: $(docker --version)"\n'
    "}\n"
    "ensure_docker\n"
)


def _with_docker(script: str) -> str:
    """Inject the ensure_docker preamble after the ``set -euo pipefail`` line."""
    marker = "set -euo pipefail\n"
    idx = script.find(marker)
    if idx == -1:
        return _ENSURE_DOCKER + script
    cut = idx + len(marker)
    return script[:cut] + _ENSURE_DOCKER + script[cut:]


# ── Control-panel pre-flight guard ────────────────────────────────────────────
# Control panels (CyberPanel, HestiaCP, …) demand a FRESH, supported server and
# fail messily on a dirty one. Playbooks flagged ``"needs_preflight": True`` get
# this ``preflight`` function injected after ``set -euo pipefail``; the script
# then sets PANEL / MIN_RAM_MB and calls ``preflight`` before the vendor
# installer. It aborts with a plain-English message instead of a cryptic failure.
_PREFLIGHT = (
    "preflight() {\n"
    '  panel="${PANEL:-control panel}"\n'
    '  min_ram="${MIN_RAM_MB:-1024}"\n'
    '  if [ "$(id -u)" -ne 0 ]; then echo ">>> ERROR: $panel must be installed as root."; exit 1; fi\n'
    '  echo ">>> Pre-flight checks for $panel..."\n'
    "  for entry in /usr/local/cpanel:cPanel /usr/local/CyberCP:CyberPanel /usr/local/hestia:HestiaCP /usr/local/directadmin:DirectAdmin /opt/psa:Plesk /www/server/panel:aaPanel /home/clp:CloudPanel; do\n"
    '    d="${entry%%:*}"; n="${entry##*:}"\n'
    '    if [ -e "$d" ]; then echo ">>> ERROR: $n is already installed ($d). $panel needs a clean server — use a fresh VPS."; exit 1; fi\n'
    "  done\n"
    '  if command -v docker >/dev/null 2>&1; then echo ">>> ERROR: Docker is present. A control panel needs a clean server (no Docker / existing web stack). Use a fresh VPS."; exit 1; fi\n'
    "  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -qE ':80[[:space:]]'; then who=$(ss -tlnp 2>/dev/null | grep -E ':80[[:space:]]' | grep -oE '\"[^\"]+\"' | head -1 | tr -d '\"'); echo \">>> ERROR: Port 80 is already in use${who:+ by '$who'}. $panel needs a clean server.\"; exit 1; fi\n"
    "  ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}')\n"
    '  if [ -n "${ram_mb:-}" ] && [ "$ram_mb" -lt "$min_ram" ]; then echo ">>> ERROR: $panel needs at least ${min_ram}MB RAM (found ${ram_mb}MB)."; exit 1; fi\n'
    '  echo ">>> Pre-flight OK — clean server, ${ram_mb:-?}MB RAM. Installing $panel; this can take several minutes."\n'
    "}\n"
)


def _with_preflight(script: str) -> str:
    """Inject the preflight function definition after the ``set -euo pipefail`` line."""
    marker = "set -euo pipefail\n"
    idx = script.find(marker)
    if idx == -1:
        return _PREFLIGHT + script
    cut = idx + len(marker)
    return script[:cut] + _PREFLIGHT + script[cut:]


# ── Multi-distro layer (Update 22, Tier 2) ────────────────────────────────────
# Web-stack playbooks used to hard-code apt + mysql-server + a pinned PHP version,
# so they broke on Debian (no mysql-server), newer Ubuntu (php8.2 missing), and every
# RHEL box (no apt). This shared preamble detects the OS family once and exposes
# helpers — pkg_install / svc_enable / php_fpm_service / php_fpm_socket /
# open_firewall — so a SINGLE script runs on Ubuntu/Debian (any version) AND
# AlmaLinux/Rocky/CentOS. PHP is installed via unversioned meta-packages (php-fpm,
# php-mysql/php-mysqlnd …) which resolve to each distro's default PHP — no PPA, no
# pinned version. The DB is MariaDB (drop-in MySQL, present in every default repo).
_DISTRO = r"""# --- ServerAlly multi-distro layer ---
. /etc/os-release 2>/dev/null || true
OS_ID="${ID:-}"; OS_LIKE="${ID_LIKE:-}"
case " $OS_ID $OS_LIKE " in
  *ubuntu*|*debian*) FAMILY=debian; PM=apt ;;
  *almalinux*|*rocky*|*centos*|*rhel*|*fedora*) FAMILY=rhel; PM=dnf ;;
  *) echo ">>> ERROR: Unsupported OS: ${OS_ID:-unknown}. This playbook supports Ubuntu/Debian and AlmaLinux/Rocky/CentOS."; exit 1 ;;
esac
if [ "$FAMILY" = rhel ] && ! command -v dnf >/dev/null 2>&1; then PM=yum; fi
echo ">>> Detected ${OS_ID:-linux} (${FAMILY} family)."
pkg_refresh() {
  if [ "$FAMILY" = debian ]; then export DEBIAN_FRONTEND=noninteractive; apt-get update -qq
  else "$PM" -y makecache >/dev/null 2>&1 || true; fi
}
pkg_install() {
  if [ "$FAMILY" = debian ]; then DEBIAN_FRONTEND=noninteractive apt-get install -y -qq "$@"
  else "$PM" install -y "$@"; fi
}
svc_enable() { systemctl enable --now "$1" >/dev/null 2>&1 || systemctl enable --now "$1"; }
svc_restart() {
  if ! systemctl restart "$1" 2>/tmp/sm_svc.log; then
    echo ">>> ERROR: $1 failed to start. Most recent log:"
    journalctl -u "$1" --no-pager -n 12 2>/dev/null | tail -12 || cat /tmp/sm_svc.log 2>/dev/null
    exit 1
  fi
}
# Debian: the version of php-fpm that is actually INSTALLED (which can differ from the
# php CLI on a box with leftover packages) — used for both the service name and socket.
php_fpm_ver() {
  # Prefer the FPM that is actually RUNNING. A box with several PHP versions installed
  # (very common once anyone adds a newer PHP) would otherwise get the lowest-numbered
  # unit — which may be stopped, so its socket does not exist and every PHP request 502s.
  v="$(systemctl list-units --type=service --state=running --no-legend 'php*-fpm.service' 2>/dev/null | sed -n 's/^[^p]*php\([0-9.]*\)-fpm\.service.*/\1/p' | head -1)"
  # Then the NEWEST installed rather than the oldest.
  [ -z "$v" ] && v="$(systemctl list-unit-files --no-legend 'php*-fpm.service' 2>/dev/null | sed -n 's/^php\([0-9.]*\)-fpm\.service.*/\1/p' | sort -V | tail -1)"
  [ -z "$v" ] && v="$(php -r 'echo PHP_VERSION;' 2>/dev/null | cut -d. -f1,2)"
  echo "$v"
}
php_fpm_service() {
  if [ "$FAMILY" = debian ]; then echo "php$(php_fpm_ver)-fpm"
  else echo "php-fpm"; fi
}
php_fpm_socket() {
  if [ "$FAMILY" = debian ]; then
    v="$(php_fpm_ver)"; s="/run/php/php${v}-fpm.sock"
    if [ ! -S "$s" ]; then
      # Only real sockets, newest first. The old code took the alphabetically-first
      # match, which on a box with an alternatives symlink is /run/php/php-fpm.sock —
      # often DANGLING, so nginx got a path with nothing behind it.
      s=""
      for c in $(ls -1 /run/php/php*-fpm.sock 2>/dev/null | sort -Vr); do
        [ -S "$c" ] && { s="$c"; break; }
      done
    fi
    [ -z "$s" ] && s="/run/php/php${v}-fpm.sock"
    echo "$s"
  else echo "/run/php-fpm/www.sock"; fi
}
open_firewall() {
  if command -v ufw >/dev/null 2>&1 && ufw status 2>/dev/null | grep -qi active; then ufw allow "${1}/tcp" >/dev/null 2>&1 || true
  elif command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld 2>/dev/null; then
    firewall-cmd --permanent --add-port="${1}/tcp" >/dev/null 2>&1 || true; firewall-cmd --reload >/dev/null 2>&1 || true
  fi
}
# --- end multi-distro layer ---
"""


_SITE_GUARDS = "# --- ServerAlly shared site guards ---\n# A domain reaches the shell as a variable and ends up inside BOTH a config file and a\n# filesystem path. Escaping it correctly in both places is harder than refusing anything\n# that is not a hostname, so it is validated rather than escaped.\ncase \"$DOMAIN\" in\n  \"\"|*[!a-zA-Z0-9.-]*|-*|.*|*.)\n    echo \">>> ERROR: '$DOMAIN' is not a valid domain name. Use something like shop.example.com.\"\n    exit 1 ;;\nesac\ncase \"$DOMAIN\" in *..*)\n    echo \">>> ERROR: '$DOMAIN' is not a valid domain name.\"; exit 1 ;;\nesac\n\n# A control panel owns its own web-server configuration. A vhost written behind its back is\n# invisible to the panel, never gets its certificate renewed, and may be overwritten on the\n# panel's next change. This is the single most likely way to ruin someone's day here.\nfor _PANEL in /usr/local/CyberCP /usr/local/cpanel /opt/psa /usr/local/directadmin; do\n  if [ -d \"$_PANEL\" ]; then\n    echo \">>> ERROR: this server runs a control panel ($_PANEL). Add this through the panel\"\n    echo \"    instead \u2014 anything created behind its back is invisible to it and will not get\"\n    echo \"    certificates renewed. Nothing was changed.\"\n    exit 1\n  fi\ndone\n\n# Which web server, and only one of them.\nNGINX=no; APACHE=no; APACHE_SVC=\"\"\nsystemctl is-active --quiet nginx 2>/dev/null && NGINX=yes\nfor _a in apache2 httpd; do\n  if systemctl is-active --quiet \"$_a\" 2>/dev/null; then APACHE=yes; APACHE_SVC=\"$_a\"; fi\ndone\nif [ \"$NGINX\" = yes ] && [ \"$APACHE\" = yes ]; then\n  echo \">>> ERROR: nginx and Apache are both running, so they are already fighting over\"\n  echo \"    port 80. Stop one of them first. Nothing was changed.\"\n  exit 1\nfi\nif [ \"$NGINX\" = no ] && [ \"$APACHE\" = no ]; then\n  echo \">>> ERROR: no web server is running on this server. Set the server up first\"\n  echo \"    (that installs nginx, PHP and a database), then add this.\"\n  exit 1\nfi\n\n# Taking over a domain that already has a config would silently repoint a live site.\n_EXISTING=\"$(grep -rl -- \"$DOMAIN\" /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null | head -1 || true)\"\nif [ -n \"$_EXISTING\" ]; then\n  echo \">>> ERROR: $DOMAIN is already configured on this server ($_EXISTING).\"\n  echo \"    Nothing was changed \u2014 delete the existing one first if you meant to replace it.\"\n  exit 1\nfi\n\n# The user the web server actually runs as, read rather than assumed: wrong ownership either\n# breaks uploads or hands the web server write access it should not have.\nWEB_USER=\"$(ps -eo user,comm 2>/dev/null | awk '$2 ~ /^(nginx|apache2|httpd)$/ && $1 != \"root\" {print $1; exit}')\"\n[ -z \"$WEB_USER\" ] && { id -u www-data >/dev/null 2>&1 && WEB_USER=www-data; }\n[ -z \"$WEB_USER\" ] && { id -u nginx >/dev/null 2>&1 && WEB_USER=nginx; }\n[ -z \"$WEB_USER\" ] && { id -u apache >/dev/null 2>&1 && WEB_USER=apache; }\n[ -z \"$WEB_USER\" ] && WEB_USER=root\n\nif [ \"$NGINX\" = yes ]; then\n  if [ -d /etc/nginx/sites-available ]; then SITE_CONF=/etc/nginx/sites-available/\"$DOMAIN\"\n  else SITE_CONF=/etc/nginx/conf.d/\"$DOMAIN\".conf; fi\n  TEST_CMD=\"nginx -t\"; RELOAD_SVC=\"nginx\"\nelse\n  if [ -d /etc/apache2/sites-available ]; then SITE_CONF=/etc/apache2/sites-available/\"$DOMAIN\".conf\n  else SITE_CONF=/etc/httpd/conf.d/\"$DOMAIN\".conf; fi\n  TEST_CMD=\"apachectl configtest\"; RELOAD_SVC=\"$APACHE_SVC\"\nfi\nENABLED_LINK=\"\"\n\n# Test BEFORE reloading, and undo on failure. Reloading a configuration that does not parse\n# takes EVERY site on this server offline, not just the new one \u2014 so a failure here removes\n# what was added and leaves the running server untouched.\napply_web_config() {\n  if [ \"$NGINX\" = yes ] && [ -d /etc/nginx/sites-enabled ]; then\n    ln -sfn \"$SITE_CONF\" /etc/nginx/sites-enabled/\"$DOMAIN\"\n    ENABLED_LINK=/etc/nginx/sites-enabled/\"$DOMAIN\"\n  elif [ \"$APACHE\" = yes ] && command -v a2ensite >/dev/null 2>&1; then\n    a2ensite \"$DOMAIN\" >/dev/null 2>&1 || true\n    ENABLED_LINK=/etc/apache2/sites-enabled/\"$DOMAIN\".conf\n  fi\n  if ! $TEST_CMD >/tmp/sm_conftest.log 2>&1; then\n    echo \">>> ERROR: the web server rejected the new configuration:\"\n    tail -12 /tmp/sm_conftest.log\n    [ -n \"$ENABLED_LINK\" ] && rm -f \"$ENABLED_LINK\"\n    rm -f \"$SITE_CONF\"\n    echo \">>> Removed what was added. The running web server was NOT touched, so your other\"\n    echo \"    websites are unaffected.\"\n    exit 1\n  fi\n  # reload, not restart: a restart drops connections that other sites are serving.\n  systemctl reload \"$RELOAD_SVC\" 2>/dev/null || svc_restart \"$RELOAD_SVC\"\n  echo \">>> Reloaded $RELOAD_SVC\"\n}\n\n# A 200 is not proof \u2014 confirm the body is really what we put there. Retried, because\n# `systemctl reload` returns BEFORE nginx has finished swapping workers, so an immediate\n# request can still be answered by the OLD config. A single shot reported \"could not verify\"\n# on a site that was serving perfectly, and a false warning teaches people to ignore real ones.\nverify_serves() {\n  _want=\"$1\"; _ok=no\n  for _try in 1 2 3 4 5 6 7 8; do\n    _body=\"$(curl -s --max-time 5 -H \"Host: $DOMAIN\" http://127.0.0.1/ 2>/dev/null | head -c 600 || true)\"\n    # -F because a domain is full of dots, which grep would treat as wildcards.\n    if printf \"%s\" \"$_body\" | grep -qF \"$_want\"; then _ok=yes; break; fi\n    sleep 2\n  done\n  [ \"$_ok\" = yes ] && return 0 || return 1\n}\n# --- end shared site guards ---\n"


# LEMP — Nginx + MariaDB + PHP-FPM, multi-distro.
_LEMP_BASH = "#!/bin/bash\nset -euo pipefail\n" + _DISTRO + r"""MYSQL_ROOT_PASS="{{MYSQL_ROOT_PASS}}"
echo "=== Installing LEMP stack ==="
pkg_refresh
pkg_install nginx
svc_enable nginx
pkg_install mariadb-server
svc_enable mariadb
if [ "$FAMILY" = debian ]; then
  pkg_install php-fpm php-mysql php-cli php-curl php-gd php-mbstring php-xml php-zip
else
  pkg_install php-fpm php-mysqlnd php-cli php-curl php-gd php-mbstring php-xml
  sed -i 's/^user = .*/user = nginx/; s/^group = .*/group = nginx/' /etc/php-fpm.d/www.conf 2>/dev/null || true
fi
svc_enable "$(php_fpm_service)"
if [ -n "$MYSQL_ROOT_PASS" ]; then
  mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED BY '${MYSQL_ROOT_PASS}'; FLUSH PRIVILEGES;" 2>/dev/null \
    || echo ">>> Note: could not set the database root password (it may already be set)."
fi
open_firewall 80; open_firewall 443
echo "Nginx: $(nginx -v 2>&1)"
echo "Database: $(mysql --version 2>/dev/null || echo MariaDB)"
echo "PHP: $(php -v 2>/dev/null | head -1)"
echo ">>> LEMP stack installed."
"""


# LAMP — Apache + MariaDB + PHP, multi-distro.
_LAMP_BASH = "#!/bin/bash\nset -euo pipefail\n" + _DISTRO + r"""echo "=== Installing LAMP stack ==="
pkg_refresh
pkg_install mariadb-server
svc_enable mariadb
if [ "$FAMILY" = debian ]; then
  pkg_install apache2 php php-mysql php-cli php-curl php-gd php-mbstring php-xml php-zip libapache2-mod-php
  a2enmod rewrite >/dev/null 2>&1 || true
  WEB_SVC=apache2
else
  pkg_install httpd php php-mysqlnd php-cli php-curl php-gd php-mbstring php-xml php-fpm
  svc_enable php-fpm
  WEB_SVC=httpd
fi
svc_enable "$WEB_SVC"
svc_restart "$WEB_SVC"
open_firewall 80; open_firewall 443
echo "Web server: $WEB_SVC"
echo "Database: $(mysql --version 2>/dev/null || echo MariaDB)"
echo "PHP: $(php -v 2>/dev/null | head -1)"
echo ">>> LAMP stack installed."
"""


# WordPress — Nginx + MariaDB + PHP-FPM + Let's Encrypt, multi-distro.
_WORDPRESS_BASH = "#!/bin/bash\nset -euo pipefail\n" + _DISTRO + r"""DOMAIN="{{DOMAIN}}"
DB_NAME="{{DB_NAME}}"
DB_USER="{{DB_USER}}"
DB_PASS="{{DB_PASS}}"
ADMIN_EMAIL="{{ADMIN_EMAIL}}"
WEB_ROOT="/var/www/${DOMAIN}"
echo "=== Installing dependencies ==="
pkg_refresh
pkg_install nginx
if [ "$FAMILY" = debian ]; then
  pkg_install mariadb-server php-fpm php-mysql php-cli php-curl php-gd php-mbstring php-xml php-zip wget tar
  WEB_USER=www-data
  NGINX_CONF="/etc/nginx/sites-available/${DOMAIN}"
  PHP_LOC="include snippets/fastcgi-php.conf;"
else
  pkg_install epel-release || true
  pkg_install mariadb-server php-fpm php-mysqlnd php-cli php-curl php-gd php-mbstring php-xml wget tar
  sed -i 's/^user = .*/user = nginx/; s/^group = .*/group = nginx/' /etc/php-fpm.d/www.conf 2>/dev/null || true
  WEB_USER=nginx
  NGINX_CONF="/etc/nginx/conf.d/${DOMAIN}.conf"
  PHP_LOC="include fastcgi_params; fastcgi_param SCRIPT_FILENAME \$document_root\$fastcgi_script_name;"
fi
svc_enable mariadb
svc_enable "$(php_fpm_service)"
echo "=== Setting up database ==="
mysql -e "CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
mysql -e "CREATE USER IF NOT EXISTS '${DB_USER}'@'localhost' IDENTIFIED BY '${DB_PASS}';"
mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO '${DB_USER}'@'localhost'; FLUSH PRIVILEGES;"
echo "=== Installing WordPress ==="
mkdir -p "$WEB_ROOT"
wget -q https://wordpress.org/latest.tar.gz -O /tmp/wp.tar.gz
tar -xzf /tmp/wp.tar.gz -C /tmp/
cp -r /tmp/wordpress/* "$WEB_ROOT/"
cp "${WEB_ROOT}/wp-config-sample.php" "${WEB_ROOT}/wp-config.php"
sed -i "s/database_name_here/${DB_NAME}/; s/username_here/${DB_USER}/; s/password_here/${DB_PASS}/" "${WEB_ROOT}/wp-config.php"
chown -R "${WEB_USER}:${WEB_USER}" "$WEB_ROOT"
echo "=== Configuring Nginx ==="
PHP_SOCK="$(php_fpm_socket)"
cat > "$NGINX_CONF" <<NGINX
server {
    listen 80;
    server_name ${DOMAIN};
    root ${WEB_ROOT};
    index index.php index.html;
    location / { try_files \$uri \$uri/ /index.php?\$args; }
    location ~ \.php\$ {
        ${PHP_LOC}
        fastcgi_pass unix:${PHP_SOCK};
    }
}
NGINX
if [ "$FAMILY" = debian ]; then
  ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/
  rm -f /etc/nginx/sites-enabled/default
fi
if [ "$FAMILY" = rhel ] && command -v setsebool >/dev/null 2>&1; then
  setsebool -P httpd_can_network_connect 1 2>/dev/null || true
  chcon -R -t httpd_sys_rw_content_t "$WEB_ROOT" 2>/dev/null || true
fi
open_firewall 80; open_firewall 443
if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -qE ':80[[:space:]]'; then
  who="$(ss -tlnp 2>/dev/null | grep -E ':80[[:space:]]' | grep -oE '"[^"]+"' | head -1 | tr -d '"')"
  if [ -n "$who" ] && [ "$who" != "nginx" ]; then
    echo ">>> ERROR: Port 80 is already in use by '$who' — this server isn't clean (a previous install is still running). Stop or remove it, or use a fresh server."
    exit 1
  fi
fi
nginx -t 2>/tmp/sm_nginx.log || { echo ">>> ERROR: Nginx configuration test failed:"; cat /tmp/sm_nginx.log; exit 1; }
svc_restart nginx
echo "=== Requesting SSL certificate ==="
pkg_install certbot python3-certbot-nginx || echo ">>> certbot unavailable — SSL will be skipped."
if command -v certbot >/dev/null 2>&1; then
  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL" --redirect \
    || echo ">>> SSL skipped (check the domain's DNS points to this server and the email is valid). WordPress is still reachable over http://${DOMAIN}/."
else
  echo ">>> SSL skipped — certbot not installed."
fi
echo ">>> WordPress ready: open https://${DOMAIN}/wp-admin/install.php to finish setup."
"""


# ── Server readiness check (Update 19, Tier 2) ────────────────────────────────
# The same requirements the pre-flight guard enforces, but in *report* mode: gather
# facts without installing, so the user can see whether a server is ready before a
# failed attempt.
_READINESS_SCRIPT = r'''echo "root=$([ "$(id -u)" -eq 0 ] && echo 1 || echo 0)"
ram_mb=$(free -m 2>/dev/null | awk '/^Mem:/{print $2}'); echo "ram_mb=${ram_mb:-0}"
ID=linux; PRETTY_NAME=Linux; [ -r /etc/os-release ] && . /etc/os-release; echo "os_id=${ID:-}"
echo "os_pretty=$(printf %s "${PRETTY_NAME:-Linux}" | tr -d '"')"
p=$(ss -tln 2>/dev/null | grep -cE ":80[[:space:]]"); echo "port80=${p:-0}"
who=$(ss -tlnp 2>/dev/null | grep -E ":80[[:space:]]" | grep -oE '"[^"]+"' | head -1 | tr -d '"'); echo "port80_proc=${who}"
echo "docker=$(command -v docker >/dev/null 2>&1 && echo 1 || echo 0)"
panel=""; for entry in /usr/local/cpanel:cPanel /usr/local/CyberCP:CyberPanel /usr/local/hestia:HestiaCP /usr/local/directadmin:DirectAdmin /opt/psa:Plesk /www/server/panel:aaPanel /home/clp:CloudPanel; do d="${entry%%:*}"; n="${entry##*:}"; [ -e "$d" ] && panel="$n"; done; echo "panel=${panel}"
'''


def _extract_min_ram(script: str) -> int:
    """The MIN_RAM_MB the playbook's pre-flight enforces (default 1024)."""
    m = re.search(r"MIN_RAM_MB=(\d+)", script or "")
    return int(m.group(1)) if m else 1024


def _extract_supported_os(script: str) -> list[str]:
    """Best-effort OS families from the playbook's ``case`` guard, e.g.
    'ubuntu:20.04|almalinux:8*' → ['almalinux', 'ubuntu']. Empty when none found."""
    m = re.search(r'case\s+"[^"]*ID[^"]*"\s+in\s+([^)]+)\)', script or "")
    if not m:
        return []
    return sorted(set(re.findall(r"[a-z]+", m.group(1).lower())))


_DEBIAN_FAMILY = ["ubuntu", "debian"]
_RHEL_FAMILY = ["almalinux", "rocky", "centos", "rhel", "fedora"]


def infer_supported_os(script: str) -> list[str] | None:
    """OS families a Linux playbook supports (Update 21 — per-playbook OS guard).
    Prefers an explicit ``case "${ID}"`` guard; otherwise infers from the package
    manager the script uses (apt → Debian/Ubuntu, dnf/yum → RHEL family). Returns None
    when it's OS-agnostic (uses both managers, or neither)."""
    explicit = _extract_supported_os(script)
    if explicit:
        return explicit
    s = script or ""
    uses_apt = bool(re.search(r"\bapt(-get)?\b", s))
    uses_rpm = bool(re.search(r"\b(dnf|yum|microdnf)\b", s))
    if uses_apt and not uses_rpm:
        return list(_DEBIAN_FAMILY)
    if uses_rpm and not uses_apt:
        return list(_RHEL_FAMILY)
    return None


def supported_os_for(playbook) -> list[str] | None:
    """OS families a playbook supports — its declared ``supported_os`` if set, else
    inferred from its bash script. None means OS-agnostic."""
    if playbook.supported_os:
        return [o.lower() for o in playbook.supported_os]
    return infer_supported_os(playbook.script_bash or "")


def os_matches(server, supported: list[str] | None) -> bool:
    """True if a Linux server's OS is compatible with ``supported`` (or there's no
    constraint, or the OS is unknown — never block on uncertainty). winrm/hosting
    servers are judged elsewhere and always pass here."""
    if getattr(server, "connection_type", "ssh") != "ssh" or not supported:
        return True
    os_id = (getattr(server, "os_type", "") or "").lower()
    return not os_id or os_id == "linux" or os_id in supported


async def check_readiness(server, playbook) -> dict:
    """Probe a server (no install) and report whether it meets the playbook's
    requirements as a green/red checklist (Update 19, Tier 2)."""
    from app.services import connection_manager
    out, _, _ = await connection_manager.execute(server, _READINESS_SCRIPT)
    facts: dict[str, str] = {}
    for line in out.splitlines():
        k, sep, v = line.partition("=")
        if sep:
            facts[k.strip()] = v.strip()

    script = playbook.script_bash or ""
    needs_clean = "preflight" in script  # playbook requires a fresh, empty server
    min_ram = _extract_min_ram(script)
    supported = supported_os_for(playbook)
    ram_mb = int(facts.get("ram_mb") or 0)
    os_id = (facts.get("os_id") or "").lower()
    os_pretty = facts.get("os_pretty") or os_id or "unknown"
    port80 = (facts.get("port80") or "0") != "0"
    proc = facts.get("port80_proc") or ""
    panel = facts.get("panel") or ""
    docker = (facts.get("docker") or "0") == "1"
    root = (facts.get("root") or "0") == "1"

    checks: list[dict] = [
        {"label": "Connects as root", "ok": root, "detail": None if root else "not connecting as root"},
    ]
    if needs_clean:
        checks.append({"label": "Port 80 is free", "ok": not port80,
                       "detail": (f"in use by '{proc}'" if proc else "in use") if port80 else None})
    checks.append({"label": f"At least {min_ram} MB memory", "ok": ram_mb >= min_ram,
                   "detail": f"{ram_mb} MB available"})
    if supported:
        os_ok = any(os_id == s or os_id.startswith(s) for s in supported)
        checks.append({"label": "Supported operating system", "ok": os_ok, "detail": os_pretty})
    else:
        checks.append({"label": "Operating system", "ok": True,
                       "detail": f"{os_pretty} — confirm the panel supports this"})
    if needs_clean:
        checks.append({"label": "No other control panel installed", "ok": not panel,
                       "detail": f"found {panel}" if panel else None})
        checks.append({"label": "No Docker / existing web stack", "ok": not docker,
                       "detail": "Docker is installed" if docker else None})

    return {"ready": all(c["ok"] for c in checks), "checks": checks}


# ── Non-interactive environment (Update 16, Phase A) ──────────────────────────
# Stop installers from pausing to ask questions (apt/dpkg confirmations, the
# Ubuntu "needrestart" service prompt, apt-listchanges). Injected into every bash
# playbook so a run doesn't freeze waiting for an answer the app can't give.
_NONINTERACTIVE = (
    "export DEBIAN_FRONTEND=noninteractive\n"
    "export NEEDRESTART_MODE=a\n"
    "export NEEDRESTART_SUSPEND=1\n"
    "export APT_LISTCHANGES_FRONTEND=none\n"
)


def _with_noninteractive(script: str) -> str:
    """Set a non-interactive environment after the ``set -euo pipefail`` line."""
    marker = "set -euo pipefail\n"
    idx = script.find(marker)
    if idx == -1:
        return script  # no safe insertion point — leave the script untouched
    cut = idx + len(marker)
    return script[:cut] + _NONINTERACTIVE + script[cut:]


def _script_for(item: dict) -> str | None:
    """Resolve a playbook's bash script, injecting any required preambles."""
    script = item.get("script_bash")
    if not script:
        return script
    if item.get("needs_docker"):
        script = _with_docker(script)
    if item.get("needs_preflight"):
        script = _with_preflight(script)
    script = _with_noninteractive(script)
    return script


# ── Official playbook definitions ─────────────────────────────────────────────

OFFICIAL_PLAYBOOKS: list[dict] = [

    # Adding a PHP version is additive by design: a new FPM listens on its own
    # socket and no vhost points at it yet, so nothing that already works changes.
    # Choosing which site uses it is a separate, reversible step.

    {
        "slug": "php-version",
        "title": "Install another PHP version",
        "description": "Adds a PHP version alongside the ones already here. Nothing that currently works changes \u2014 you choose afterwards which sites should use it.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 150,
        "tags": ['php', 'version', 'fpm'],
        "variables": [{'name': 'PHP_VERSION', 'label': 'Version to install (e.g. 8.3)', 'default': '8.3', 'required': True}],
        "script_bash": ("#!/bin/bash\nset -euo pipefail\n" + _DISTRO + "# supported_os: ubuntu, debian, almalinux, rocky, centos\nPHP_VERSION=\"{{PHP_VERSION}}\"\n\necho \"=== Installing PHP $PHP_VERSION ===\"\n\n# The version lands in package names, a service name and a socket path, so it is validated\n# rather than escaped.\ncase \"$PHP_VERSION\" in\n  [0-9].[0-9]|[0-9].[0-9][0-9]) : ;;\n  *) echo \">>> ERROR: '$PHP_VERSION' is not a PHP version. Use something like 8.3.\"; exit 1 ;;\nesac\n\nif [ -d \"/etc/php/$PHP_VERSION/fpm\" ] || command -v \"php$PHP_VERSION\" >/dev/null 2>&1; then\n  echo \">>> PHP $PHP_VERSION is already installed on this server.\"\n  systemctl is-active --quiet \"php$PHP_VERSION-fpm\" 2>/dev/null \\\n    && echo \">>> Its FPM service is running.\" \\\n    || { svc_enable \"php$PHP_VERSION-fpm\" 2>/dev/null || true; \\\n         echo \">>> Started its FPM service.\"; }\n  exit 0\nfi\n\npkg_refresh\nif [ \"$FAMILY\" = debian ]; then\n  # The distro ships one PHP version; anything else comes from Ond\u0159ej Sur\u00fd's archive, which\n  # is the standard source every panel uses for this.\n  if ! grep -rq \"ondrej\" /etc/apt/sources.list.d/ 2>/dev/null; then\n    echo \">>> Adding the PHP archive\"\n    pkg_install software-properties-common ca-certificates lsb-release apt-transport-https\n    LC_ALL=C.UTF-8 add-apt-repository -y ppa:ondrej/php >/dev/null 2>&1 \\\n      || { echo \">>> ERROR: could not add the PHP archive. Nothing was changed.\"; exit 1; }\n    pkg_refresh\n  fi\n  # The set a real site needs \u2014 without these a framework fails at boot with a blank page.\n  PKGS=\"php$PHP_VERSION-fpm php$PHP_VERSION-cli php$PHP_VERSION-mysql php$PHP_VERSION-mbstring\"\n  PKGS=\"$PKGS php$PHP_VERSION-xml php$PHP_VERSION-curl php$PHP_VERSION-zip php$PHP_VERSION-gd\"\n  PKGS=\"$PKGS php$PHP_VERSION-bcmath php$PHP_VERSION-intl\"\n  if ! pkg_install $PKGS; then\n    echo \">>> ERROR: PHP $PHP_VERSION could not be installed. It may not exist for this\"\n    echo \"    system yet. Nothing that was already working has changed.\"\n    exit 1\n  fi\n  SVC=\"php$PHP_VERSION-fpm\"\nelse\n  V_NODOT=\"$(echo \"$PHP_VERSION\" | tr -d '.')\"\n  pkg_install \"https://rpms.remirepo.net/enterprise/remi-release-$(rpm -E %rhel).rpm\" 2>/dev/null || true\n  \"$PM\" -y module reset php >/dev/null 2>&1 || true\n  \"$PM\" -y module enable \"php:remi-$PHP_VERSION\" >/dev/null 2>&1 || true\n  if ! pkg_install php-fpm php-cli php-mysqlnd php-mbstring php-xml php-gd php-intl; then\n    echo \">>> ERROR: PHP $PHP_VERSION could not be installed. Nothing was changed.\"\n    exit 1\n  fi\n  SVC=\"php-fpm\"\nfi\n\nsvc_enable \"$SVC\"\nif ! systemctl is-active --quiet \"$SVC\"; then\n  echo \">>> ERROR: PHP $PHP_VERSION installed but its service did not start:\"\n  journalctl -u \"$SVC\" --no-pager -n 10 2>/dev/null | tail -10 || true\n  exit 1\nfi\n\n# The socket is what a site's config will point at, so its existence is the real proof the\n# install is usable \u2014 not merely that the package installed.\nSOCK=\"/run/php/php$PHP_VERSION-fpm.sock\"\n[ \"$FAMILY\" = debian ] || SOCK=\"/run/php-fpm/www.sock\"\nfor i in 1 2 3 4 5; do [ -S \"$SOCK\" ] && break; sleep 1; done\nif [ -S \"$SOCK\" ]; then\n  echo \">>> PHP $PHP_VERSION is running and ready at $SOCK\"\nelse\n  echo \">>> Note: PHP $PHP_VERSION is running but its socket is not at the usual path.\"\n  echo \"    Sites can still be pointed at it, but check the FPM pool configuration.\"\nfi\n\necho \"\"\necho \"=== PHP $PHP_VERSION is installed ===\"\necho \"Installed versions now: $(ls -1 /etc/php 2>/dev/null | tr '\\n' ' ')\"\necho \"Nothing changed for your existing sites \u2014 they keep the version they had.\"\necho \"Next: choose which sites should use $PHP_VERSION on the PHP page.\"\n"),
    },

    # Laravel is a website in shape but its document root is public/, not the
    # project folder — serving the project folder would make .env and the whole
    # codebase downloadable. Guards come from _SITE_GUARDS, so this costs no
    # duplication.

    {
        "slug": "laravel-site",
        "title": "Laravel application",
        "description": "A fresh Laravel install with its own database, key, and correct permissions \u2014 ready to open in the browser or replace with your own repository.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 180,
        "tags": ['laravel', 'php', 'composer', 'website'],
        "variables": [{'name': 'DOMAIN', 'label': 'Domain (e.g. app.example.com)', 'default': '', 'required': True}, {'name': 'WEB_ROOT', 'label': 'Where sites live on this server', 'default': '/var/www', 'required': True}, {'name': 'DB_NAME', 'label': 'Database name', 'default': 'laravel', 'required': True}, {'name': 'DB_USER', 'label': 'Database user', 'default': 'laravel', 'required': True}],
        "access_info": {'name': '{{DOMAIN}}', 'url': 'http://{{DOMAIN}}', 'note': "Code in {{WEB_ROOT}}/{{DOMAIN}}. The database password is in /root/{{DOMAIN}}_db.txt (readable by root only) and already written into the app's .env."},
        "script_bash": ("#!/bin/bash\nset -euo pipefail\n" + _DISTRO + "# supported_os: ubuntu, debian, almalinux, rocky, centos\nDOMAIN=\"{{DOMAIN}}\"\nWEB_ROOT=\"{{WEB_ROOT}}\"\nDB_NAME=\"{{DB_NAME}}\"\nDB_USER=\"{{DB_USER}}\"\n\necho \"=== Installing Laravel at $DOMAIN ===\"\n\n" + _SITE_GUARDS + "\n\ncase \"$WEB_ROOT\" in\n  /*) : ;;\n  *) echo \">>> ERROR: the sites folder must be an absolute path, not '$WEB_ROOT'.\"; exit 1 ;;\nesac\n# These end up in SQL and in a systemd-free but still quoted context, so they are validated\n# the same way the domain is rather than escaped.\nfor _v in \"$DB_NAME\" \"$DB_USER\"; do\n  case \"$_v\" in\n    \"\"|*[!a-zA-Z0-9_]*)\n      echo \">>> ERROR: '$_v' is not a valid database name or user \u2014 letters, numbers and\"\n      echo \"    underscores only. Nothing was changed.\"\n      exit 1 ;;\n  esac\ndone\n\nSITE_DIR=\"$WEB_ROOT/$DOMAIN\"\nDOC_ROOT=\"$SITE_DIR/public\"\nif [ -e \"$SITE_DIR\" ]; then\n  echo \">>> ERROR: $SITE_DIR already exists. Nothing was changed.\"\n  exit 1\nfi\n\ncommand -v php >/dev/null 2>&1 || {\n  echo \">>> ERROR: PHP is not installed. Set the server up first, then install Laravel.\"\n  exit 1; }\ncommand -v composer >/dev/null 2>&1 || {\n  echo \">>> ERROR: Composer is not installed, and Laravel cannot be installed without it.\"\n  echo \"    Run the Composer installer on this server first.\"\n  exit 1; }\n\n# The PHP version decides whether this can work at all, so it is checked before anything\n# is created. Ubuntu 22.04 ships PHP 8.1; current Laravel needs 8.3+, and Composer will\n# fall back to Laravel 10 \u2014 whose every release now carries a security advisory, which\n# Composer refuses to install by default. The result is a 200-line dependency error that\n# says nothing useful. One sentence up front is better.\nPHP_MM=\"$(php -r 'echo PHP_MAJOR_VERSION . \".\" . PHP_MINOR_VERSION;' 2>/dev/null || echo 0.0)\"\nPHP_OK=\"$(php -r 'echo (PHP_VERSION_ID >= 80300) ? \"yes\" : \"no\";' 2>/dev/null || echo no)\"\nif [ \"$PHP_OK\" != yes ]; then\n  echo \">>> ERROR: this server has PHP $PHP_MM, and Laravel needs PHP 8.3 or newer.\"\n  echo \"    Older Laravel versions that would run on PHP $PHP_MM all have known security\"\n  echo \"    problems, so installing one would not be safe. Install a newer PHP on this\"\n  echo \"    server first, then try again. Nothing was changed.\"\n  exit 1\nfi\necho \">>> PHP $PHP_MM is new enough for Laravel\"\n\n# Laravel refuses to boot without these, and the failure is a blank page rather than a\n# message, so they are checked up front and installed if the distro has them.\nMISSING=\"\"\nfor EXT in mbstring xml curl zip; do\n  php -m 2>/dev/null | grep -qi \"^$EXT$\" || MISSING=\"$MISSING $EXT\"\ndone\nif [ -n \"$MISSING\" ]; then\n  echo \">>> Installing missing PHP extensions:$MISSING\"\n  pkg_refresh\n  if [ \"$FAMILY\" = debian ]; then\n    PHPV=\"$(php_fpm_ver)\"\n    for EXT in $MISSING; do\n      pkg_install \"php${PHPV}-${EXT}\" 2>/dev/null || pkg_install \"php-${EXT}\" 2>/dev/null || true\n    done\n  else\n    for EXT in $MISSING; do pkg_install \"php-${EXT}\" 2>/dev/null || true; done\n  fi\n  FPM=\"$(php_fpm_service)\"\n  systemctl is-active --quiet \"$FPM\" 2>/dev/null && svc_restart \"$FPM\" || true\nfi\n\nDB_OK=no\nif command -v mysql >/dev/null 2>&1 && mysql -e \"SELECT 1\" >/dev/null 2>&1; then DB_OK=yes; fi\nif [ \"$DB_OK\" = no ]; then\n  echo \">>> ERROR: cannot reach MySQL/MariaDB as root on this server, so the database\"\n  echo \"    cannot be created. Set the server up first. Nothing was changed.\"\n  exit 1\nfi\nif mysql -N -e \"SHOW DATABASES LIKE '$DB_NAME'\" 2>/dev/null | grep -q .; then\n  echo \">>> ERROR: a database called '$DB_NAME' already exists. Choose another name so an\"\n  echo \"    existing application's data is not touched. Nothing was changed.\"\n  exit 1\nfi\n\n# Generated on the server and never printed into the chat \u2014 written to a root-only file.\nDB_PASS=\"$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 24)\"\n\necho \">>> Downloading Laravel (this is the slow part)\"\n# Composer as root is normally refused; the alternative is a home directory for the web\n# user, which is more moving parts. The tree is chowned to the web user straight after, so\n# nothing is left owned by root.\nexport COMPOSER_ALLOW_SUPERUSER=1\nexport COMPOSER_HOME=/tmp/composer-serverally\nmkdir -p \"$COMPOSER_HOME\"\nif ! composer create-project --no-interaction --prefer-dist laravel/laravel \"$SITE_DIR\" \\\n     >/tmp/sm_laravel.log 2>&1; then\n  echo \">>> ERROR: Laravel could not be downloaded. Last lines:\"\n  tail -15 /tmp/sm_laravel.log\n  rm -rf \"$SITE_DIR\"\n  echo \">>> Removed the half-made folder. Nothing else was changed.\"\n  exit 1\nfi\necho \">>> Laravel downloaded to $SITE_DIR\"\n\nmysql -e \"CREATE DATABASE \\`$DB_NAME\\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;\"\nmysql -e \"CREATE USER '$DB_USER'@'localhost' IDENTIFIED BY '$DB_PASS';\"\n# Rights on this one database only \u2014 never the whole server, and never the root account.\nmysql -e \"GRANT ALL PRIVILEGES ON \\`$DB_NAME\\`.* TO '$DB_USER'@'localhost';\"\nmysql -e \"FLUSH PRIVILEGES;\"\nprintf 'Laravel database for %s\\n\\ndatabase: %s\\nuser:     %s\\npassword: %s\\n' \\\n  \"$DOMAIN\" \"$DB_NAME\" \"$DB_USER\" \"$DB_PASS\" > /root/\"$DOMAIN\"_db.txt\nchmod 600 /root/\"$DOMAIN\"_db.txt\necho \">>> Database $DB_NAME created (password saved to /root/${DOMAIN}_db.txt, root only)\"\n\nENVF=\"$SITE_DIR/.env\"\n[ -f \"$ENVF\" ] || cp \"$SITE_DIR/.env.example\" \"$ENVF\" 2>/dev/null || touch \"$ENVF\"\nset_env() {\n  if grep -qE \"^$1=\" \"$ENVF\"; then\n    sed -i -E \"s|^$1=.*|$1=$2|\" \"$ENVF\"\n  else\n    printf '%s=%s\\n' \"$1\" \"$2\" >> \"$ENVF\"\n  fi\n}\nset_env APP_ENV production\nset_env APP_DEBUG false\nset_env APP_URL \"http://$DOMAIN\"\nset_env DB_CONNECTION mysql\nset_env DB_HOST 127.0.0.1\nset_env DB_PORT 3306\nset_env DB_DATABASE \"$DB_NAME\"\nset_env DB_USERNAME \"$DB_USER\"\nset_env DB_PASSWORD \"$DB_PASS\"\n\n# Without a key every encrypted cookie and session in the app breaks.\n( cd \"$SITE_DIR\" && php artisan key:generate --force >/dev/null 2>&1 ) \\\n  && echo \">>> Application key generated\" \\\n  || echo \">>> Note: could not generate the application key \u2014 run 'php artisan key:generate' in $SITE_DIR\"\n\n# Laravel 11+ defaults SESSION_DRIVER=database, so the very FIRST request reads a\n# `sessions` table. Without the schema the site 500s with \"Table ... doesn't exist\" \u2014 a\n# fresh install that looks broken. Running the migrations also proves the credentials we\n# just wrote into .env actually work, which nothing else here would confirm.\nif ( cd \"$SITE_DIR\" && php artisan migrate --force >/tmp/sm_migrate.log 2>&1 ); then\n  echo \">>> Database tables created\"\nelse\n  echo \">>> ERROR: could not create the database tables. The site will not load until this\"\n  echo \"    is fixed. Last lines:\"\n  tail -10 /tmp/sm_migrate.log\n  echo \">>> Everything else is in place \u2014 run 'php artisan migrate' in $SITE_DIR once the\"\n  echo \"    database problem is resolved.\"\nfi\n\nchown -R \"$WEB_USER\":\"$WEB_USER\" \"$SITE_DIR\"\nfind \"$SITE_DIR\" -type d -exec chmod 755 {} \\;\nfind \"$SITE_DIR\" -type f -exec chmod 644 {} \\;\n# These two are the ones Laravel writes to at runtime. If they are not writable the very\n# first request is a 500 with nothing useful on screen.\nchmod -R 775 \"$SITE_DIR/storage\" \"$SITE_DIR/bootstrap/cache\" 2>/dev/null || true\n# .env holds the database password, so it is not world-readable like the rest of the tree.\nchmod 640 \"$ENVF\"\necho \">>> Permissions set (storage and bootstrap/cache writable, .env kept private)\"\n\nINDEX=\"index.php index.html\"\nPHP_BLOCK_N=\"\"\nPHP_BLOCK_A=\"\"\nif [ \"$NGINX\" = yes ]; then\n  SOCK=\"$(php_fpm_socket)\"\n  PHP_BLOCK_N=\"    location ~ \\.php\\$ {\n        include fastcgi_params;\n        fastcgi_param SCRIPT_FILENAME \\$document_root\\$fastcgi_script_name;\n        fastcgi_pass unix:$SOCK;\n        fastcgi_index index.php;\n    }\"\nelse\n  PHP_BLOCK_A=\"    <FilesMatch \\.php\\$>\n        SetHandler \\\"proxy:unix:$(php_fpm_socket)|fcgi://localhost\\\"\n    </FilesMatch>\"\nfi\n\n# The document root is public/, NOT the project folder. Serving the project folder would\n# make .env, the whole codebase and the vendor tree downloadable over HTTP \u2014 the single\n# worst mistake available when hosting a Laravel app.\nif [ \"$NGINX\" = yes ]; then\n  cat > \"$SITE_CONF\" <<NGEOF\n# Created by ServerAlly \u2014 Laravel $DOMAIN\nserver {\n    listen 80;\n    listen [::]:80;\n    server_name $DOMAIN;\n    root $DOC_ROOT;\n    index $INDEX;\n\n    add_header X-Frame-Options \"SAMEORIGIN\";\n    add_header X-Content-Type-Options \"nosniff\";\n    charset utf-8;\n\n    location / {\n        try_files \\$uri \\$uri/ /index.php?\\$query_string;\n    }\n$PHP_BLOCK_N\n    location = /favicon.ico { access_log off; log_not_found off; }\n    location = /robots.txt  { access_log off; log_not_found off; }\n    location ~ /\\.(?!well-known).* { deny all; }\n\n    error_log /var/log/nginx/$DOMAIN-error.log error;\n    access_log /var/log/nginx/$DOMAIN-access.log;\n}\nNGEOF\nelse\n  cat > \"$SITE_CONF\" <<APEOF\n# Created by ServerAlly \u2014 Laravel $DOMAIN\n<VirtualHost *:80>\n    ServerName $DOMAIN\n    DocumentRoot $DOC_ROOT\n    DirectoryIndex $INDEX\n\n    <Directory $DOC_ROOT>\n        AllowOverride All\n        Require all granted\n    </Directory>\n$PHP_BLOCK_A\n    ErrorLog \\${APACHE_LOG_DIR}/$DOMAIN-error.log\n    CustomLog \\${APACHE_LOG_DIR}/$DOMAIN-access.log combined\n</VirtualHost>\nAPEOF\nfi\necho \">>> Wrote $SITE_CONF (document root is public/, so the code itself is not downloadable)\"\n\napply_web_config\n\n# A 200 is not proof: a broken Laravel returns 500, and an empty docroot returns a\n# directory listing. Look for something only a working Laravel page contains.\nif verify_serves \"Laravel\"; then\n  echo \">>> Verified: Laravel is serving at $DOMAIN.\"\nelse\n  CODE=\"$(curl -s -o /dev/null -w \"%{http_code}\" --max-time 8 -H \"Host: $DOMAIN\" http://127.0.0.1/ 2>/dev/null || echo 000)\"\n  echo \">>> The site is configured but did not return a Laravel page (HTTP $CODE).\"\n  echo \"    Most often this is a permissions problem on storage/. Its error log:\"\n  tail -8 \"$SITE_DIR/storage/logs/laravel.log\" 2>/dev/null || tail -8 /var/log/nginx/\"$DOMAIN\"-error.log 2>/dev/null || true\nfi\n\necho \"\"\necho \"=== Laravel is installed at $DOMAIN ===\"\necho \"Code:      $SITE_DIR\"\necho \"Serves:    $DOC_ROOT\"\necho \"Database:  $DB_NAME (user $DB_USER)\"\necho \"Password:  /root/${DOMAIN}_db.txt \u2014 root only, already in the app's .env\"\necho \"Next:      point the domain's DNS here, then add HTTPS.\"\n"),
    },

    # Two installers that put something on a domain. Their shared checks live in
    # _SITE_GUARDS rather than being copied, because writing a web-server config is the
    # one thing here that can take down sites unrelated to the one being added — and the
    # copy that drifts is the one that forgets to test the config before reloading.

    {
        "slug": "create-site",
        "title": "Create a website (empty)",
        "description": "Makes a folder, a web address and a working PHP page \u2014 ready for your own files, a Git deploy, or a WordPress install. No database is created.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 30,
        "tags": ['website', 'nginx', 'apache', 'vhost', 'php'],
        "variables": [{'name': 'DOMAIN', 'label': 'Domain (e.g. shop.example.com)', 'default': '', 'required': True}, {'name': 'WEB_ROOT', 'label': 'Where sites live on this server', 'default': '/var/www', 'required': True}, {'name': 'WITH_PHP', 'label': 'Serve PHP (yes/no)', 'default': 'yes', 'required': True}],
        "access_info": {'name': '{{DOMAIN}}', 'url': 'http://{{DOMAIN}}', 'note': "Files go in {{WEB_ROOT}}/{{DOMAIN}}/public. Point the domain's DNS at this server, then add HTTPS."},
        "script_bash": ("#!/bin/bash\nset -euo pipefail\n" + _DISTRO + "# supported_os: ubuntu, debian, almalinux, rocky, centos\nDOMAIN=\"{{DOMAIN}}\"\nWEB_ROOT=\"{{WEB_ROOT}}\"\nWITH_PHP=\"{{WITH_PHP}}\"\n\necho \"=== Creating the website $DOMAIN ===\"\n\n" + _SITE_GUARDS + "\n\ncase \"$WEB_ROOT\" in\n  /*) : ;;\n  *) echo \">>> ERROR: the sites folder must be an absolute path, not '$WEB_ROOT'.\"; exit 1 ;;\nesac\n\nSITE_DIR=\"$WEB_ROOT/$DOMAIN\"\nDOC_ROOT=\"$SITE_DIR/public\"\nif [ -e \"$SITE_DIR\" ]; then\n  echo \">>> ERROR: $SITE_DIR already exists. Nothing was changed.\"\n  exit 1\nfi\n\necho \">>> Web server runs as $WEB_USER\"\n\nmkdir -p \"$DOC_ROOT\"\ncat > \"$DOC_ROOT/index.html\" <<HTMLEOF\n<!doctype html>\n<html lang=\"en\"><head><meta charset=\"utf-8\">\n<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n<meta name=\"robots\" content=\"noindex\">\n<title>$DOMAIN is ready</title>\n<style>body{font-family:system-ui,sans-serif;margin:0;display:grid;place-items:center;\nmin-height:100vh;background:#f8fafc;color:#0f172a}div{max-width:32rem;padding:2rem}\nh1{font-size:1.25rem;margin:0 0 .5rem}p{color:#475569;line-height:1.6;margin:0}</style>\n</head><body><div>\n<h1>$DOMAIN is ready</h1>\n<p>This website was created by ServerAlly and has no content yet. Upload your files to\nthis folder, deploy from Git, or install WordPress into it.</p>\n</div></body></html>\nHTMLEOF\nchown -R \"$WEB_USER\":\"$WEB_USER\" \"$SITE_DIR\"\nfind \"$SITE_DIR\" -type d -exec chmod 755 {} \\;\nfind \"$SITE_DIR\" -type f -exec chmod 644 {} \\;\necho \">>> Created $DOC_ROOT\"\n\nPHP_BLOCK_N=\"\"\nPHP_BLOCK_A=\"\"\nINDEX=\"index.html\"\nif [ \"$WITH_PHP\" = yes ] && command -v php >/dev/null 2>&1; then\n  INDEX=\"index.php index.html\"\n  if [ \"$NGINX\" = yes ]; then\n    # Never a hardcoded version: a wrong socket path makes the server hand out PHP SOURCE\n    # as plain text, which leaks database credentials to anyone who visits.\n    SOCK=\"$(php_fpm_socket)\"\n    echo \">>> PHP will be served through $SOCK\"\n    PHP_BLOCK_N=\"    location ~ \\.php\\$ {\n        include fastcgi_params;\n        fastcgi_param SCRIPT_FILENAME \\$document_root\\$fastcgi_script_name;\n        fastcgi_pass unix:$SOCK;\n        fastcgi_index index.php;\n    }\"\n  else\n    PHP_BLOCK_A=\"    <FilesMatch \\.php\\$>\n        SetHandler \\\"proxy:unix:$(php_fpm_socket)|fcgi://localhost\\\"\n    </FilesMatch>\"\n  fi\nelif [ \"$WITH_PHP\" = yes ]; then\n  echo \">>> Note: PHP is not installed, so this site will serve static files only.\"\nfi\n\nif [ \"$NGINX\" = yes ]; then\n  cat > \"$SITE_CONF\" <<NGEOF\n# Created by ServerAlly for $DOMAIN\nserver {\n    listen 80;\n    listen [::]:80;\n    server_name $DOMAIN;\n    root $DOC_ROOT;\n    index $INDEX;\n\n    add_header X-Frame-Options \"SAMEORIGIN\";\n    add_header X-Content-Type-Options \"nosniff\";\n    charset utf-8;\n\n    location / {\n        try_files \\$uri \\$uri/ /index.php?\\$query_string;\n    }\n$PHP_BLOCK_N\n    location = /favicon.ico { access_log off; log_not_found off; }\n    location = /robots.txt  { access_log off; log_not_found off; }\n    location ~ /\\.(?!well-known).* { deny all; }\n\n    error_log /var/log/nginx/$DOMAIN-error.log error;\n    access_log /var/log/nginx/$DOMAIN-access.log;\n}\nNGEOF\nelse\n  cat > \"$SITE_CONF\" <<APEOF\n# Created by ServerAlly for $DOMAIN\n<VirtualHost *:80>\n    ServerName $DOMAIN\n    DocumentRoot $DOC_ROOT\n    DirectoryIndex $INDEX\n\n    <Directory $DOC_ROOT>\n        AllowOverride All\n        Require all granted\n    </Directory>\n$PHP_BLOCK_A\n    ErrorLog \\${APACHE_LOG_DIR}/$DOMAIN-error.log\n    CustomLog \\${APACHE_LOG_DIR}/$DOMAIN-access.log combined\n</VirtualHost>\nAPEOF\nfi\necho \">>> Wrote $SITE_CONF\"\n\napply_web_config\n\nif verify_serves \"$DOMAIN is ready\"; then\n  echo \">>> Verified: the server is serving this site.\"\nelse\n  echo \">>> Note: the site is configured but the placeholder page did not come back from\"\n  echo \"    127.0.0.1. If another site is the default for this server that can be normal;\"\n  echo \"    check again once DNS points here.\"\nfi\n\necho \"\"\necho \"=== $DOMAIN is set up ===\"\necho \"Files:   $DOC_ROOT\"\necho \"Config:  $SITE_CONF\"\necho \"Next:    point the domain's DNS at this server, then add HTTPS.\"\n"),
    },

    {
        "slug": "create-app",
        "title": "Host a web application",
        "description": "For a Node, Python, Go or Laravel-queue style app: points a domain at your running program and keeps it alive across crashes and reboots. No database is created.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 40,
        "tags": ['application', 'nodejs', 'python', 'proxy', 'systemd'],
        "variables": [{'name': 'DOMAIN', 'label': 'Domain (e.g. app.example.com)', 'default': '', 'required': True}, {'name': 'APP_PORT', 'label': 'Port your app listens on', 'default': '3000', 'required': True}, {'name': 'APP_DIR', 'label': 'Folder the app runs from', 'default': '/var/www', 'required': True}, {'name': 'START_CMD', 'label': 'Command that starts it (leave blank to set up later)', 'default': '', 'required': False}, {'name': 'RUN_AS', 'label': 'Run the app as this user', 'default': 'www-data', 'required': True}],
        "access_info": {'name': '{{DOMAIN}}', 'url': 'http://{{DOMAIN}}', 'note': 'Your code goes in {{APP_DIR}}/{{DOMAIN}}. The service is called app-{{DOMAIN}} — check it with: systemctl status app-{{DOMAIN}}'},
        "script_bash": ("#!/bin/bash\nset -euo pipefail\n" + _DISTRO + "# supported_os: ubuntu, debian, almalinux, rocky, centos\nDOMAIN=\"{{DOMAIN}}\"\nAPP_PORT=\"{{APP_PORT}}\"\nAPP_DIR=\"{{APP_DIR}}\"\nSTART_CMD=\"{{START_CMD}}\"\nRUN_AS=\"{{RUN_AS}}\"\n\necho \"=== Hosting the web application $DOMAIN ===\"\n\n" + _SITE_GUARDS + "\n\n# The port lands in a config file and a systemd unit, so it is validated the same way the\n# domain is \u2014 refused rather than escaped.\ncase \"$APP_PORT\" in\n  \"\"|*[!0-9]*) echo \">>> ERROR: '$APP_PORT' is not a port number.\"; exit 1 ;;\nesac\nif [ \"$APP_PORT\" -lt 1 ] || [ \"$APP_PORT\" -gt 65535 ]; then\n  echo \">>> ERROR: port $APP_PORT is outside the valid range.\"; exit 1\nfi\n# 80 and 443 belong to the web server that is about to proxy TO the app. Pointing the proxy\n# at itself makes an infinite loop that takes the whole web server down.\nif [ \"$APP_PORT\" = 80 ] || [ \"$APP_PORT\" = 443 ]; then\n  echo \">>> ERROR: port $APP_PORT is the web server's own port. Your app must listen on a\"\n  echo \"    different port (3000 is usual) \u2014 the web server forwards to it. Nothing changed.\"\n  exit 1\nfi\ncase \"$APP_DIR\" in\n  /*) : ;;\n  *) echo \">>> ERROR: the app folder must be an absolute path, not '$APP_DIR'.\"; exit 1 ;;\nesac\nif ! id -u \"$RUN_AS\" >/dev/null 2>&1; then\n  echo \">>> ERROR: there is no user called '$RUN_AS' on this server. Nothing was changed.\"\n  exit 1\nfi\n\n# Another app already proxied to this port would mean two domains silently serving the same\n# program \u2014 confusing rather than broken, but not what anyone asked for.\nif grep -rls \"127.0.0.1:$APP_PORT\" /etc/nginx /etc/apache2 /etc/httpd 2>/dev/null | head -1 | grep -q .; then\n  echo \">>> Note: something else on this server already forwards to port $APP_PORT.\"\n  echo \"    Continuing \u2014 but check you meant to share it.\"\nfi\n\nAPP_ROOT=\"$APP_DIR/$DOMAIN\"\nUNIT=\"app-$DOMAIN\"\n\nmkdir -p \"$APP_ROOT\"\nchown -R \"$RUN_AS\":\"$RUN_AS\" \"$APP_ROOT\"\necho \">>> App folder: $APP_ROOT (owned by $RUN_AS)\"\n\n# \u2500\u2500 the reverse proxy \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nif [ \"$NGINX\" = yes ]; then\n  cat > \"$SITE_CONF\" <<NGEOF\n# Created by ServerAlly \u2014 web application $DOMAIN\nserver {\n    listen 80;\n    listen [::]:80;\n    server_name $DOMAIN;\n\n    add_header X-Frame-Options \"SAMEORIGIN\";\n    add_header X-Content-Type-Options \"nosniff\";\n    charset utf-8;\n\n    location / {\n        proxy_pass http://127.0.0.1:$APP_PORT;\n        proxy_http_version 1.1;\n        # These four are what make WebSockets work through the proxy. Without them a\n        # realtime app connects, gets upgraded, and is cut off immediately.\n        proxy_set_header Upgrade \\$http_upgrade;\n        proxy_set_header Connection \"upgrade\";\n        proxy_set_header Host \\$host;\n        proxy_cache_bypass \\$http_upgrade;\n        # So the app sees the visitor's address rather than the proxy's.\n        proxy_set_header X-Real-IP \\$remote_addr;\n        proxy_set_header X-Forwarded-For \\$proxy_add_x_forwarded_for;\n        proxy_set_header X-Forwarded-Proto \\$scheme;\n        proxy_read_timeout 60s;\n    }\n\n    error_log /var/log/nginx/$DOMAIN-error.log error;\n    access_log /var/log/nginx/$DOMAIN-access.log;\n}\nNGEOF\nelse\n  cat > \"$SITE_CONF\" <<APEOF\n# Created by ServerAlly \u2014 web application $DOMAIN\n<VirtualHost *:80>\n    ServerName $DOMAIN\n    ProxyPreserveHost On\n    ProxyPass / http://127.0.0.1:$APP_PORT/\n    ProxyPassReverse / http://127.0.0.1:$APP_PORT/\n    # WebSocket upgrade, same reason as the nginx side.\n    RewriteEngine On\n    RewriteCond %{HTTP:Upgrade} =websocket [NC]\n    RewriteRule /(.*) ws://127.0.0.1:$APP_PORT/\\$1 [P,L]\n    ErrorLog \\${APACHE_LOG_DIR}/$DOMAIN-error.log\n    CustomLog \\${APACHE_LOG_DIR}/$DOMAIN-access.log combined\n</VirtualHost>\nAPEOF\n  # Apache cannot proxy at all without these, and the failure is a confusing 500 rather\n  # than a clear message, so they are enabled before the config is tested.\n  for _m in proxy proxy_http rewrite proxy_wstunnel; do\n    command -v a2enmod >/dev/null 2>&1 && a2enmod \"$_m\" >/dev/null 2>&1 || true\n  done\nfi\necho \">>> Wrote $SITE_CONF (forwarding $DOMAIN to 127.0.0.1:$APP_PORT)\"\n\napply_web_config\n\n# \u2500\u2500 the thing that keeps it running \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nif [ -n \"$START_CMD\" ]; then\n  cat > /etc/systemd/system/\"$UNIT\".service <<UNITEOF\n[Unit]\nDescription=$DOMAIN (managed by ServerAlly)\nAfter=network.target\n# These two belong in [Unit], NOT [Service] \u2014 systemd silently ignores them under\n# [Service] (\"Unknown key name\"), which means the crash-loop protection would look\n# present and do nothing. Caught by systemd-analyze verify after a test kill showed\n# 12 restarts with no limit ever applied.\nStartLimitBurst=5\nStartLimitIntervalSec=60\n\n[Service]\nType=simple\nUser=$RUN_AS\nWorkingDirectory=$APP_ROOT\n# `exec` matters: without it bash stays as the service's main process and the real app\n# is only its child. systemd would then watch the wrapper rather than the program \u2014\n# and stopping the service orphans the app, which keeps holding the port so the restart\n# fails with \"address already in use\". With exec, the app IS the main process.\n# -l keeps a login shell so PATH-managed runtimes (nvm, pyenv, rbenv) resolve.\nExecStart=/bin/bash -lc 'exec $START_CMD'\nRestart=always\nRestartSec=5\nStandardOutput=journal\nStandardError=journal\nEnvironment=NODE_ENV=production\nEnvironment=PORT=$APP_PORT\n\n[Install]\nWantedBy=multi-user.target\nUNITEOF\n  systemctl daemon-reload\n  systemctl enable \"$UNIT\" >/dev/null 2>&1 || true\n  systemctl restart \"$UNIT\" || true\n  sleep 3\n  if systemctl is-active --quiet \"$UNIT\"; then\n    echo \">>> Service $UNIT is running and will start again on boot.\"\n  else\n    # Honest rather than silent: the proxy is correct, the app is not running, and the\n    # reason is in its own log.\n    echo \">>> The service $UNIT did not stay running. The web address is set up correctly,\"\n    echo \"    but your app is not answering yet. Its last output:\"\n    journalctl -u \"$UNIT\" --no-pager -n 12 2>/dev/null | tail -12 || true\n    echo \">>> Fix the start command, then: systemctl restart $UNIT\"\n  fi\nelse\n  echo \">>> No start command given, so no service was created. The web address is ready and\"\n  echo \"    forwards to port $APP_PORT \u2014 start your app on that port, or add the service later.\"\nfi\n\n# \u2500\u2500 does it actually answer? \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\nCODE=\"$(curl -s -o /dev/null -w \"%{http_code}\" --max-time 8 -H \"Host: $DOMAIN\" http://127.0.0.1/ 2>/dev/null || echo 000)\"\ncase \"$CODE\" in\n  502|504)\n    echo \">>> The domain works but nothing is listening on port $APP_PORT yet \u2014 that is what\"\n    echo \"    a 502 means here. Start your app on that port and it will come to life.\" ;;\n  000)\n    echo \">>> Could not reach the web server locally to check. Try the domain in a browser.\" ;;\n  *)\n    echo \">>> Verified: $DOMAIN answered with HTTP $CODE through the proxy.\" ;;\nesac\n\necho \"\"\necho \"=== $DOMAIN is set up as a web application ===\"\necho \"Code:     $APP_ROOT\"\necho \"Proxy:    $DOMAIN \u2192 127.0.0.1:$APP_PORT\"\n[ -n \"$START_CMD\" ] && echo \"Service:  systemctl status $UNIT\"\necho \"Next:     point the domain's DNS here, then add HTTPS.\"\n"),
    },

    # The missing primitive. Ploi's "Add site" makes a folder, a web-server
    # config and a placeholder page — nothing more; WordPress is a separate
    # installer run INTO that site. We had only the WordPress-shaped path, so
    # "give me a website for my own files" had no code route at all.


    # ── Added after benchmarking a live Ploi provision (26 tasks) and
    # reading the finished machine: everything a website server needs that
    # we did not have. Without Composer and Node our OWN deploy pipeline
    # could not build a PHP or JavaScript app on a server our OWN setup
    # wizard had just finished.

    {
        'slug': 'composer',
        'title': 'Composer (PHP dependency manager)',
        'description': 'Installs Composer 2 globally. Every modern PHP application — Laravel, Symfony, most WordPress plugins built this decade — needs it to install.',
        'category': 'setup',
        'os_family': 'linux',
        'script_type': 'bash',
        'est_runtime_sec': 45,
        'tags': ['php', 'composer', 'laravel'],
        'variables': [],
        "script_bash": ('#!/bin/bash\nset -euo pipefail\n# supported_os: ubuntu, debian, almalinux, rocky, centos\necho "=== Installing Composer ==="\nif command -v composer >/dev/null 2>&1; then\n  echo ">>> Composer is already installed: $(composer --version 2>/dev/null | head -1)"\n  exit 0\nfi\nif ! command -v php >/dev/null 2>&1; then\n  echo ">>> ERROR: PHP is not installed. Install the web stack first — Composer is a PHP program and cannot run without it."\n  exit 1\nfi\n\n# The installer is fetched over the network and then run as root, so its\n# signature is checked against the published hash BEFORE it executes. Piping\n# an unverified script straight into php would mean anyone who could tamper\n# with that download owns the server.\ncd /tmp\nEXPECTED="$(curl -fsSL https://composer.github.io/installer.sig)"\nphp -r "copy(\'https://getcomposer.org/installer\', \'/tmp/composer-setup.php\');"\nACTUAL="$(php -r "echo hash_file(\'sha384\', \'/tmp/composer-setup.php\');")"\nif [ "$EXPECTED" != "$ACTUAL" ]; then\n  rm -f /tmp/composer-setup.php\n  echo ">>> ERROR: the Composer installer did not match its published signature. Nothing was installed. This is either a corrupted download or someone tampering with it — try again, and if it repeats, stop and ask."\n  exit 1\nfi\nphp /tmp/composer-setup.php --quiet --install-dir=/usr/local/bin --filename=composer\nrm -f /tmp/composer-setup.php\n\ncommand -v composer >/dev/null 2>&1 || { echo ">>> ERROR: Composer did not install."; exit 1; }\necho ">>> Composer ready: $(composer --version | head -1)"\n'),
    },

    {
        'slug': 'supervisor',
        'title': 'Supervisor (keeps background jobs running)',
        'description': 'Installs Supervisor, which restarts background workers when they stop. Laravel queues, scheduled jobs and long-running scripts need it.',
        'category': 'setup',
        'os_family': 'linux',
        'script_type': 'bash',
        'est_runtime_sec': 45,
        'tags': ['supervisor', 'queue', 'laravel', 'workers'],
        'variables': [],
        "script_bash": ('#!/bin/bash\nset -euo pipefail\n# supported_os: ubuntu, debian, almalinux, rocky, centos\n' + _DISTRO + 'echo "=== Installing Supervisor ==="\nif command -v supervisord >/dev/null 2>&1; then\n  echo ">>> Supervisor is already installed."\nelse\n  pkg_refresh\n  pkg_install supervisor\nfi\n# Debian calls the unit supervisor, RHEL calls it supervisord.\nUNIT=supervisor\nsystemctl list-unit-files --no-legend \'supervisor.service\' 2>/dev/null | grep -q . || UNIT=supervisord\nmkdir -p /etc/supervisor/conf.d 2>/dev/null || true\nsvc_enable "$UNIT"\nsystemctl is-active --quiet "$UNIT" || { echo ">>> ERROR: Supervisor installed but is not running."; exit 1; }\necho ">>> Supervisor is running. Worker configs go in /etc/supervisor/conf.d."\n'),
    },

    {
        'slug': 'redis-cache',
        'title': 'Redis + Memcached (makes sites faster)',
        'description': 'Installs Redis and Memcached for caching and sessions, both listening only on this server. WordPress and Laravel are noticeably faster with them.',
        'category': 'setup',
        'os_family': 'linux',
        'script_type': 'bash',
        'est_runtime_sec': 60,
        'tags': ['redis', 'memcached', 'cache', 'performance'],
        'variables': [],
        "script_bash": ('#!/bin/bash\nset -euo pipefail\n# supported_os: ubuntu, debian, almalinux, rocky, centos\n' + _DISTRO + 'echo "=== Installing Redis and Memcached ==="\npkg_refresh\nif [ "$FAMILY" = debian ]; then\n  pkg_install redis-server memcached\n  REDIS_UNIT=redis-server\n  REDIS_CONF=/etc/redis/redis.conf\nelse\n  pkg_install redis memcached\n  REDIS_UNIT=redis\n  REDIS_CONF=/etc/redis/redis.conf\n  [ -f /etc/redis.conf ] && REDIS_CONF=/etc/redis.conf\nfi\n\n# Bind to this machine only. A Redis reachable from the internet with no\n# password is one of the most reliably exploited holes there is — it is how\n# a large share of crypto-miner infections get in.\nif [ -f "$REDIS_CONF" ]; then\n  sed -i "s/^[[:space:]]*bind .*/bind 127.0.0.1 ::1/" "$REDIS_CONF"\n  grep -q "^protected-mode" "$REDIS_CONF" \\\n    && sed -i "s/^protected-mode .*/protected-mode yes/" "$REDIS_CONF" \\\n    || echo "protected-mode yes" >> "$REDIS_CONF"\nfi\n# Memcached ships listening on all interfaces on some images — same problem.\nfor MC in /etc/memcached.conf /etc/sysconfig/memcached; do\n  [ -f "$MC" ] || continue\n  if grep -q "^-l " "$MC"; then sed -i "s/^-l .*/-l 127.0.0.1/" "$MC"; fi\n  if grep -q "^OPTIONS=" "$MC"; then\n    sed -i "s/^OPTIONS=.*/OPTIONS=\\"-l 127.0.0.1\\"/" "$MC"\n  fi\ndone\n\nsvc_enable "$REDIS_UNIT"\nsvc_enable memcached\n\n# The PHP extensions, so a site can actually use them. Optional: a missing\n# extension package must not fail the whole server setup.\nif command -v php >/dev/null 2>&1; then\n  if [ "$FAMILY" = debian ]; then\n    PHPV="$(php_fpm_ver)"\n    pkg_install "php${PHPV}-redis" "php${PHPV}-memcached" 2>/dev/null \\\n      || pkg_install php-redis php-memcached 2>/dev/null \\\n      || echo ">>> Note: the PHP cache extensions were not available; Redis itself is installed and running."\n  else\n    pkg_install php-pecl-redis php-pecl-memcached 2>/dev/null \\\n      || echo ">>> Note: the PHP cache extensions were not available; Redis itself is installed and running."\n  fi\n  FPM="$(php_fpm_service)"\n  systemctl is-active --quiet "$FPM" && svc_restart "$FPM" || true\nfi\n\nredis-cli ping >/dev/null 2>&1 && echo ">>> Redis is answering." \\\n  || { echo ">>> ERROR: Redis is installed but not answering."; exit 1; }\necho ">>> Redis and Memcached are running, reachable only from this server."\n'),
    },

    {
        'slug': 'php-limits',
        'title': 'Raise PHP upload and memory limits',
        'description': 'PHP ships allowing 2 MB uploads and 128 MB of memory. That is the reason a WordPress media upload or a plugin install fails on a brand-new server.',
        'category': 'setup',
        'os_family': 'linux',
        'script_type': 'bash',
        'est_runtime_sec': 20,
        'tags': ['php', 'upload', 'wordpress', 'limits'],
        'variables': [{'name': 'UPLOAD_MAX', 'label': 'Largest file a visitor can upload', 'default': '64M', 'required': True}, {'name': 'MEMORY_LIMIT', 'label': 'Memory one page may use', 'default': '256M', 'required': True}, {'name': 'MAX_EXECUTION', 'label': 'Seconds a page may run', 'default': '120', 'required': True}],
        "script_bash": ('#!/bin/bash\nset -euo pipefail\n# supported_os: ubuntu, debian, almalinux, rocky, centos\n' + _DISTRO + 'UPLOAD_MAX="{{UPLOAD_MAX}}"\nMEMORY_LIMIT="{{MEMORY_LIMIT}}"\nMAX_EXECUTION="{{MAX_EXECUTION}}"\necho "=== Raising PHP limits ==="\nif ! command -v php >/dev/null 2>&1; then\n  echo ">>> ERROR: PHP is not installed on this server."\n  exit 1\nfi\n\n# Every php.ini PHP actually reads — never a hardcoded version path. A\n# guessed path silently edits a file nothing loads, and the limit appears\n# changed while uploads keep failing.\nINIS="$(php -i 2>/dev/null | sed -n \'s/^Loaded Configuration File => //p\')"\nfor d in /etc/php/*/fpm/php.ini /etc/php/*/cli/php.ini /etc/php.ini \\\n         /etc/php-fpm.d/../php.ini; do\n  [ -f "$d" ] && INIS="$INIS $d"\ndone\nINIS="$(echo "$INIS" | tr " " "\\n" | grep -v "^$" | sort -u)"\n[ -n "$INIS" ] || { echo ">>> ERROR: could not find a php.ini to edit."; exit 1; }\n\nCHANGED=0\nfor INI in $INIS; do\n  cp -n "$INI" "${INI}.serverally.bak" 2>/dev/null || true\n  set_ini() {\n    if grep -qE "^[; ]*$1[[:space:]]*=" "$INI"; then\n      sed -i -E "s|^[; ]*$1[[:space:]]*=.*|$1 = $2|" "$INI"\n    else\n      printf "\\n%s = %s\\n" "$1" "$2" >> "$INI"\n    fi\n  }\n  set_ini upload_max_filesize "$UPLOAD_MAX"\n  # post_max_size must be at least upload_max_filesize or the upload is\n  # rejected before PHP ever looks at the file size limit.\n  set_ini post_max_size "$UPLOAD_MAX"\n  set_ini memory_limit "$MEMORY_LIMIT"\n  set_ini max_execution_time "$MAX_EXECUTION"\n  set_ini max_input_time "$MAX_EXECUTION"\n  echo ">>> Updated $INI"\n  CHANGED=$((CHANGED+1))\ndone\n\nFPM="$(php_fpm_service)"\nif systemctl is-active --quiet "$FPM" 2>/dev/null; then\n  svc_restart "$FPM"\n  echo ">>> Reloaded $FPM so the new limits are live."\nfi\n\n# PHP is only half of it. nginx rejects a body over ITS OWN limit (1 MB by default)\n# BEFORE the request ever reaches PHP, so raising php.ini alone still gives the visitor\n# a 413 while the setting reads 64M. Found by reading a competitor\'s finished server,\n# which sets nginx and PHP together.\nif [ -d /etc/nginx/conf.d ] && command -v nginx >/dev/null 2>&1; then\n  printf \'client_max_body_size %s;\\n\' "$UPLOAD_MAX" > /etc/nginx/conf.d/serverally-upload.conf\n  if nginx -t >/dev/null 2>&1; then\n    systemctl reload nginx >/dev/null 2>&1 || true\n    echo ">>> nginx will now accept bodies up to $UPLOAD_MAX."\n  else\n    # Never reload a configuration that does not parse: that takes down every OTHER\n    # site on the server, not just uploads.\n    rm -f /etc/nginx/conf.d/serverally-upload.conf\n    echo ">>> Left nginx alone: its configuration did not test clean."\n  fi\nfi\n# Apache has no low default here (LimitRequestBody is unlimited), so nothing to do.\necho ">>> PHP now accepts uploads up to $UPLOAD_MAX ($CHANGED file(s) updated)."\n'),
    },

    {
        'slug': 'auto-updates',
        'title': 'Automatic security updates',
        'description': 'Turns on unattended security updates, so the server keeps getting patched after today. Only security fixes are applied automatically.',
        'category': 'security',
        'os_family': 'linux',
        'script_type': 'bash',
        'est_runtime_sec': 45,
        'tags': ['updates', 'security', 'patching'],
        'variables': [],
        "script_bash": ('#!/bin/bash\nset -euo pipefail\n# supported_os: ubuntu, debian, almalinux, rocky, centos\n' + _DISTRO + 'echo "=== Turning on automatic security updates ==="\npkg_refresh\nif [ "$FAMILY" = debian ]; then\n  pkg_install unattended-upgrades\n  # Security origins only — and #clear FIRST, because APT list directives APPEND rather\n  # than replace, and stock Ubuntu ships "${distro_id}:${distro_codename}" (the WHOLE\n  # archive) enabled. Without clearing it, every feature update would keep applying\n  # itself unattended while we told the customer "security only" — a server that\n  # wakes up with a new major PHP and a dead website. Caught by reading apt-config\n  # dump on a real box, not by reading our own file.\n  cat > /etc/apt/apt.conf.d/51serverally-auto-upgrades <<\'EOF\'\nAPT::Periodic::Update-Package-Lists "1";\nAPT::Periodic::Unattended-Upgrade "1";\nAPT::Periodic::AutocleanInterval "7";\nEOF\n  cat > /etc/apt/apt.conf.d/52serverally-origins <<\'EOF\'\n#clear "Unattended-Upgrade::Allowed-Origins";\nUnattended-Upgrade::Allowed-Origins {\n    "${distro_id}:${distro_codename}-security";\n    "${distro_id}ESMApps:${distro_codename}-apps-security";\n    "${distro_id}ESM:${distro_codename}-infra-security";\n};\n// Never reboot on its own. A reboot nobody expected, in the middle of the\n// working day, is worse than a patch waiting a few hours.\nUnattended-Upgrade::Automatic-Reboot "false";\nEOF\n  svc_enable unattended-upgrades\n  unattended-upgrade --dry-run --debug >/dev/null 2>&1 \\\n    && echo ">>> Checked: the update job runs cleanly." \\\n    || echo ">>> Installed. The first run happens on the daily timer."\nelse\n  pkg_install dnf-automatic\n  CONF=/etc/dnf/automatic.conf\n  if [ -f "$CONF" ]; then\n    sed -i "s/^upgrade_type.*/upgrade_type = security/" "$CONF"\n    sed -i "s/^apply_updates.*/apply_updates = yes/" "$CONF"\n  fi\n  svc_enable dnf-automatic.timer\nfi\necho ">>> This server will now install security updates on its own. It will never reboot itself."\n'),
    },

    # ── Server Setup — Linux ──────────────────────────────────────────────────

    {
        "slug": "swap-file",
        "title": "Create and Enable Swap File",
        "description": "Creates a swap file to extend virtual memory. Safe to run on any Linux server.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 30,
        "tags": ["swap", "memory", "performance"],
        "variables": [
            {"name": "SWAP_SIZE", "label": "Swap Size (e.g. 2G, 4G)", "default": "2G", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'SWAP_SIZE="{{SWAP_SIZE}}"\n'
            "if swapon --show | grep -q '/swapfile'; then\n"
            "  echo 'Swap file already exists. Skipping.'\n"
            "  free -h\n"
            "  exit 0\n"
            "fi\n"
            'echo "Creating ${SWAP_SIZE} swap file..."\n'
            'fallocate -l "$SWAP_SIZE" /swapfile\n'
            "chmod 600 /swapfile\n"
            "mkswap /swapfile\n"
            "swapon /swapfile\n"
            "grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab\n"
            "sysctl vm.swappiness=10\n"
            "echo 'vm.swappiness=10' >> /etc/sysctl.conf\n"
            "echo 'Swap enabled.'\n"
            "free -h\n"
        ),
    },

    {
        "slug": "set-timezone",
        "title": "Set Server Timezone",
        "description": "Sets the server timezone using timedatectl.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 10,
        "tags": ["timezone", "system"],
        "variables": [
            {"name": "TIMEZONE", "label": "Timezone (e.g. UTC, America/New_York)", "default": "UTC", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'TIMEZONE="{{TIMEZONE}}"\n'
            'timedatectl set-timezone "$TIMEZONE"\n'
            'echo "Timezone set to: $(timedatectl show -p Timezone --value)"\n'
            "date\n"
        ),
    },

    {
        "slug": "docker",
        "title": "Docker + Docker Compose",
        "description": "Installs Docker Engine and Docker Compose plugin on Ubuntu/Debian.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["docker", "containers", "devops"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "if command -v docker &>/dev/null; then\n"
            '  echo "Docker already installed: $(docker --version)"\n'
            "  exit 0\n"
            "fi\n"
            'echo "Installing Docker..."\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq ca-certificates curl gnupg lsb-release\n"
            "install -m 0755 -d /etc/apt/keyrings\n"
            "curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg\n"
            "chmod a+r /etc/apt/keyrings/docker.gpg\n"
            'echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin\n"
            "systemctl enable --now docker\n"
            'echo "Docker installed: $(docker --version)"\n'
            'echo "Compose: $(docker compose version)"\n'
        ),
    },

    {
        "slug": "nodejs-pm2",
        "title": "Node.js LTS + PM2",
        "description": "Installs Node.js LTS via NodeSource and PM2 process manager.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["nodejs", "pm2", "javascript"],
        "variables": [
            {"name": "NODE_VERSION", "label": "Node.js major version", "default": "20", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'NODE_VERSION="{{NODE_VERSION}}"\n'
            "if command -v node &>/dev/null; then\n"
            '  echo "Node.js already installed: $(node --version)"\n'
            "else\n"
            '  curl -fsSL "https://deb.nodesource.com/setup_${NODE_VERSION}.x" | bash -\n'
            "  apt-get install -y -qq nodejs\n"
            '  echo "Node.js installed: $(node --version)"\n'
            "fi\n"
            "npm install -g pm2 --quiet\n"
            "pm2 startup || true\n"
            'echo "PM2: $(pm2 --version)"\n'
        ),
    },

    {
        "slug": "python-env",
        "title": "Python 3 + pip + virtualenv",
        "description": "Ensures Python 3, pip, and virtualenv are installed and up-to-date.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["python", "pip", "virtualenv"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "apt-get update -qq\n"
            "apt-get install -y -qq python3 python3-pip python3-venv python3-dev\n"
            "pip3 install --upgrade pip virtualenv --quiet\n"
            'echo "Python: $(python3 --version)"\n'
            'echo "pip: $(pip3 --version)"\n'
            'echo "virtualenv: $(virtualenv --version)"\n'
        ),
    },

    {
        "slug": "lemp-stack",
        "title": "LEMP Stack (Nginx + MySQL + PHP)",
        "description": "Installs Nginx, MySQL, PHP-FPM, and common PHP extensions.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 180,
        "tags": ["nginx", "mysql", "php", "lemp", "web-server"],
        "supported_os": ["ubuntu", "debian", "almalinux", "rocky", "centos", "rhel", "fedora"],
        "variables": [
            {"name": "MYSQL_ROOT_PASS", "label": "MySQL Root Password (optional)", "default": "", "required": False}
        ],
        "script_bash": _LEMP_BASH,
    },

    {
        "slug": "lamp-stack",
        "title": "LAMP Stack (Apache + MySQL + PHP)",
        "description": "Installs Apache2, MySQL Server, PHP, and common PHP extensions.",
        "category": "setup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 180,
        "tags": ["apache", "mysql", "php", "lamp", "web-server"],
        "supported_os": ["ubuntu", "debian", "almalinux", "rocky", "centos", "rhel", "fedora"],
        "variables": [],
        "script_bash": _LAMP_BASH,
    },

    # ── Security — Linux ──────────────────────────────────────────────────────

    {
        "slug": "ufw-setup",
        "title": "UFW Firewall Setup",
        "description": "Installs UFW, allows SSH/HTTP/HTTPS, and enables the firewall.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["ufw", "firewall", "security"],
        "variables": [
            {"name": "SSH_PORT", "label": "SSH Port", "default": "22", "required": True},
            {"name": "ALLOW_HTTP", "label": "Allow HTTP (80)? yes/no", "default": "yes", "required": False},
            {"name": "ALLOW_HTTPS", "label": "Allow HTTPS (443)? yes/no", "default": "yes", "required": False}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'SSH_PORT="{{SSH_PORT}}"\n'
            'ALLOW_HTTP="{{ALLOW_HTTP}}"\n'
            'ALLOW_HTTPS="{{ALLOW_HTTPS}}"\n'
            "apt-get install -y -qq ufw\n"
            "ufw --force reset\n"
            "ufw default deny incoming\n"
            "ufw default allow outgoing\n"
            'ufw allow "${SSH_PORT}/tcp" comment "SSH"\n'
            '[[ "$ALLOW_HTTP" == "yes" ]] && ufw allow 80/tcp comment "HTTP"\n'
            '[[ "$ALLOW_HTTPS" == "yes" ]] && ufw allow 443/tcp comment "HTTPS"\n'
            "ufw --force enable\n"
            "ufw status verbose\n"
            'echo "Firewall enabled."\n'
        ),
    },

    {
        "slug": "initial-hardening",
        "title": "Initial Server Security Hardening",
        "description": "Applies essential security: disables root SSH login, enables auto-updates, configures UFW and fail2ban.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["security", "hardening", "ssh", "firewall"],
        "variables": [
            {"name": "SSH_PORT", "label": "SSH Port", "default": "22", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'SSH_PORT="{{SSH_PORT}}"\n'
            'echo "=== Hardening SSH ==="\n'
            "sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config\n"
            "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config\n"
            "sed -i 's/^#*X11Forwarding.*/X11Forwarding no/' /etc/ssh/sshd_config\n"
            "systemctl restart sshd\n"
            'echo "=== Installing unattended-upgrades ==="\n'
            "apt-get install -y -qq unattended-upgrades apt-listchanges\n"
            "dpkg-reconfigure -plow unattended-upgrades\n"
            'echo "=== Configuring UFW ==="\n'
            "apt-get install -y -qq ufw\n"
            "ufw default deny incoming\n"
            "ufw default allow outgoing\n"
            'ufw allow "${SSH_PORT}/tcp" comment "SSH"\n'
            "ufw --force enable\n"
            'echo "=== Installing fail2ban ==="\n'
            "apt-get install -y -qq fail2ban\n"
            "systemctl enable --now fail2ban\n"
            'echo "Hardening complete. Verify SSH access before closing this session."\n'
        ),
    },

    {
        "slug": "fail2ban",
        "title": "Fail2Ban Install + Config",
        "description": "Installs fail2ban to protect SSH and services from brute-force attacks.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["fail2ban", "security", "brute-force"],
        "variables": [
            {"name": "BAN_TIME", "label": "Ban time in seconds", "default": "3600", "required": True},
            {"name": "MAX_RETRY", "label": "Max retry attempts", "default": "5", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'BAN_TIME="{{BAN_TIME}}"\n'
            'MAX_RETRY="{{MAX_RETRY}}"\n'
            "apt-get install -y -qq fail2ban\n"
            "cat > /etc/fail2ban/jail.local << EOF\n"
            "[DEFAULT]\n"
            "bantime  = ${BAN_TIME}\n"
            "findtime = 600\n"
            "maxretry = ${MAX_RETRY}\n"
            "[sshd]\n"
            "enabled = true\n"
            "EOF\n"
            "systemctl enable --now fail2ban\n"
            "fail2ban-client status\n"
            'echo "fail2ban installed and configured."\n'
        ),
    },

    {
        "slug": "ssh-key-auth",
        "title": "Enforce SSH Key Authentication Only",
        "description": "Disables password SSH login. Run only after verifying your SSH key works.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 15,
        "tags": ["ssh", "security", "keys"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config\n"
            "sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config\n"
            "sed -i 's/^#*UsePAM.*/UsePAM yes/' /etc/ssh/sshd_config\n"
            "sshd -t && systemctl reload sshd\n"
            'echo "SSH password authentication disabled. Key-only login enforced."\n'
        ),
    },

    {
        "slug": "letsencrypt",
        "title": "Certbot + Let's Encrypt SSL",
        "description": "Installs Certbot and obtains a free SSL certificate for your domain.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["ssl", "https", "certbot", "letsencrypt"],
        "variables": [
            {"name": "DOMAIN", "label": "Domain Name", "default": "example.com", "required": True},
            {"name": "EMAIL", "label": "Admin Email", "default": "", "required": True},
            {"name": "WEBSERVER", "label": "Web server (nginx or apache)", "default": "nginx", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'DOMAIN="{{DOMAIN}}"\n'
            'EMAIL="{{EMAIL}}"\n'
            'WEBSERVER="{{WEBSERVER}}"\n'
            "apt-get install -y -qq certbot\n"
            'if [[ "$WEBSERVER" == "nginx" ]]; then\n'
            "  apt-get install -y -qq python3-certbot-nginx\n"
            '  certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect\n'
            'elif [[ "$WEBSERVER" == "apache" ]]; then\n'
            "  apt-get install -y -qq python3-certbot-apache\n"
            '  certbot --apache -d "$DOMAIN" --non-interactive --agree-tos -m "$EMAIL" --redirect\n'
            "fi\n"
            "certbot certificates\n"
            'echo "SSL certificate installed for $DOMAIN."\n'
        ),
    },

    {
        "slug": "security-audit",
        "title": "Security Audit Report",
        "description": "Comprehensive security check: open ports, users, SSH config, UFW, and fail2ban.",
        "category": "security",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["security", "audit", "report"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -uo pipefail\n"
            'echo "=== ServerAlly Security Audit: $(date) ==="\n'
            'echo ""\n'
            'echo "--- OS ---"\n'
            "cat /etc/os-release | grep PRETTY_NAME; uname -r\n"
            'echo ""\n'
            'echo "--- Open Ports ---"\n'
            "ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null\n"
            'echo ""\n'
            'echo "--- SSH Config ---"\n'
            "grep -E 'PermitRoot|PasswordAuth|Port ' /etc/ssh/sshd_config | grep -v '^#'\n"
            'echo ""\n'
            'echo "--- UFW Status ---"\n'
            "ufw status 2>/dev/null || echo 'ufw not installed'\n"
            'echo ""\n'
            'echo "--- Fail2Ban ---"\n'
            "fail2ban-client status 2>/dev/null || echo 'fail2ban not installed'\n"
            'echo ""\n'
            'echo "--- Logged-in Users ---"\n'
            "who\n"
            'echo "Audit complete."\n'
        ),
    },

    # ── Backup & Restore — Linux ──────────────────────────────────────────────

    {
        "slug": "mysql-backup-local",
        "title": "MySQL Auto Backup (local cron)",
        "description": "Sets up a daily MySQL backup cron job with rotation.",
        "category": "backup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["mysql", "backup", "cron"],
        "variables": [
            {"name": "DB_USER", "label": "MySQL Username", "default": "root", "required": True},
            {"name": "DB_PASS", "label": "MySQL Password", "default": "", "required": True},
            {"name": "BACKUP_DIR", "label": "Backup Directory", "default": "/var/backups/mysql", "required": True},
            {"name": "KEEP_DAYS", "label": "Days to Keep Backups", "default": "7", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'DB_USER="{{DB_USER}}"\n'
            'DB_PASS="{{DB_PASS}}"\n'
            'BACKUP_DIR="{{BACKUP_DIR}}"\n'
            'KEEP_DAYS="{{KEEP_DAYS}}"\n'
            'mkdir -p "$BACKUP_DIR"\n'
            'chmod 700 "$BACKUP_DIR"\n'
            "printf '#!/bin/bash\\nDATE=$(date +%%Y%%m%%d_%%H%%M%%S)\\n"
            'mysqldump -u %s -p"%s" --all-databases --single-transaction | gzip > "%s/all_${DATE}.sql.gz"\\n'
            'find "%s" -name "*.sql.gz" -mtime +%s -delete\\n'
            "' \"$DB_USER\" \"$DB_PASS\" \"$BACKUP_DIR\" \"$BACKUP_DIR\" \"$KEEP_DAYS\" > /usr/local/bin/mysql-backup.sh\n"
            "chmod 700 /usr/local/bin/mysql-backup.sh\n"
            "echo '0 2 * * * root /usr/local/bin/mysql-backup.sh >> /var/log/mysql-backup.log 2>&1' > /etc/cron.d/mysql-backup\n"
            "bash /usr/local/bin/mysql-backup.sh\n"
            'echo "MySQL backup configured. Runs daily at 2:00 AM."\n'
        ),
    },

    {
        "slug": "postgres-backup",
        "title": "PostgreSQL Auto Backup",
        "description": "Sets up a daily PostgreSQL full backup with cron and rotation.",
        "category": "backup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["postgresql", "postgres", "backup", "cron"],
        "variables": [
            {"name": "PG_USER", "label": "PostgreSQL User", "default": "postgres", "required": True},
            {"name": "BACKUP_DIR", "label": "Backup Directory", "default": "/var/backups/postgresql", "required": True},
            {"name": "KEEP_DAYS", "label": "Days to Keep", "default": "7", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PG_USER="{{PG_USER}}"\n'
            'BACKUP_DIR="{{BACKUP_DIR}}"\n'
            'KEEP_DAYS="{{KEEP_DAYS}}"\n'
            'mkdir -p "$BACKUP_DIR"\n'
            'chown "$PG_USER" "$BACKUP_DIR"\n'
            "printf '#!/bin/bash\\nDATE=$(date +%%Y%%m%%d_%%H%%M%%S)\\n"
            'sudo -u %s pg_dumpall | gzip > "%s/all_${DATE}.sql.gz"\\n'
            'find "%s" -name "*.sql.gz" -mtime +%s -delete\\n'
            "' \"$PG_USER\" \"$BACKUP_DIR\" \"$BACKUP_DIR\" \"$KEEP_DAYS\" > /usr/local/bin/pg-backup.sh\n"
            "chmod 750 /usr/local/bin/pg-backup.sh\n"
            "echo '0 3 * * * root /usr/local/bin/pg-backup.sh >> /var/log/pg-backup.log 2>&1' > /etc/cron.d/pg-backup\n"
            "bash /usr/local/bin/pg-backup.sh\n"
            'echo "PostgreSQL backup configured. Runs daily at 3:00 AM."\n'
        ),
    },

    {
        "slug": "mysql-backup-s3",
        "title": "MySQL Auto Backup to S3",
        "description": "Backs up all MySQL databases and uploads to an S3-compatible bucket.",
        "category": "backup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["mysql", "backup", "s3", "aws"],
        "variables": [
            {"name": "DB_USER", "label": "MySQL Username", "default": "root", "required": True},
            {"name": "DB_PASS", "label": "MySQL Password", "default": "", "required": True},
            {"name": "S3_BUCKET", "label": "S3 Bucket path", "default": "s3://mybucket/mysql-backups", "required": True},
            {"name": "AWS_ACCESS_KEY", "label": "AWS Access Key ID", "default": "", "required": True},
            {"name": "AWS_SECRET_KEY", "label": "AWS Secret Access Key", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "apt-get install -y -qq awscli\n"
            'export AWS_ACCESS_KEY_ID="{{AWS_ACCESS_KEY}}"\n'
            'export AWS_SECRET_ACCESS_KEY="{{AWS_SECRET_KEY}}"\n'
            "mkdir -p /tmp/mysql-backups\n"
            "DATE=$(date +%Y%m%d_%H%M%S)\n"
            'mysqldump -u {{DB_USER}} -p"{{DB_PASS}}" --all-databases --single-transaction | gzip > "/tmp/mysql-backups/all_${DATE}.sql.gz"\n'
            'aws s3 cp "/tmp/mysql-backups/all_${DATE}.sql.gz" "{{S3_BUCKET}}/all_${DATE}.sql.gz"\n'
            'rm -f "/tmp/mysql-backups/all_${DATE}.sql.gz"\n'
            'echo "Backup uploaded to {{S3_BUCKET}}"\n'
        ),
    },

    {
        "slug": "rclone-setup",
        "title": "Rclone Cloud Sync Setup",
        "description": "Installs rclone for syncing files to any cloud storage provider.",
        "category": "backup",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["rclone", "backup", "cloud", "sync"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "curl -fsSL https://rclone.org/install.sh | bash\n"
            'echo "rclone: $(rclone --version | head -1)"\n'
            'echo ""\n'
            'echo "Next: run rclone config to set up your cloud provider."\n'
        ),
    },

    # ── App Deployment — Linux ────────────────────────────────────────────────

    {
        "slug": "wordpress",
        "access": {"name": "WordPress", "url": "https://{{DOMAIN}}/wp-admin/install.php", "note": "Finish setup in the browser — set your site title and admin account there."},
        "title": "WordPress (Nginx + MySQL + PHP)",
        "description": "Full WordPress install with Nginx, MySQL, PHP-FPM, and Let's Encrypt SSL.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 300,
        "tags": ["wordpress", "nginx", "mysql", "php", "cms"],
        "variables": [
            {"name": "DOMAIN", "label": "Domain Name", "default": "example.com", "required": True},
            {"name": "DB_NAME", "label": "Database Name", "default": "wordpress", "required": True},
            {"name": "DB_USER", "label": "Database User", "default": "wpuser", "required": True},
            {"name": "DB_PASS", "label": "Database Password", "default": "", "required": True},
            {"name": "ADMIN_EMAIL", "label": "Admin Email", "default": "", "required": True}
        ],
        "supported_os": ["ubuntu", "debian", "almalinux", "rocky", "centos", "rhel", "fedora"],
        "script_bash": _WORDPRESS_BASH,
    },

    {
        "slug": "portainer",
        "needs_docker": True,
        "access": {"name": "Portainer", "url": "https://{{HOST}}:{{PORT}}", "note": "Create your admin account on first open — do it promptly, Portainer locks new setups after a few minutes."},
        "title": "Portainer (Docker Management UI)",
        "description": "Installs Portainer CE for managing Docker containers via a web UI.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["portainer", "docker", "ui"],
        "variables": [
            {"name": "PORT", "label": "Web Port", "default": "9443", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PORT="{{PORT}}"\n'
            "docker volume create portainer_data 2>/dev/null || true\n"
            "docker stop portainer 2>/dev/null || true; docker rm portainer 2>/dev/null || true\n"
            'docker run -d --name portainer --restart=always -p "${PORT}:9443" -v /var/run/docker.sock:/var/run/docker.sock -v portainer_data:/data portainer/portainer-ce:latest\n'
            'echo "Portainer running at https://$(curl -s ifconfig.me):${PORT}"\n'
        ),
    },

    {
        "slug": "uptime-kuma",
        "needs_docker": True,
        "access": {"name": "Uptime Kuma", "url": "http://{{HOST}}:{{PORT}}", "note": "Create your admin account on first open."},
        "title": "Uptime Kuma (Self-hosted Monitoring)",
        "description": "Installs Uptime Kuma for monitoring websites and services.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 60,
        "tags": ["monitoring", "uptime", "docker"],
        "variables": [
            {"name": "PORT", "label": "Web Port", "default": "3001", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PORT="{{PORT}}"\n'
            "docker stop uptime-kuma 2>/dev/null || true; docker rm uptime-kuma 2>/dev/null || true\n"
            'docker run -d --name uptime-kuma --restart=always -p "${PORT}:3001" -v uptime-kuma:/app/data louislam/uptime-kuma:1\n'
            'echo "Uptime Kuma running at http://$(curl -s ifconfig.me):${PORT}"\n'
        ),
    },

    {
        "slug": "ghost-cms",
        "needs_docker": True,
        "access": {"name": "Ghost", "url": "http://{{HOST}}:2368", "note": "Set up your admin account at /ghost."},
        "title": "Ghost CMS",
        "description": "Installs Ghost CMS using Docker with Nginx reverse proxy.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 300,
        "tags": ["ghost", "cms", "blog", "docker"],
        "variables": [
            {"name": "DOMAIN", "label": "Domain Name", "default": "example.com", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'DOMAIN="{{DOMAIN}}"\n'
            "mkdir -p /opt/ghost\n"
            'printf "services:\\n  ghost:\\n    image: ghost:5-alpine\\n    restart: always\\n    ports: [\\"2368:2368\\"]\\n    environment:\\n      url: https://%s\\n    volumes:\\n      - ghost_content:/var/lib/ghost/content\\nvolumes:\\n  ghost_content:\\n" "$DOMAIN" > /opt/ghost/docker-compose.yml\n'
            "cd /opt/ghost && docker compose up -d\n"
            'echo "Ghost running at http://$(curl -s ifconfig.me):2368"\n'
        ),
    },

    {
        "slug": "nextcloud",
        "needs_docker": True,
        "access": {"name": "Nextcloud", "url": "http://{{HOST}}:8080", "username": "admin", "password": "{{NC_ADMIN_PASS}}"},
        "title": "Nextcloud",
        "description": "Installs Nextcloud self-hosted cloud storage using Docker.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 480,
        "tags": ["nextcloud", "cloud-storage", "docker"],
        "variables": [
            {"name": "DOMAIN", "label": "Domain Name", "default": "cloud.example.com", "required": True},
            {"name": "NC_ADMIN_PASS", "label": "Admin Password", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'DOMAIN="{{DOMAIN}}"\n'
            'NC_ADMIN_PASS="{{NC_ADMIN_PASS}}"\n'
            "mkdir -p /opt/nextcloud\n"
            'printf "services:\\n  nextcloud:\\n    image: nextcloud:latest\\n    restart: always\\n    ports: [\\"8080:80\\"]\\n    environment:\\n      NEXTCLOUD_ADMIN_USER: admin\\n      NEXTCLOUD_ADMIN_PASSWORD: %s\\n      NEXTCLOUD_TRUSTED_DOMAINS: %s\\n    volumes:\\n      - nextcloud_data:/var/www/html\\nvolumes:\\n  nextcloud_data:\\n" "$NC_ADMIN_PASS" "$DOMAIN" > /opt/nextcloud/docker-compose.yml\n'
            "cd /opt/nextcloud && docker compose up -d\n"
            'echo "Nextcloud starting at http://$(curl -s ifconfig.me):8080"\n'
        ),
    },

    {
        "slug": "gitea",
        "needs_docker": True,
        "access": {"name": "Gitea", "url": "http://{{HOST}}:{{PORT}}", "note": "Complete the install wizard in the browser; the first registered user becomes the admin."},
        "title": "Gitea (Self-hosted Git)",
        "description": "Installs Gitea — a lightweight self-hosted Git service.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 180,
        "tags": ["gitea", "git", "self-hosted", "docker"],
        "variables": [
            {"name": "PORT", "label": "Web Port", "default": "3000", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PORT="{{PORT}}"\n'
            "mkdir -p /opt/gitea\n"
            'printf "services:\\n  gitea:\\n    image: gitea/gitea:latest\\n    restart: always\\n    ports: [\\"%s:3000\\", \\"222:22\\"]\\n    volumes: [gitea_data:/data]\\nvolumes:\\n  gitea_data:\\n" "$PORT" > /opt/gitea/docker-compose.yml\n'
            "cd /opt/gitea && docker compose up -d\n"
            'echo "Gitea running at http://$(curl -s ifconfig.me):${PORT}"\n'
        ),
    },

    {
        "slug": "n8n",
        "needs_docker": True,
        "access": {"name": "n8n", "url": "http://{{HOST}}:{{PORT}}", "username": "{{N8N_USER}}", "password": "{{N8N_PASS}}"},
        "title": "n8n (Workflow Automation)",
        "description": "Installs n8n self-hosted workflow automation using Docker.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["n8n", "automation", "workflow", "docker"],
        "variables": [
            {"name": "PORT", "label": "Web Port", "default": "5678", "required": True},
            {"name": "N8N_USER", "label": "Basic Auth Username", "default": "admin", "required": True},
            {"name": "N8N_PASS", "label": "Basic Auth Password", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PORT="{{PORT}}"\n'
            'docker run -d --name n8n --restart=always -p "${PORT}:5678" -e N8N_BASIC_AUTH_ACTIVE=true -e N8N_BASIC_AUTH_USER="{{N8N_USER}}" -e N8N_BASIC_AUTH_PASSWORD="{{N8N_PASS}}" -v n8n_data:/home/node/.n8n n8nio/n8n:latest\n'
            'echo "n8n running at http://$(curl -s ifconfig.me):${PORT}"\n'
        ),
    },

    {
        "slug": "vaultwarden",
        "needs_docker": True,
        "access": {"name": "Vaultwarden", "url": "http://{{HOST}}:{{PORT}}", "note": "Create your account in the browser. The admin panel is at /admin (use your admin token)."},
        "title": "Vaultwarden (Bitwarden-compatible)",
        "description": "Installs Vaultwarden, a lightweight Bitwarden-compatible password manager.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["vaultwarden", "bitwarden", "passwords", "docker"],
        "variables": [
            {"name": "PORT", "label": "Web Port", "default": "8080", "required": True},
            {"name": "ADMIN_TOKEN", "label": "Admin Token (strong password)", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PORT="{{PORT}}"\n'
            'docker run -d --name vaultwarden --restart=always -p "${PORT}:80" -e ADMIN_TOKEN="{{ADMIN_TOKEN}}" -v vaultwarden_data:/data vaultwarden/server:latest\n'
            'echo "Vaultwarden running at http://$(curl -s ifconfig.me):${PORT}"\n'
        ),
    },

    {
        "slug": "nodejs-app-github",
        "title": "Deploy Node.js App from GitHub",
        "description": "Clones a GitHub repo, installs dependencies, and runs with PM2.",
        "category": "deployment",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["nodejs", "github", "deploy", "pm2"],
        "variables": [
            {"name": "REPO_URL", "label": "GitHub Repository URL", "default": "https://github.com/user/repo.git", "required": True},
            {"name": "APP_DIR", "label": "Deploy Directory", "default": "/opt/app", "required": True},
            {"name": "APP_NAME", "label": "PM2 App Name", "default": "myapp", "required": True},
            {"name": "START_CMD", "label": "Start Command", "default": "npm start", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'REPO_URL="{{REPO_URL}}"\n'
            'APP_DIR="{{APP_DIR}}"\n'
            'APP_NAME="{{APP_NAME}}"\n'
            'START_CMD="{{START_CMD}}"\n'
            'if [ -d "$APP_DIR" ]; then\n'
            '  cd "$APP_DIR" && git pull\n'
            "else\n"
            '  git clone "$REPO_URL" "$APP_DIR"\n'
            "fi\n"
            'cd "$APP_DIR"\n'
            "npm install --production\n"
            'pm2 delete "$APP_NAME" 2>/dev/null || true\n'
            'pm2 start $START_CMD --name "$APP_NAME"\n'
            "pm2 save\n"
            'echo "App deployed."\n'
            "pm2 status\n"
        ),
    },

    # ── Control Panels — Linux ────────────────────────────────────────────────

    {
        "slug": "cyberpanel",
        "needs_preflight": True,
        "title": "CyberPanel (OpenLiteSpeed)",
        "description": (
            "Installs CyberPanel — a free, open-source hosting control panel built on "
            "OpenLiteSpeed. Requires a FRESH server (Ubuntu 20.04/22.04 or AlmaLinux 8) "
            "with no other web server or panel. After install, you can re-add this server "
            "in Hosting Mode to manage sites, databases and email from ServerAlly."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 900,
        "tags": ["control-panel", "cyberpanel", "openlitespeed", "hosting"],
        "variables": [
            {"name": "ADMIN_PASSWORD", "label": "CyberPanel admin password", "default": "", "required": True}
        ],
        "access": {
            "name": "CyberPanel",
            "url": "https://{{HOST}}:8090",
            "username": "admin",
            "password": "{{ADMIN_PASSWORD}}",
            "note": "Your browser will warn about a self-signed certificate on first load — that's expected; continue past it.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="CyberPanel"\n'
            "MIN_RAM_MB=1024\n"
            'ADMIN_PASSWORD="{{ADMIN_PASSWORD}}"\n'
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}:${VERSION_ID:-}" in\n'
            "  ubuntu:20.04|ubuntu:22.04|almalinux:8*) : ;;\n"
            '  *) echo ">>> ERROR: CyberPanel supports Ubuntu 20.04/22.04 or AlmaLinux 8. Found ${PRETTY_NAME:-$ID}."; exit 1 ;;\n'
            "esac\n"
            'echo ">>> Downloading the official CyberPanel installer..."\n'
            "curl -sSL -o /tmp/cyberpanel.sh https://cyberpanel.net/install.sh\n"
            'echo ">>> Running installer (OpenLiteSpeed + full services, ~10-15 min)..."\n'
            "# Feed answers to the installer prompts: 1=install, 1=OpenLiteSpeed,\n"
            "# Y=full services, N=remote MySQL, <Enter>=latest version, s+password=set\n"
            "# admin password, Y=Memcached, Y=Redis, Yes=Watchdog.\n"
            "printf '1\\n1\\nY\\nN\\n\\ns\\n%s\\nY\\nY\\nYes\\n' \"$ADMIN_PASSWORD\" | bash /tmp/cyberpanel.sh\n"
            'echo ">>> CyberPanel installed. Panel: https://YOUR-SERVER-IP:8090 (user: admin) — see the access card for the link."\n'
        ),
    },

    {
        "slug": "hestiacp",
        "needs_preflight": True,
        "title": "HestiaCP (Hestia Control Panel)",
        "description": (
            "Installs HestiaCP — a free, open-source web hosting control panel for "
            "Ubuntu/Debian. Requires a FRESH server. Sets up the admin account "
            "non-interactively with the values you provide."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 900,
        "tags": ["control-panel", "hestiacp", "hosting"],
        "variables": [
            {"name": "ADMIN_EMAIL", "label": "Admin email", "default": "", "required": True},
            {"name": "ADMIN_PASSWORD", "label": "Admin password", "default": "", "required": True},
            {"name": "HOSTNAME", "label": "Server hostname (FQDN, e.g. panel.example.com)", "default": "", "required": True},
        ],
        "access": {
            "name": "HestiaCP",
            "url": "https://{{HOST}}:8083",
            "username": "admin",
            "password": "{{ADMIN_PASSWORD}}",
            "note": "Expect a self-signed-certificate warning on first load.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="HestiaCP"\n'
            "MIN_RAM_MB=1024\n"
            'ADMIN_EMAIL="{{ADMIN_EMAIL}}"\n'
            'ADMIN_PASSWORD="{{ADMIN_PASSWORD}}"\n'
            'HOSTNAME_FQDN="{{HOSTNAME}}"\n'
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}" in ubuntu|debian) : ;; *) echo ">>> ERROR: HestiaCP supports Ubuntu/Debian. Found ${PRETTY_NAME:-$ID}."; exit 1 ;; esac\n'
            'echo ">>> Downloading the official HestiaCP installer..."\n'
            "wget -qO /tmp/hst-install.sh https://raw.githubusercontent.com/hestiacp/hestiacp/release/install/hst-install.sh\n"
            'echo ">>> Installing HestiaCP (non-interactive, ~10 min)..."\n'
            'bash /tmp/hst-install.sh --interactive no --force --email "$ADMIN_EMAIL" --password "$ADMIN_PASSWORD" --hostname "$HOSTNAME_FQDN" --lang en\n'
            'echo ">>> HestiaCP installed. Panel: https://YOUR-SERVER-IP:8083 (user: admin) — see the access card."\n'
        ),
    },

    {
        "slug": "aapanel",
        "needs_preflight": True,
        "title": "aaPanel",
        "description": (
            "Installs aaPanel — a free, beginner-friendly hosting control panel (LNMP/LAMP). "
            "Requires a FRESH server (Ubuntu/Debian/CentOS/AlmaLinux). The login URL, username "
            "and a temporary password are printed at the end of the install — copy them."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 360,
        "tags": ["control-panel", "aapanel", "hosting"],
        "variables": [],
        "access": {
            "name": "aaPanel",
            "note": "aaPanel prints your exact panel URL (it includes a random security path), username and temporary password at the END of the install log above — copy them now. To retrieve them later, run 'bt default' on the server.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="aaPanel"\n'
            "MIN_RAM_MB=1024\n"
            "preflight\n"
            'echo ">>> Downloading the official aaPanel installer..."\n'
            "curl -sSL -o /tmp/aapanel.sh https://www.aapanel.com/script/install_6.0_en.sh\n"
            'echo ">>> Installing aaPanel (~5 min)..."\n'
            "echo y | bash /tmp/aapanel.sh aapanel\n"
            'echo ">>> aaPanel installed. Copy the URL / username / password shown above."\n'
        ),
    },

    {
        "slug": "cloudpanel",
        "needs_preflight": True,
        "title": "CloudPanel",
        "description": (
            "Installs CloudPanel — a free, modern hosting control panel (PHP/Node/Python) for "
            "Debian 11/12 and Ubuntu 22.04/24.04. Requires a FRESH server with at least 2 GB RAM. "
            "Create your admin account on the first visit."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 420,
        "tags": ["control-panel", "cloudpanel", "hosting"],
        "variables": [],
        "access": {
            "name": "CloudPanel",
            "url": "https://{{HOST}}:8443",
            "note": "Create your admin account on the first visit (no preset login). Expect a self-signed-certificate warning.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="CloudPanel"\n'
            "MIN_RAM_MB=2048\n"
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}:${VERSION_ID:-}" in\n'
            "  debian:11|debian:12|ubuntu:22.04|ubuntu:24.04) : ;;\n"
            '  *) echo ">>> ERROR: CloudPanel supports Debian 11/12 or Ubuntu 22.04/24.04. Found ${PRETTY_NAME:-$ID}."; exit 1 ;;\n'
            "esac\n"
            "export DEBIAN_FRONTEND=noninteractive\n"
            "apt-get update -qq\n"
            "apt-get install -y -qq curl wget sudo\n"
            'echo ">>> Downloading the official CloudPanel installer..."\n'
            "curl -sSL https://installer.cloudpanel.io/ce/v2/install.sh -o /tmp/cloudpanel.sh\n"
            'echo ">>> Installing CloudPanel (MySQL 8.0, ~5 min)..."\n'
            "DB_ENGINE=MYSQL_8.0 bash /tmp/cloudpanel.sh\n"
            'echo ">>> CloudPanel installed. Open https://YOUR-SERVER-IP:8443 and create your admin account."\n'
        ),
    },

    {
        "slug": "webmin",
        "needs_preflight": False,
        "title": "Webmin",
        "description": (
            "Installs Webmin — a free, web-based system administration panel for Linux "
            "(manage users, services, packages, cron, firewall, and more). Lightweight and "
            "coexists with your existing setup — no fresh server required. Log in with your "
            "server's root or sudo user."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 150,
        "tags": ["control-panel", "webmin", "system"],
        "variables": [],
        "access": {
            "name": "Webmin",
            "url": "https://{{HOST}}:10000",
            "username": "root",
            "note": "Log in with your server's root or sudo-user password. Expect a self-signed-certificate warning on first load.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            ". /etc/os-release\n"
            'case "${ID:-}" in ubuntu|debian) : ;; *) echo ">>> ERROR: This Webmin playbook supports Ubuntu/Debian. Found ${PRETTY_NAME:-$ID}."; exit 1 ;; esac\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq curl\n"
            'echo ">>> Adding the official Webmin repository..."\n'
            "curl -fsSL https://download.webmin.com/setup-repos.sh -o /tmp/webmin-setup-repos.sh\n"
            "sh /tmp/webmin-setup-repos.sh -f\n"
            "apt-get update -qq\n"
            'echo ">>> Installing Webmin (~2 min)..."\n'
            "apt-get install -y --install-recommends webmin\n"
            'echo ">>> Webmin installed. Open https://YOUR-SERVER-IP:10000 and log in with your root or sudo user."\n'
        ),
    },

    {
        "slug": "virtualmin",
        "needs_preflight": True,
        "title": "Virtualmin (GPL)",
        "description": (
            "Installs Virtualmin GPL — a free, full web-hosting control panel built on Webmin "
            "(Apache, BIND, Postfix, MariaDB/MySQL). Requires a FRESH server with 2 GB+ RAM and a "
            "fully-qualified hostname. Log in as root and finish the setup wizard on first visit."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 900,
        "tags": ["control-panel", "virtualmin", "hosting"],
        "variables": [
            {"name": "HOSTNAME", "label": "Server hostname (FQDN, e.g. server.example.com)", "default": "", "required": True},
        ],
        "access": {
            "name": "Virtualmin",
            "url": "https://{{HOST}}:10000",
            "username": "root",
            "note": "Log in with your server's root password, then complete the post-install wizard. Expect a self-signed-certificate warning.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="Virtualmin"\n'
            "MIN_RAM_MB=2048\n"
            'HOSTNAME_FQDN="{{HOSTNAME}}"\n'
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}" in ubuntu|debian|almalinux|rocky|centos) : ;; *) echo ">>> ERROR: Virtualmin supports Ubuntu/Debian/AlmaLinux/Rocky/CentOS. Found ${PRETTY_NAME:-$ID}."; exit 1 ;; esac\n'
            'echo ">>> Setting hostname to $HOSTNAME_FQDN..."\n'
            'hostnamectl set-hostname "$HOSTNAME_FQDN" 2>/dev/null || true\n'
            'echo ">>> Downloading the official Virtualmin installer..."\n'
            "curl -fsSL https://software.virtualmin.com/gpl/scripts/virtualmin-install.sh -o /tmp/virtualmin-install.sh\n"
            'echo ">>> Installing Virtualmin GPL (~10-15 min)..."\n'
            'sh /tmp/virtualmin-install.sh --force --hostname "$HOSTNAME_FQDN"\n'
            'echo ">>> Virtualmin installed. Open https://YOUR-SERVER-IP:10000 and log in as root."\n'
        ),
    },

    # ── Control Panels — Premium (license required) ──────────────────────────

    {
        "slug": "cpanel-whm",
        "needs_preflight": True,
        "title": "cPanel / WHM",
        "description": (
            "Installs cPanel & WHM — the industry-standard commercial hosting panel. Requires a "
            "FRESH server (AlmaLinux/Rocky 8-9, CloudLinux, CentOS 7, or Ubuntu 20.04/22.04 — NOT "
            "Debian) with 2 GB+ RAM. cPanel needs a license; a 15-day trial is offered on first "
            "login. Manage it via WHM on port 2087."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 1800,
        "tags": ["control-panel", "cpanel", "whm", "hosting", "premium"],
        "variables": [
            {"name": "HOSTNAME", "label": "Server hostname (FQDN, e.g. server.example.com)", "default": "", "required": True}
        ],
        "access": {
            "name": "WHM (cPanel)",
            "url": "https://{{HOST}}:2087",
            "username": "root",
            "note": "Log in with your server's root password. cPanel needs a license — a 15-day trial is offered on first login (store.cpanel.net). Expect a self-signed-certificate warning.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="cPanel & WHM"\n'
            "MIN_RAM_MB=2048\n"
            'HOSTNAME_FQDN="{{HOSTNAME}}"\n'
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}:${VERSION_ID:-}" in\n'
            "  almalinux:8*|almalinux:9*|rocky:8*|rocky:9*|cloudlinux:*|centos:7*|ubuntu:20.04|ubuntu:22.04) : ;;\n"
            '  *) echo ">>> ERROR: cPanel supports AlmaLinux/Rocky 8-9, CloudLinux, CentOS 7, or Ubuntu 20.04/22.04 (not Debian). Found ${PRETTY_NAME:-$ID}."; exit 1 ;;\n'
            "esac\n"
            'echo ">>> Setting hostname to $HOSTNAME_FQDN..."\n'
            'hostnamectl set-hostname "$HOSTNAME_FQDN" || true\n'
            'echo ">>> Downloading and running the official cPanel installer (~25-40 min)..."\n'
            "cd /home\n"
            "curl -o latest -L https://securedownloads.cpanel.net/latest\n"
            "sh latest\n"
            'echo ">>> cPanel & WHM installed. WHM: https://YOUR-SERVER-IP:2087 (user: root). Add a license or start a trial on first login."\n'
        ),
    },

    {
        "slug": "plesk",
        "needs_preflight": True,
        "title": "Plesk",
        "description": (
            "Installs Plesk — a leading commercial hosting panel — via its official one-click "
            "installer. Requires a FRESH server (Ubuntu 20.04/22.04, Debian 11/12, or "
            "AlmaLinux/Rocky/CentOS 8-9) with 2 GB+ RAM. A trial license is available on first "
            "login. Presets the admin password you provide."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 1200,
        "tags": ["control-panel", "plesk", "hosting", "premium"],
        "variables": [
            {"name": "ADMIN_PASSWORD", "label": "Plesk admin password", "default": "", "required": True}
        ],
        "access": {
            "name": "Plesk",
            "url": "https://{{HOST}}:8443",
            "username": "admin",
            "password": "{{ADMIN_PASSWORD}}",
            "note": "Plesk needs a license — choose the trial on first login. Expect a self-signed-certificate warning.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="Plesk"\n'
            "MIN_RAM_MB=2048\n"
            'ADMIN_PASSWORD="{{ADMIN_PASSWORD}}"\n'
            "preflight\n"
            ". /etc/os-release\n"
            'case "${ID:-}:${VERSION_ID:-}" in\n'
            "  ubuntu:20.04|ubuntu:22.04|debian:11|debian:12|almalinux:8*|almalinux:9*|rocky:8*|rocky:9*|centos:8*) : ;;\n"
            '  *) echo ">>> ERROR: Plesk supports Ubuntu 20.04/22.04, Debian 11/12, or AlmaLinux/Rocky/CentOS 8-9. Found ${PRETTY_NAME:-$ID}."; exit 1 ;;\n'
            "esac\n"
            'echo ">>> Downloading the official Plesk one-click installer..."\n'
            "curl -fsSL https://autoinstall.plesk.com/one-click-installer -o /tmp/plesk-installer.sh\n"
            'echo ">>> Installing Plesk (~15-25 min)..."\n'
            "sh /tmp/plesk-installer.sh\n"
            'echo ">>> Setting the Plesk admin password..."\n'
            'plesk bin admin --set-password -passwd "$ADMIN_PASSWORD" || echo ">>> Could not preset the admin password; run plesk login on the server for a one-time login link."\n'
            'echo ">>> Plesk installed. Panel: https://YOUR-SERVER-IP:8443 (user: admin)."\n'
        ),
    },

    {
        "slug": "directadmin",
        "needs_preflight": True,
        "title": "DirectAdmin",
        "description": (
            "Installs DirectAdmin — a lightweight commercial hosting panel — using your license "
            "key. Requires a FRESH server (AlmaLinux/Rocky 8-9, Ubuntu 20.04/22.04/24.04, or "
            "Debian 11/12) with 1 GB+ RAM. Get a license key (incl. a low-cost personal option) "
            "from directadmin.com. Admin credentials are printed at the end of the install."
        ),
        "category": "control-panel",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 1200,
        "tags": ["control-panel", "directadmin", "hosting", "premium"],
        "variables": [
            {"name": "LICENSE_KEY", "label": "DirectAdmin license key", "default": "", "required": True}
        ],
        "access": {
            "name": "DirectAdmin",
            "url": "https://{{HOST}}:2222",
            "note": "Your admin username and password are printed at the END of the install log above — copy them now. Expect a self-signed-certificate warning.",
        },
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PANEL="DirectAdmin"\n'
            "MIN_RAM_MB=1024\n"
            'LICENSE_KEY="{{LICENSE_KEY}}"\n'
            "preflight\n"
            'if [ -z "$LICENSE_KEY" ]; then echo ">>> ERROR: A DirectAdmin license key is required (get one at https://www.directadmin.com/)."; exit 1; fi\n'
            ". /etc/os-release\n"
            'case "${ID:-}:${VERSION_ID:-}" in\n'
            "  almalinux:8*|almalinux:9*|rocky:8*|rocky:9*|centos:7*|centos:8*|ubuntu:20.04|ubuntu:22.04|ubuntu:24.04|debian:11|debian:12) : ;;\n"
            '  *) echo ">>> ERROR: DirectAdmin supports AlmaLinux/Rocky 8-9, CentOS, Ubuntu 20.04/22.04/24.04, or Debian 11/12. Found ${PRETTY_NAME:-$ID}."; exit 1 ;;\n'
            "esac\n"
            'echo ">>> Downloading the official DirectAdmin installer..."\n'
            "curl -fsSL https://download.directadmin.com/setup.sh -o /tmp/da-setup.sh\n"
            "chmod 755 /tmp/da-setup.sh\n"
            'echo ">>> Installing DirectAdmin (~15 min)..."\n'
            '/tmp/da-setup.sh "$LICENSE_KEY"\n'
            'echo ">>> DirectAdmin installed. Panel: https://YOUR-SERVER-IP:2222 — the admin login is printed above."\n'
        ),
    },

    # ── Monitoring — Linux ────────────────────────────────────────────────────

    {
        "slug": "netdata",
        "access": {"name": "Netdata", "url": "http://{{HOST}}:19999", "note": "No login required by default."},
        "title": "Netdata Real-time Monitoring",
        "description": "Installs Netdata for beautiful real-time system monitoring.",
        "category": "monitoring",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["netdata", "monitoring", "metrics"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "wget -q -O /tmp/netdata-kickstart.sh https://get.netdata.cloud/kickstart.sh\n"
            "sh /tmp/netdata-kickstart.sh --stable-channel --dont-wait --no-updates\n"
            "systemctl enable --now netdata\n"
            'echo "Netdata running at http://$(curl -s ifconfig.me):19999"\n'
        ),
    },

    {
        "slug": "prometheus-grafana",
        "needs_docker": True,
        "access": {"name": "Grafana", "url": "http://{{HOST}}:{{GRAFANA_PORT}}", "username": "admin", "password": "{{GRAFANA_PASS}}"},
        "title": "Prometheus + Grafana Stack",
        "description": "Deploys Prometheus + Node Exporter + Grafana via Docker Compose.",
        "category": "monitoring",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 300,
        "tags": ["prometheus", "grafana", "metrics", "docker"],
        "variables": [
            {"name": "GRAFANA_PASS", "label": "Grafana Admin Password", "default": "", "required": True},
            {"name": "GRAFANA_PORT", "label": "Grafana Port", "default": "3000", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'GRAFANA_PORT="{{GRAFANA_PORT}}"\n'
            'GRAFANA_PASS="{{GRAFANA_PASS}}"\n'
            "mkdir -p /opt/monitoring\n"
            'printf "services:\\n  prometheus:\\n    image: prom/prometheus:latest\\n    restart: always\\n    ports: [\\"9090:9090\\"]\\n  node-exporter:\\n    image: prom/node-exporter:latest\\n    restart: always\\n  grafana:\\n    image: grafana/grafana:latest\\n    restart: always\\n    ports: [\\"%s:3000\\"]\\n    environment:\\n      GF_SECURITY_ADMIN_PASSWORD: %s\\n    volumes: [grafana_data:/var/lib/grafana]\\nvolumes:\\n  grafana_data:\\n" "$GRAFANA_PORT" "$GRAFANA_PASS" > /opt/monitoring/docker-compose.yml\n'
            "cd /opt/monitoring && docker compose up -d\n"
            'echo "Grafana: http://$(curl -s ifconfig.me):${GRAFANA_PORT} (admin/$GRAFANA_PASS)"\n'
        ),
    },

    {
        "slug": "disk-alert",
        "title": "Disk Usage Email Alert",
        "description": "Creates a cron job that emails you when disk usage exceeds a threshold.",
        "category": "monitoring",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 30,
        "tags": ["disk", "alert", "email", "cron"],
        "variables": [
            {"name": "THRESHOLD", "label": "Alert Threshold %", "default": "85", "required": True},
            {"name": "EMAIL", "label": "Alert Email Address", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'THRESHOLD="{{THRESHOLD}}"\n'
            'EMAIL="{{EMAIL}}"\n'
            "SCRIPT=/usr/local/bin/disk-alert.sh\n"
            "printf '%s\\n' '#!/bin/bash' > \"$SCRIPT\"\n"
            "printf 'USAGE=$(df / | tail -1 | awk \"{print \\$5}\" | tr -d %%)\\n' >> \"$SCRIPT\"\n"
            "printf '[ \"$USAGE\" -ge \"%s\" ] && echo \"Disk $USAGE%% used on $(hostname)\" | mail -s \"[Alert] High Disk Usage\" \"%s\"\\n' \"$THRESHOLD\" \"$EMAIL\" >> \"$SCRIPT\"\n"
            "chmod 755 \"$SCRIPT\"\n"
            "echo '0 * * * * root /usr/local/bin/disk-alert.sh' > /etc/cron.d/disk-alert\n"
            'echo "Disk alert configured. Will email $EMAIL when usage exceeds ${THRESHOLD}%."\n'
        ),
    },

    # ── Maintenance — Linux ───────────────────────────────────────────────────

    {
        "slug": "full-update",
        "title": "Full System Update + Cleanup",
        "description": "Updates all packages, removes unused dependencies, and cleans the cache.",
        "category": "maintenance",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 120,
        "tags": ["update", "maintenance", "cleanup"],
        "variables": [],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'echo "=== Updating package list ==="\n'
            "apt-get update\n"
            'echo "=== Upgrading packages ==="\n'
            "DEBIAN_FRONTEND=noninteractive apt-get upgrade -y\n"
            'echo "=== Removing unused packages ==="\n'
            "apt-get autoremove -y\n"
            "apt-get autoclean\n"
            'if [ -f /var/run/reboot-required ]; then\n'
            '  echo "NOTICE: A reboot is required."\n'
            "else\n"
            '  echo "No reboot required."\n'
            "fi\n"
            'echo "Update complete."\n'
        ),
    },

    {
        "slug": "clean-logs",
        "title": "Clear Old Logs + Temp Files",
        "description": "Rotates and removes old log files and temp files to free disk space.",
        "category": "maintenance",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 30,
        "tags": ["logs", "cleanup", "disk-space"],
        "variables": [
            {"name": "LOG_AGE_DAYS", "label": "Delete logs older than (days)", "default": "30", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -uo pipefail\n"
            'LOG_AGE_DAYS="{{LOG_AGE_DAYS}}"\n'
            'echo "=== Before cleanup ==="\n'
            "df -h /\n"
            'journalctl --vacuum-time="${LOG_AGE_DAYS}d" 2>/dev/null || true\n'
            'find /var/log -name "*.gz" -mtime +"$LOG_AGE_DAYS" -delete 2>/dev/null || true\n'
            'find /tmp -mtime +"$LOG_AGE_DAYS" -delete 2>/dev/null || true\n'
            'echo "=== After cleanup ==="\n'
            "df -h /\n"
            'echo "Cleanup complete."\n'
        ),
    },

    {
        "slug": "find-large-files",
        "title": "Large Files Report",
        "description": "Finds the largest files and reports disk usage by directory.",
        "category": "maintenance",
        "os_family": "linux",
        "script_type": "bash",
        "est_runtime_sec": 30,
        "tags": ["disk-space", "files", "report"],
        "variables": [
            {"name": "TOP_N", "label": "Number of files to show", "default": "20", "required": True},
            {"name": "MIN_SIZE", "label": "Minimum file size", "default": "100M", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -uo pipefail\n"
            'TOP_N="{{TOP_N}}"\n'
            'MIN_SIZE="{{MIN_SIZE}}"\n'
            'echo "=== Disk Overview ==="\n'
            "df -h\n"
            'echo ""\n'
            'echo "=== Top ${TOP_N} Largest Files (>= ${MIN_SIZE}) ==="\n'
            'find / -xdev -type f -size "+${MIN_SIZE}" 2>/dev/null | xargs ls -lh 2>/dev/null | sort -k5 -hr | head -"$TOP_N"\n'
            'echo ""\n'
            'echo "=== Top 10 Dirs by Size ==="\n'
            "du -hx --max-depth=3 / 2>/dev/null | sort -hr | head -10\n"
            'echo "Report complete."\n'
        ),
    },

    # ── Windows Server Playbooks ──────────────────────────────────────────────

    {
        "slug": "win-chocolatey",
        "title": "Install Chocolatey Package Manager",
        "description": "Installs Chocolatey, the Windows package manager.",
        "category": "setup",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 60,
        "tags": ["chocolatey", "package-manager", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "if (Get-Command choco -ErrorAction SilentlyContinue) {\n"
            "    Write-Host \"Chocolatey already installed: $(choco --version)\"\n"
            "    exit 0\n"
            "}\n"
            "Write-Host 'Installing Chocolatey...'\n"
            "Set-ExecutionPolicy Bypass -Scope Process -Force\n"
            "[System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072\n"
            "Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))\n"
            "Write-Host \"Chocolatey installed: $(choco --version)\"\n"
        ),
    },

    {
        "slug": "win-openssh",
        "title": "Enable OpenSSH Server",
        "description": "Enables and configures the OpenSSH Server on Windows Server.",
        "category": "setup",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 60,
        "tags": ["ssh", "openssh", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0\n"
            "Start-Service sshd\n"
            "Set-Service -Name sshd -StartupType Automatic\n"
            "New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue\n"
            "Write-Host 'OpenSSH Server enabled on port 22.'\n"
            "Get-Service sshd\n"
        ),
    },

    {
        "slug": "win-iis",
        "title": "Install IIS Web Server",
        "description": "Installs IIS with ASP.NET, management tools, and common features.",
        "category": "setup",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 120,
        "tags": ["iis", "web-server", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "Write-Host 'Installing IIS...'\n"
            "Install-WindowsFeature -Name Web-Server, Web-Mgmt-Tools, Web-Asp-Net45, Web-Net-Ext45 -IncludeManagementTools\n"
            "Start-Service W3SVC\n"
            "Set-Service -Name W3SVC -StartupType Automatic\n"
            "Write-Host 'IIS installed.'\n"
            "Get-Service W3SVC\n"
        ),
    },

    {
        "slug": "win-nodejs",
        "title": "Install Node.js LTS + PM2 (Windows)",
        "description": "Installs Node.js LTS and PM2 on Windows Server via Chocolatey.",
        "category": "setup",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 120,
        "tags": ["nodejs", "pm2", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "if (-not (Get-Command node -ErrorAction SilentlyContinue)) {\n"
            "    choco install nodejs-lts -y --no-progress\n"
            "    $env:Path = [System.Environment]::GetEnvironmentVariable('Path','Machine')\n"
            "}\n"
            "npm install -g pm2 --quiet\n"
            "Write-Host \"Node: $(node --version), PM2: $(pm2 --version)\"\n"
        ),
    },

    {
        "slug": "win-docker",
        "title": "Install Docker Engine (Windows Server)",
        "description": "Installs Docker Engine for Windows Server.",
        "category": "setup",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 180,
        "tags": ["docker", "containers", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "if (Get-Command docker -ErrorAction SilentlyContinue) {\n"
            "    Write-Host \"Docker already installed: $(docker --version)\"\n"
            "    exit 0\n"
            "}\n"
            "Install-Module -Name DockerMsftProvider -Repository PSGallery -Force\n"
            "Install-Package -Name docker -ProviderName DockerMsftProvider -Force\n"
            "Start-Service Docker\n"
            "Set-Service -Name Docker -StartupType Automatic\n"
            "Write-Host \"Docker installed: $(docker --version)\"\n"
        ),
    },

    {
        "slug": "win-firewall",
        "title": "Configure Windows Firewall Rules",
        "description": "Configures Windows Firewall to allow HTTP, HTTPS, and RDP.",
        "category": "security",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 30,
        "tags": ["firewall", "security", "windows"],
        "variables": [
            {"name": "RDP_PORT", "label": "RDP Port", "default": "3389", "required": True}
        ],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "$RDP_PORT = {{RDP_PORT}}\n"
            "New-NetFirewallRule -DisplayName 'Allow HTTP' -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow -ErrorAction SilentlyContinue\n"
            "New-NetFirewallRule -DisplayName 'Allow HTTPS' -Direction Inbound -Protocol TCP -LocalPort 443 -Action Allow -ErrorAction SilentlyContinue\n"
            "New-NetFirewallRule -DisplayName 'Allow RDP' -Direction Inbound -Protocol TCP -LocalPort $RDP_PORT -Action Allow -ErrorAction SilentlyContinue\n"
            "Write-Host 'Firewall rules configured.'\n"
        ),
    },

    {
        "slug": "win-updates",
        "title": "Enable Automatic Windows Updates",
        "description": "Configures Windows Update for automatic download and installation.",
        "category": "security",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 60,
        "tags": ["windows-update", "security"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "$AUSettings = New-Object -ComObject Microsoft.Update.AutoUpdate\n"
            "$AUSettings.Settings.NotificationLevel = 4\n"
            "$AUSettings.Settings.Save()\n"
            "Set-Service -Name wuauserv -StartupType Automatic\n"
            "Start-Service wuauserv\n"
            "Write-Host 'Automatic Windows Updates enabled.'\n"
        ),
    },

    {
        "slug": "win-rdp-secure",
        "title": "Harden RDP Access",
        "description": "Enables NLA on RDP and configures account lockout policy.",
        "category": "security",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 60,
        "tags": ["rdp", "security", "windows"],
        "variables": [
            {"name": "NEW_RDP_PORT", "label": "RDP Port", "default": "3389", "required": True}
        ],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Set-StrictMode -Version Latest\n"
            "$ErrorActionPreference = 'Stop'\n"
            "$NEW_PORT = {{NEW_RDP_PORT}}\n"
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name PortNumber -Value $NEW_PORT\n"
            "Set-ItemProperty -Path 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Terminal Server' -Name 'UserAuthentication' -Value 1\n"
            "net accounts /lockoutthreshold:5 /lockoutduration:30 /lockoutwindow:30\n"
            "Write-Host \"RDP hardened. Port: $NEW_PORT, NLA enabled, lockout policy set.\"\n"
        ),
    },

    {
        "slug": "win-audit",
        "title": "Windows Security Audit Report",
        "description": "Comprehensive Windows security audit: users, firewall, services, updates.",
        "category": "security",
        "os_family": "windows",
        "script_type": "powershell",
        "est_runtime_sec": 120,
        "tags": ["security", "audit", "windows"],
        "variables": [],
        "script_powershell": (
            "#Requires -Version 5.1\n"
            "Write-Host '=== ServerAlly Windows Security Audit ==='\n"
            "Write-Host \"Date: $(Get-Date)\"\n"
            "Write-Host ''\n"
            "Write-Host '--- OS Info ---'\n"
            "Get-ComputerInfo | Select-Object WindowsProductName, WindowsVersion\n"
            "Write-Host '--- Local Users ---'\n"
            "Get-LocalUser | Select-Object Name, Enabled, LastLogon\n"
            "Write-Host '--- Administrators ---'\n"
            "Get-LocalGroupMember -Group 'Administrators'\n"
            "Write-Host '--- Open Ports ---'\n"
            "Get-NetTCPConnection -State Listen | Select-Object LocalPort, State | Sort-Object LocalPort\n"
            "Write-Host '--- Firewall Profiles ---'\n"
            "Get-NetFirewallProfile | Select-Object Name, Enabled, DefaultInboundAction\n"
            "Write-Host 'Audit complete.'\n"
        ),
    },
]


# ── Seed function ─────────────────────────────────────────────────────────────

def _build_playbook(item: dict) -> Playbook:
    """Construct a Playbook row from a definition (without mutating it)."""
    return Playbook(
        slug=item["slug"],
        title=item["title"],
        description=item.get("description"),
        category=item.get("category"),
        os_family=item.get("os_family"),
        script_type=item.get("script_type"),
        est_runtime_sec=item.get("est_runtime_sec"),
        tags=item.get("tags"),
        variables=item.get("variables", []),
        access_info=item.get("access"),
        supported_os=item.get("supported_os"),
        script_bash=_script_for(item),
        script_powershell=item.get("script_powershell"),
        is_official=True,
        is_public=True,
    )


async def seed_if_empty(db: AsyncSession) -> None:
    """Seed official playbooks if the table is empty."""
    result = await db.execute(select(Playbook).limit(1))
    if result.scalar_one_or_none() is not None:
        return

    logger.info("Seeding %d official playbooks...", len(OFFICIAL_PLAYBOOKS))
    for item in OFFICIAL_PLAYBOOKS:
        db.add(_build_playbook(item))

    await db.commit()
    logger.info("Playbook seed complete.")


async def resync_official_scripts(db: AsyncSession) -> dict:
    """Upsert official playbooks against the current definitions (matched by slug):
    update existing rows' scripts/access and INSERT any new playbooks. Use after
    editing or adding playbooks. Preserves run_count/rating. Returns counts.
    """
    from sqlalchemy import update as sa_update

    existing = set((await db.execute(select(Playbook.slug))).scalars().all())
    updated = inserted = 0
    for item in OFFICIAL_PLAYBOOKS:
        if item["slug"] in existing:
            await db.execute(
                sa_update(Playbook)
                .where(Playbook.slug == item["slug"])
                .values(
                    script_bash=_script_for(item),
                    script_powershell=item.get("script_powershell"),
                    access_info=item.get("access"),
                    variables=item.get("variables", []),
                    supported_os=item.get("supported_os"),
                )
            )
            updated += 1
        else:
            db.add(_build_playbook(item))
            inserted += 1
    await db.commit()
    return {"updated": updated, "inserted": inserted}


def substitute_variables(script: str, variables: dict) -> str:
    """Replace {{VAR_NAME}} placeholders with provided values."""
    for key, value in variables.items():
        script = script.replace("{{" + key + "}}", str(value))
    return script
