"""Playbook service — seed data and execution helpers."""
from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.playbook import Playbook

logger = logging.getLogger(__name__)

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
    "  if command -v ss >/dev/null 2>&1 && ss -tln 2>/dev/null | grep -qE ':80[[:space:]]'; then echo \">>> ERROR: Port 80 is already in use. $panel needs a clean server.\"; exit 1; fi\n"
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
        "variables": [
            {"name": "PHP_VERSION", "label": "PHP Version", "default": "8.3", "required": True},
            {"name": "MYSQL_ROOT_PASS", "label": "MySQL Root Password", "default": "", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PHP_VERSION="{{PHP_VERSION}}"\n'
            'MYSQL_ROOT_PASS="{{MYSQL_ROOT_PASS}}"\n'
            'echo "Installing LEMP stack..."\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq nginx\n"
            "systemctl enable --now nginx\n"
            "apt-get install -y -qq mysql-server\n"
            "systemctl enable --now mysql\n"
            'if [ -n "$MYSQL_ROOT_PASS" ]; then\n'
            "  mysql -e \"ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY '$MYSQL_ROOT_PASS'; FLUSH PRIVILEGES;\"\n"
            "fi\n"
            "apt-get install -y -qq software-properties-common\n"
            "add-apt-repository -y ppa:ondrej/php\n"
            "apt-get update -qq\n"
            'apt-get install -y -qq php${PHP_VERSION}-fpm php${PHP_VERSION}-mysql php${PHP_VERSION}-curl php${PHP_VERSION}-gd php${PHP_VERSION}-mbstring php${PHP_VERSION}-xml php${PHP_VERSION}-zip\n'
            "systemctl enable --now php${PHP_VERSION}-fpm\n"
            'echo "Nginx: $(nginx -v 2>&1)"\n'
            'echo "MySQL: $(mysql --version)"\n'
            'echo "PHP: $(php -v | head -1)"\n'
            'echo "LEMP stack installed."\n'
        ),
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
        "variables": [
            {"name": "PHP_VERSION", "label": "PHP Version", "default": "8.3", "required": True}
        ],
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'PHP_VERSION="{{PHP_VERSION}}"\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq apache2 mysql-server\n"
            "a2enmod rewrite\n"
            "systemctl enable --now apache2 mysql\n"
            "apt-get install -y -qq software-properties-common\n"
            "add-apt-repository -y ppa:ondrej/php\n"
            "apt-get update -qq\n"
            'apt-get install -y -qq php${PHP_VERSION} libapache2-mod-php${PHP_VERSION} php${PHP_VERSION}-mysql php${PHP_VERSION}-curl php${PHP_VERSION}-gd php${PHP_VERSION}-mbstring php${PHP_VERSION}-xml php${PHP_VERSION}-zip\n'
            "systemctl restart apache2\n"
            'echo "Apache: $(apache2 -v | head -1)"\n'
            'echo "PHP: $(php -v | head -1)"\n'
            'echo "LAMP stack installed."\n'
        ),
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
            'echo "=== ServerMind Security Audit: $(date) ==="\n'
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
        "script_bash": (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            'DOMAIN="{{DOMAIN}}"\n'
            'DB_NAME="{{DB_NAME}}"\n'
            'DB_USER="{{DB_USER}}"\n'
            'DB_PASS="{{DB_PASS}}"\n'
            'ADMIN_EMAIL="{{ADMIN_EMAIL}}"\n'
            'WEB_ROOT="/var/www/${DOMAIN}"\n'
            'echo "=== Installing dependencies ==="\n'
            "apt-get update -qq\n"
            "apt-get install -y -qq nginx mysql-server php8.2-fpm php8.2-mysql php8.2-curl php8.2-gd php8.2-mbstring php8.2-xml php8.2-zip certbot python3-certbot-nginx wget\n"
            'echo "=== Setting up database ==="\n'
            'mysql -e "CREATE DATABASE IF NOT EXISTS ${DB_NAME} CHARACTER SET utf8mb4;"\n'
            'mysql -e "CREATE USER IF NOT EXISTS \'${DB_USER}\'@\'localhost\' IDENTIFIED BY \'${DB_PASS}\';"\n'
            'mysql -e "GRANT ALL PRIVILEGES ON ${DB_NAME}.* TO \'${DB_USER}\'@\'localhost\'; FLUSH PRIVILEGES;"\n'
            'echo "=== Installing WordPress ==="\n'
            'mkdir -p "$WEB_ROOT"\n'
            "wget -q https://wordpress.org/latest.tar.gz -O /tmp/wp.tar.gz\n"
            "tar -xzf /tmp/wp.tar.gz -C /tmp/\n"
            'cp -r /tmp/wordpress/* "$WEB_ROOT/"\n'
            'chown -R www-data:www-data "$WEB_ROOT"\n'
            'cp "${WEB_ROOT}/wp-config-sample.php" "${WEB_ROOT}/wp-config.php"\n'
            'sed -i "s/database_name_here/$DB_NAME/; s/username_here/$DB_USER/; s/password_here/$DB_PASS/" "${WEB_ROOT}/wp-config.php"\n'
            'echo "=== Configuring Nginx ==="\n'
            'printf "server {\\n  listen 80;\\n  server_name %s;\\n  root %s;\\n  index index.php;\\n  location / { try_files \\$uri \\$uri/ /index.php?\\$args; }\\n  location ~ \\.php$ { include snippets/fastcgi-php.conf; fastcgi_pass unix:/run/php/php8.2-fpm.sock; }\\n}\\n" "$DOMAIN" "$WEB_ROOT" > "/etc/nginx/sites-available/${DOMAIN}"\n'
            'ln -sf "/etc/nginx/sites-available/${DOMAIN}" /etc/nginx/sites-enabled/\n'
            "nginx -t && systemctl reload nginx\n"
            'certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m "$ADMIN_EMAIL" --redirect || echo "SSL skipped"\n'
            'echo "WordPress ready: https://${DOMAIN}/wp-admin/install.php"\n'
        ),
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
            "in Hosting Mode to manage sites, databases and email from ServerMind."
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
            "Write-Host '=== ServerMind Windows Security Audit ==='\n"
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
