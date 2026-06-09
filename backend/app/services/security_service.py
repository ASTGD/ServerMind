"""Security audit service.

Runs a battery of *read-only* diagnostic commands against a server, parses the
output, and produces a scored list of findings. To stay fast we collect every
diagnostic into a single shell script delimited by sentinels, run it in one
round-trip via :func:`connection_manager.execute`, then split the output back
into sections and evaluate each check independently.

All commands are read-only. Suggested remediation commands (``fix_command``) are
returned to the user for display only — they are NEVER executed automatically.
"""
from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from dataclasses import dataclass

from app.models.server import Server
from app.services import connection_manager

logger = logging.getLogger(__name__)

# ── Severity model ──────────────────────────────────────────────────────────

SEVERITY_WEIGHTS: dict[str, int] = {
    "critical": 25,
    "high": 12,
    "medium": 6,
    "low": 2,
    "pass": 0,
    "info": 0,
    "unknown": 0,
}

_SECTION_RE = re.compile(r"^__SMSEC__([a-zA-Z0-9_]+)__$", re.MULTILINE)


def _marker(section_id: str) -> str:
    return f"__SMSEC__{section_id}__"


# ── Data structures ─────────────────────────────────────────────────────────

@dataclass
class Section:
    """A shell command whose raw output feeds one or more checks."""

    id: str
    command: str


@dataclass
class Check:
    """A single security check. Reads the raw output of ``section`` and returns
    a finding dict via ``evaluate(raw, ctx)``."""

    id: str
    title: str
    category: str
    section: str
    evaluate: Callable[[str, dict], dict]
    description: str = ""


def _finding(
    check: Check,
    *,
    severity: str,
    status: str,
    detail: str | None = None,
    recommendation: str | None = None,
    fix_command: str | None = None,
    description: str | None = None,
) -> dict:
    return {
        "id": check.id,
        "title": check.title,
        "category": check.category,
        "severity": severity,
        "status": status,
        "description": description or check.description,
        "detail": detail,
        "recommendation": recommendation,
        "fix_command": fix_command,
    }


# ── Small parse helpers ─────────────────────────────────────────────────────

def _kv(raw: str) -> dict[str, str]:
    """Parse ``key=value`` lines (value may contain spaces) into a dict."""
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


def _sshd_conf(raw: str) -> dict[str, str]:
    """Parse lowercased ``key value`` sshd config lines into a dict."""
    out: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            out.setdefault(parts[0], parts[1].strip())
    return out


# ═══════════════════════════════════════════════════════════════════════════
# LINUX
# ═══════════════════════════════════════════════════════════════════════════

LINUX_SECTIONS: list[Section] = [
    Section("meta", (
        'echo "uid=$(id -u 2>/dev/null)"; '
        'echo "user=$(id -un 2>/dev/null)"; '
        'echo "kernel=$(uname -r 2>/dev/null)"; '
        'echo "host=$(hostname 2>/dev/null)"; '
        '( . /etc/os-release 2>/dev/null; echo "os=${PRETTY_NAME:-unknown}" )'
    )),
    Section("sshd", (
        '(sshd -T 2>/dev/null || /usr/sbin/sshd -T 2>/dev/null '
        "|| grep -vE '^[[:space:]]*#' /etc/ssh/sshd_config 2>/dev/null) "
        "| tr 'A-Z' 'a-z'"
    )),
    Section("firewall", (
        'echo "ufw=$(ufw status 2>/dev/null | head -1 | tr -d "\\n")"; '
        'echo "firewalld=$(systemctl is-active firewalld 2>/dev/null)"; '
        'echo "iptables_rules=$(iptables -S 2>/dev/null | grep -vcE \'^-P\')"; '
        'echo "iptables_drop=$(iptables -S 2>/dev/null | grep -cE \'^-P (INPUT|FORWARD) DROP\')"; '
        'echo "nft=$(nft list ruleset 2>/dev/null | grep -c .)"'
    )),
    Section("fail2ban", (
        'echo "active=$(systemctl is-active fail2ban 2>/dev/null)"; '
        'echo "installed=$(command -v fail2ban-client >/dev/null 2>&1 && echo yes || echo no)"'
    )),
    Section("updates", (
        'if command -v apt-get >/dev/null 2>&1; then '
        '  U=$(apt-get -s upgrade 2>/dev/null | grep -cE \'^Inst\'); '
        '  S=$(apt-get -s upgrade 2>/dev/null | grep -E \'^Inst\' | grep -ciE \'security\'); '
        '  echo "mgr=apt"; echo "updates=$U"; echo "security=$S"; '
        'elif command -v dnf >/dev/null 2>&1; then '
        '  U=$(dnf -q check-update 2>/dev/null | grep -cE \'^[a-zA-Z0-9]\'); '
        '  S=$(dnf -q updateinfo list security 2>/dev/null | grep -ciE \'/Sec|security\'); '
        '  echo "mgr=dnf"; echo "updates=$U"; echo "security=$S"; '
        'elif command -v yum >/dev/null 2>&1; then '
        '  S=$(yum -q updateinfo list security 2>/dev/null | grep -ciE \'/Sec|security\'); '
        '  echo "mgr=yum"; echo "security=$S"; '
        'else echo "mgr=unknown"; fi'
    )),
    Section("autoupdate", (
        'echo "unattended=$(dpkg -l unattended-upgrades 2>/dev/null | grep -c \'^ii\')"; '
        'echo "apt_periodic=$(grep -hsriE \'Unattended-Upgrade[[:space:]]*\\"1\\"\' '
        '/etc/apt/apt.conf.d/ 2>/dev/null | grep -c .)"; '
        'echo "dnf_auto=$(systemctl is-active dnf-automatic.timer 2>/dev/null)"'
    )),
    Section("shadow", (
        'echo "empty=$(awk -F: \'($2==""){print $1}\' /etc/shadow 2>&1 | tr \'\\n\' \',\')"; '
        'echo "perm=$(stat -c \'%a\' /etc/shadow 2>/dev/null)"'
    )),
    Section("uid0", (
        "awk -F: '($3==0){print $1}' /etc/passwd 2>/dev/null | tr '\\n' ' '"
    )),
    Section("sudoers", (
        "grep -rhE 'NOPASSWD' /etc/sudoers /etc/sudoers.d/ 2>&1 "
        "| grep -vE '^[[:space:]]*#' | tr '\\n' ';'"
    )),
    Section("logindefs", (
        "grep -E '^[[:space:]]*(PASS_MAX_DAYS|PASS_MIN_LEN|PASS_MIN_DAYS)' "
        "/etc/login.defs 2>/dev/null"
    )),
    Section("worldwritable", (
        'WW=$(find /etc /usr/bin /usr/sbin /bin /sbin -xdev -type f -perm -0002 2>/dev/null); '
        'echo "count=$(printf \'%s\\n\' "$WW" | grep -c .)"; '
        'printf \'%s\' "$WW" | head -15 | tr \'\\n\' \' \''
    )),
    Section("suid", (
        "find /usr/bin /usr/sbin /bin /sbin /usr/local/bin /usr/local/sbin "
        "-xdev -type f -perm -4000 2>/dev/null | tr '\\n' ' '"
    )),
    Section("perms", (
        'echo "shadow=$(stat -c \'%a %U %G\' /etc/shadow 2>/dev/null)"; '
        'echo "passwd=$(stat -c \'%a %U %G\' /etc/passwd 2>/dev/null)"; '
        'echo "gshadow=$(stat -c \'%a %U %G\' /etc/gshadow 2>/dev/null)"'
    )),
    Section("listening", (
        "(ss -tlnH 2>/dev/null || netstat -tln 2>/dev/null) | awk '{print $4}'"
    )),
    Section("mac", (
        'echo "selinux=$(getenforce 2>/dev/null || echo none)"; '
        'echo "apparmor=$(aa-status 2>/dev/null | head -1 || echo none)"'
    )),
    Section("reboot", (
        'test -f /var/run/reboot-required && echo "required" || echo "no"'
    )),
]


# ── Linux evaluators ────────────────────────────────────────────────────────

def _eval_ssh_root(raw: str, ctx: dict) -> dict:
    c = _checkmap["ssh_root_login"]
    conf = ctx.setdefault("_sshd", _sshd_conf(raw))
    val = conf.get("permitrootlogin")
    if val is None:
        return _finding(c, severity="unknown", status="unknown",
                        detail="Could not read sshd configuration.",
                        recommendation="Ensure OpenSSH server is installed and the scan user can read its config.")
    if val == "yes":
        return _finding(c, severity="high", status="fail",
                        detail=f"PermitRootLogin = {val}",
                        recommendation="Disable direct root SSH login. Use a sudo-enabled account instead.",
                        fix_command="sudo sed -i 's/^#\\?PermitRootLogin.*/PermitRootLogin no/' /etc/ssh/sshd_config && sudo systemctl restart sshd")
    return _finding(c, severity="pass", status="pass",
                    detail=f"PermitRootLogin = {val}",
                    recommendation="Root login over SSH is restricted.")


def _eval_ssh_password(raw: str, ctx: dict) -> dict:
    c = _checkmap["ssh_password_auth"]
    conf = ctx.setdefault("_sshd", _sshd_conf(raw))
    val = conf.get("passwordauthentication")
    if val is None:
        return _finding(c, severity="unknown", status="unknown",
                        detail="Could not read sshd configuration.")
    if val == "yes":
        return _finding(c, severity="medium", status="warn",
                        detail="PasswordAuthentication = yes",
                        recommendation="Prefer key-based authentication and disable password auth once keys are set up.",
                        fix_command="sudo sed -i 's/^#\\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && sudo systemctl restart sshd")
    return _finding(c, severity="pass", status="pass",
                    detail=f"PasswordAuthentication = {val}",
                    recommendation="Password authentication is disabled — key-only access.")


def _eval_ssh_empty_pw(raw: str, ctx: dict) -> dict:
    c = _checkmap["ssh_empty_passwords"]
    conf = ctx.setdefault("_sshd", _sshd_conf(raw))
    val = conf.get("permitemptypasswords")
    if val == "yes":
        return _finding(c, severity="high", status="fail",
                        detail="PermitEmptyPasswords = yes",
                        recommendation="Never allow empty passwords over SSH.",
                        fix_command="sudo sed -i 's/^#\\?PermitEmptyPasswords.*/PermitEmptyPasswords no/' /etc/ssh/sshd_config && sudo systemctl restart sshd")
    if val is None:
        return _finding(c, severity="unknown", status="unknown", detail="Could not read sshd configuration.")
    return _finding(c, severity="pass", status="pass", detail=f"PermitEmptyPasswords = {val}")


def _eval_ssh_max_auth(raw: str, ctx: dict) -> dict:
    c = _checkmap["ssh_max_auth_tries"]
    conf = ctx.setdefault("_sshd", _sshd_conf(raw))
    val = conf.get("maxauthtries")
    if val is None:
        return _finding(c, severity="unknown", status="unknown", detail="Not configured.")
    try:
        n = int(val)
    except ValueError:
        return _finding(c, severity="unknown", status="unknown", detail=f"MaxAuthTries = {val}")
    if n > 4:
        return _finding(c, severity="low", status="warn",
                        detail=f"MaxAuthTries = {n}",
                        recommendation="Lower MaxAuthTries to 3-4 to slow brute-force attempts.",
                        fix_command="sudo sed -i 's/^#\\?MaxAuthTries.*/MaxAuthTries 4/' /etc/ssh/sshd_config && sudo systemctl restart sshd")
    return _finding(c, severity="pass", status="pass", detail=f"MaxAuthTries = {n}")


def _eval_ssh_port(raw: str, ctx: dict) -> dict:
    c = _checkmap["ssh_port"]
    conf = ctx.setdefault("_sshd", _sshd_conf(raw))
    val = conf.get("port", "22")
    return _finding(c, severity="info", status="info",
                    detail=f"SSH listening on port {val}",
                    recommendation=None if val != "22" else "Default port 22 is fine; a non-standard port reduces automated scan noise but is not a security control by itself.")


def _eval_firewall(raw: str, ctx: dict) -> dict:
    c = _checkmap["firewall_active"]
    kv = _kv(raw)
    ufw = kv.get("ufw", "").lower()
    firewalld = kv.get("firewalld", "")
    try:
        ipt_rules = int(kv.get("iptables_rules", "0") or 0)
    except ValueError:
        ipt_rules = 0
    try:
        ipt_drop = int(kv.get("iptables_drop", "0") or 0)
    except ValueError:
        ipt_drop = 0
    try:
        nft = int(kv.get("nft", "0") or 0)
    except ValueError:
        nft = 0

    # NB: "inactive" contains the substring "active" — must exclude it explicitly.
    ufw_active = "active" in ufw and "inactive" not in ufw
    active = ufw_active or firewalld == "active" or ipt_rules > 0 or ipt_drop > 0 or nft > 0
    if active:
        which = []
        if ufw_active:
            which.append("ufw")
        if firewalld == "active":
            which.append("firewalld")
        if ipt_rules > 0 or ipt_drop > 0:
            which.append("iptables")
        if nft > 0:
            which.append("nftables")
        return _finding(c, severity="pass", status="pass",
                        detail=f"Active firewall: {', '.join(which) or 'rules present'}")
    return _finding(c, severity="high", status="fail",
                    detail="No active firewall detected (ufw inactive, firewalld inactive, no iptables/nft rules).",
                    recommendation="Enable a host firewall and allow only required ports (e.g. SSH, HTTP, HTTPS).",
                    fix_command="sudo ufw allow OpenSSH && sudo ufw --force enable")


def _eval_fail2ban(raw: str, ctx: dict) -> dict:
    c = _checkmap["fail2ban"]
    kv = _kv(raw)
    if kv.get("active") == "active":
        return _finding(c, severity="pass", status="pass", detail="fail2ban is installed and running.")
    if kv.get("installed") == "yes":
        return _finding(c, severity="low", status="warn",
                        detail="fail2ban is installed but not active.",
                        recommendation="Start and enable fail2ban to block repeated failed logins.",
                        fix_command="sudo systemctl enable --now fail2ban")
    return _finding(c, severity="medium", status="fail",
                    detail="fail2ban is not installed.",
                    recommendation="Install fail2ban to automatically ban hosts after repeated failed SSH logins.",
                    fix_command="sudo apt-get install -y fail2ban && sudo systemctl enable --now fail2ban")


def _eval_updates(raw: str, ctx: dict) -> dict:
    c = _checkmap["pending_updates"]
    kv = _kv(raw)
    mgr = kv.get("mgr", "unknown")
    if mgr == "unknown":
        return _finding(c, severity="unknown", status="unknown",
                        detail="No supported package manager detected.")
    try:
        sec = int(kv.get("security", "0") or 0)
    except ValueError:
        sec = 0
    try:
        total = int(kv.get("updates", "0") or 0)
    except ValueError:
        total = 0
    fix = "sudo apt-get update && sudo apt-get upgrade -y" if mgr == "apt" else f"sudo {mgr} upgrade -y"
    if sec > 0:
        sev = "high" if sec >= 5 else "medium"
        return _finding(c, severity=sev, status="fail",
                        detail=f"{sec} pending security update(s){f', {total} total' if total else ''} ({mgr}).",
                        recommendation="Apply outstanding security updates promptly.",
                        fix_command=fix)
    if total > 0:
        return _finding(c, severity="low", status="warn",
                        detail=f"{total} package update(s) available, none flagged security ({mgr}).",
                        recommendation="Keep packages current to reduce exposure.",
                        fix_command=fix)
    return _finding(c, severity="pass", status="pass", detail=f"System is up to date ({mgr}).")


def _eval_autoupdate(raw: str, ctx: dict) -> dict:
    c = _checkmap["unattended_upgrades"]
    kv = _kv(raw)
    try:
        unattended = int(kv.get("unattended", "0") or 0)
    except ValueError:
        unattended = 0
    try:
        periodic = int(kv.get("apt_periodic", "0") or 0)
    except ValueError:
        periodic = 0
    dnf_auto = kv.get("dnf_auto", "")
    if (unattended > 0 and periodic > 0) or dnf_auto == "active":
        return _finding(c, severity="pass", status="pass", detail="Automatic security updates are enabled.")
    return _finding(c, severity="low", status="warn",
                    detail="Automatic/unattended security updates are not fully enabled.",
                    recommendation="Enable unattended security updates so critical patches apply without manual action.",
                    fix_command="sudo apt-get install -y unattended-upgrades && sudo dpkg-reconfigure -plow unattended-upgrades")


def _eval_empty_pw_accounts(raw: str, ctx: dict) -> dict:
    c = _checkmap["empty_password_accounts"]
    kv = _kv(raw)
    empty = kv.get("empty", "")
    if "permission denied" in empty.lower():
        return _finding(c, severity="unknown", status="unknown",
                        detail="Could not read /etc/shadow (scan user lacks root).",
                        recommendation="Re-run the scan as root (or a sudo-enabled user) to audit password hashes.")
    accounts = [a for a in empty.split(",") if a.strip()]
    if accounts:
        return _finding(c, severity="critical", status="fail",
                        detail=f"Accounts with empty password: {', '.join(accounts)}",
                        recommendation="Set or lock passwords for these accounts immediately.",
                        fix_command=f"sudo passwd -l {accounts[0]}")
    if not ctx.get("is_root"):
        return _finding(c, severity="unknown", status="unknown",
                        detail="Could not read /etc/shadow (scan user lacks root).",
                        recommendation="Re-run the scan as root to audit for empty passwords.")
    return _finding(c, severity="pass", status="pass", detail="No accounts with empty passwords.")


def _eval_uid0(raw: str, ctx: dict) -> dict:
    c = _checkmap["uid0_accounts"]
    users = [u for u in raw.split() if u.strip()]
    extra = [u for u in users if u != "root"]
    if extra:
        return _finding(c, severity="critical", status="fail",
                        detail=f"Non-root accounts with UID 0: {', '.join(extra)}",
                        recommendation="Remove UID 0 from these accounts — only root should have UID 0.")
    if "root" in users:
        return _finding(c, severity="pass", status="pass", detail="Only root has UID 0.")
    return _finding(c, severity="unknown", status="unknown", detail="Could not read /etc/passwd.")


def _eval_sudoers(raw: str, ctx: dict) -> dict:
    c = _checkmap["sudo_nopasswd"]
    if "permission denied" in raw.lower():
        return _finding(c, severity="unknown", status="unknown",
                        detail="Could not read sudoers (scan user lacks root).",
                        recommendation="Re-run as root to audit passwordless sudo grants.")
    entries = [e for e in raw.split(";") if e.strip()]
    if entries:
        return _finding(c, severity="medium", status="warn",
                        detail=f"{len(entries)} passwordless (NOPASSWD) sudo rule(s) found.",
                        recommendation="Review NOPASSWD sudo rules — passwordless sudo widens blast radius if an account is compromised.",
                        fix_command="sudo visudo")
    return _finding(c, severity="pass", status="pass", detail="No passwordless sudo rules.")


def _eval_logindefs(raw: str, ctx: dict) -> dict:
    c = _checkmap["password_policy"]
    vals: dict[str, int] = {}
    for line in raw.splitlines():
        parts = line.split()
        if len(parts) == 2 and parts[1].lstrip("-").isdigit():
            vals[parts[0]] = int(parts[1])
    max_days = vals.get("PASS_MAX_DAYS")
    if max_days is None:
        return _finding(c, severity="info", status="info", detail="Password aging policy not explicitly set.")
    if max_days > 365 or max_days <= 0:
        return _finding(c, severity="low", status="warn",
                        detail=f"PASS_MAX_DAYS = {max_days}",
                        recommendation="Set a reasonable maximum password age (e.g. 90-365 days).")
    return _finding(c, severity="pass", status="pass", detail=f"PASS_MAX_DAYS = {max_days}")


def _eval_worldwritable(raw: str, ctx: dict) -> dict:
    c = _checkmap["world_writable"]
    kv = _kv(raw)
    try:
        # count line is "count=N"; tolerate trailing tokens just in case
        count = int((kv.get("count", "0") or "0").split()[0])
    except (ValueError, IndexError):
        count = 0
    sample = re.sub(r"count=\d+", "", raw).strip()
    if count > 0:
        return _finding(c, severity="medium", status="warn",
                        detail=f"{count} world-writable file(s) in system directories. e.g. {sample[:300]}",
                        recommendation="Remove world-writable permission from system files (chmod o-w).")
    return _finding(c, severity="pass", status="pass", detail="No world-writable files in system directories.")


_SUID_BASELINE = {
    "sudo", "su", "passwd", "chsh", "chfn", "newgrp", "gpasswd", "mount", "umount",
    "ping", "ping6", "fusermount", "fusermount3", "pkexec", "ssh-keysign",
    "dbus-daemon-launch-helper", "polkit-agent-helper-1", "unix_chkpwd", "chage",
    "expiry", "crontab", "at", "snap-confine", "vmware-user-suid-wrapper",
    "sudoedit", "umount.nfs", "mount.nfs",
}


def _eval_suid(raw: str, ctx: dict) -> dict:
    c = _checkmap["suid_binaries"]
    paths = [p for p in raw.split() if p.strip()]
    unusual = [p for p in paths if p.rsplit("/", 1)[-1] not in _SUID_BASELINE]
    if unusual:
        sample = " ".join(unusual[:12])
        return _finding(c, severity="medium", status="warn",
                        detail=f"{len(unusual)} non-standard SUID binary/binaries: {sample}",
                        recommendation="Review unexpected SUID binaries — remove the SUID bit if not required (sudo chmod u-s <file>).")
    if paths:
        return _finding(c, severity="pass", status="pass",
                        detail=f"{len(paths)} SUID binaries, all standard system tools.")
    return _finding(c, severity="info", status="info", detail="No SUID binaries detected in standard paths.")


def _eval_perms(raw: str, ctx: dict) -> dict:
    c = _checkmap["sensitive_perms"]
    kv = _kv(raw)
    shadow = kv.get("shadow", "")
    if not shadow:
        return _finding(c, severity="unknown", status="unknown", detail="Could not stat /etc/shadow.")
    mode = shadow.split()[0] if shadow.split() else ""
    # Other-readable/writable shadow is dangerous (last octal digit must be 0)
    if mode and mode[-1] != "0":
        return _finding(c, severity="high", status="fail",
                        detail=f"/etc/shadow permissions = {shadow}",
                        recommendation="Restrict /etc/shadow so 'other' has no access.",
                        fix_command="sudo chmod 640 /etc/shadow")
    return _finding(c, severity="pass", status="pass", detail=f"/etc/shadow permissions = {shadow}")


_RISKY_PORTS = {
    "21": "FTP (plaintext)",
    "23": "Telnet (plaintext)",
    "512": "rexec",
    "513": "rlogin",
    "514": "rsh",
    "2049": "NFS",
}
_DB_PORTS = {
    "3306": "MySQL/MariaDB",
    "5432": "PostgreSQL",
    "6379": "Redis",
    "27017": "MongoDB",
    "9200": "Elasticsearch",
    "11211": "Memcached",
}


def _eval_listening(raw: str, ctx: dict) -> dict:
    c = _checkmap["listening_ports"]
    ports_world: set[str] = set()
    ports_all: set[str] = set()
    for line in raw.splitlines():
        addr = line.strip()
        if not addr or ":" not in addr:
            continue
        host, _, port = addr.rpartition(":")
        if not port.isdigit():
            continue
        ports_all.add(port)
        host = host.strip("[]")
        if host in ("0.0.0.0", "::", "*", ""):
            ports_world.add(port)

    risky = sorted(p for p in ports_all if p in _RISKY_PORTS)
    exposed_db = sorted(p for p in ports_world if p in _DB_PORTS)

    if risky:
        names = ", ".join(f"{p} ({_RISKY_PORTS[p]})" for p in risky)
        return _finding(c, severity="medium", status="warn",
                        detail=f"Insecure/plaintext service ports listening: {names}",
                        recommendation="Disable plaintext services (telnet/ftp/rsh) in favour of SSH/SFTP/HTTPS.")
    if exposed_db:
        names = ", ".join(f"{p} ({_DB_PORTS[p]})" for p in exposed_db)
        return _finding(c, severity="medium", status="warn",
                        detail=f"Database/cache ports bound to all interfaces: {names}",
                        recommendation="Bind databases to localhost or restrict access via firewall — they should not be world-reachable.")
    if ports_all:
        ordered = ", ".join(sorted(ports_all, key=lambda x: int(x)))
        return _finding(c, severity="info", status="info",
                        detail=f"{len(ports_all)} listening TCP port(s): {ordered}")
    return _finding(c, severity="info", status="info", detail="No listening TCP ports detected.")


def _eval_mac(raw: str, ctx: dict) -> dict:
    c = _checkmap["mac_enabled"]
    kv = _kv(raw)
    selinux = kv.get("selinux", "none").lower()
    apparmor = kv.get("apparmor", "none").lower()
    if selinux == "enforcing" or "module is loaded" in apparmor:
        which = "SELinux (enforcing)" if selinux == "enforcing" else "AppArmor"
        return _finding(c, severity="pass", status="pass", detail=f"Mandatory access control active: {which}")
    if selinux == "permissive":
        return _finding(c, severity="low", status="warn",
                        detail="SELinux is in permissive mode (logging only, not enforcing).",
                        recommendation="Switch SELinux to enforcing once policy issues are resolved.")
    return _finding(c, severity="low", status="warn",
                    detail="No mandatory access control (SELinux/AppArmor) detected as active.",
                    recommendation="Enable AppArmor (Debian/Ubuntu) or SELinux (RHEL family) for defence in depth.")


def _eval_reboot(raw: str, ctx: dict) -> dict:
    c = _checkmap["reboot_required"]
    if "required" in raw:
        return _finding(c, severity="medium", status="warn",
                        detail="A reboot is required to finish applying updates (likely a kernel update).",
                        recommendation="Schedule a reboot so kernel/security patches take effect.",
                        fix_command="sudo reboot")
    return _finding(c, severity="pass", status="pass", detail="No pending reboot required.")


LINUX_CHECKS: list[Check] = [
    Check("ssh_root_login", "SSH root login", "ssh", "sshd", _eval_ssh_root,
          "Direct root login over SSH should be disabled."),
    Check("ssh_password_auth", "SSH password authentication", "ssh", "sshd", _eval_ssh_password,
          "Key-based auth is preferred over passwords."),
    Check("ssh_empty_passwords", "SSH empty passwords", "ssh", "sshd", _eval_ssh_empty_pw,
          "Empty passwords must never be permitted over SSH."),
    Check("ssh_max_auth_tries", "SSH max auth tries", "ssh", "sshd", _eval_ssh_max_auth,
          "Limit authentication attempts to slow brute-force."),
    Check("ssh_port", "SSH listening port", "ssh", "sshd", _eval_ssh_port,
          "Which port the SSH daemon listens on."),
    Check("firewall_active", "Host firewall", "firewall", "firewall", _eval_firewall,
          "A host firewall should restrict inbound traffic."),
    Check("fail2ban", "Brute-force protection (fail2ban)", "firewall", "fail2ban", _eval_fail2ban,
          "fail2ban bans hosts after repeated failed logins."),
    Check("pending_updates", "Pending security updates", "updates", "updates", _eval_updates,
          "Outstanding security updates should be applied."),
    Check("unattended_upgrades", "Automatic security updates", "updates", "autoupdate", _eval_autoupdate,
          "Critical patches should apply automatically."),
    Check("empty_password_accounts", "Accounts without passwords", "accounts", "shadow", _eval_empty_pw_accounts,
          "No account should have an empty password."),
    Check("uid0_accounts", "Privileged (UID 0) accounts", "accounts", "uid0", _eval_uid0,
          "Only root should have UID 0."),
    Check("sudo_nopasswd", "Passwordless sudo", "accounts", "sudoers", _eval_sudoers,
          "Passwordless sudo widens the blast radius of a compromise."),
    Check("password_policy", "Password aging policy", "accounts", "logindefs", _eval_logindefs,
          "Passwords should have a sane maximum age."),
    Check("world_writable", "World-writable system files", "filesystem", "worldwritable", _eval_worldwritable,
          "System files should not be writable by everyone."),
    Check("suid_binaries", "SUID/SGID binaries", "filesystem", "suid", _eval_suid,
          "Unexpected SUID binaries are a privilege-escalation risk."),
    Check("sensitive_perms", "Sensitive file permissions", "filesystem", "perms", _eval_perms,
          "/etc/shadow and friends must be tightly permissioned."),
    Check("listening_ports", "Listening network services", "services", "listening", _eval_listening,
          "Open ports widen the attack surface."),
    Check("mac_enabled", "Mandatory access control", "hardening", "mac", _eval_mac,
          "SELinux/AppArmor add defence in depth."),
    Check("reboot_required", "Pending reboot", "kernel", "reboot", _eval_reboot,
          "A pending reboot means patches are not yet active."),
]


# ═══════════════════════════════════════════════════════════════════════════
# WINDOWS (PowerShell) — staged for Phase 2B (WinRM). Defined now so the audit
# battery is ready the moment connection_manager supports winrm.
# ═══════════════════════════════════════════════════════════════════════════

WINDOWS_SECTIONS: list[Section] = [
    Section("firewall", "(Get-NetFirewallProfile | ForEach-Object { \"$($_.Name)=$($_.Enabled)\" }) -join ';'"),
    Section("defender", "$s = Get-MpComputerStatus; \"realtime=$($s.RealTimeProtectionEnabled);antivirus=$($s.AntivirusEnabled)\""),
    Section("rdp", "\"deny=$((Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server').fDenyTSConnections);nla=$((Get-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp').UserAuthentication)\""),
    Section("smb1", "\"smb1=$((Get-SmbServerConfiguration).EnableSMB1Protocol)\""),
    Section("uac", "\"uac=$((Get-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System').EnableLUA)\""),
]


def _eval_win_firewall(raw: str, ctx: dict) -> dict:
    c = _checkmap["win_firewall"]
    profiles = _kv(raw.replace(";", "\n"))
    disabled = [k for k, v in profiles.items() if v.lower() in ("false", "0")]
    if disabled:
        return _finding(c, severity="high", status="fail",
                        detail=f"Firewall disabled for profile(s): {', '.join(disabled)}",
                        recommendation="Enable Windows Firewall for all profiles.",
                        fix_command="Set-NetFirewallProfile -All -Enabled True")
    if profiles:
        return _finding(c, severity="pass", status="pass", detail="Windows Firewall enabled for all profiles.")
    return _finding(c, severity="unknown", status="unknown", detail="Could not read firewall state.")


def _eval_win_defender(raw: str, ctx: dict) -> dict:
    c = _checkmap["win_defender"]
    kv = _kv(raw.replace(";", "\n"))
    if kv.get("realtime", "").lower() == "true":
        return _finding(c, severity="pass", status="pass", detail="Defender real-time protection enabled.")
    return _finding(c, severity="high", status="fail",
                    detail=f"Real-time protection: {kv.get('realtime', 'unknown')}",
                    recommendation="Enable Microsoft Defender real-time protection or a supported AV.",
                    fix_command="Set-MpPreference -DisableRealtimeMonitoring $false")


def _eval_win_rdp(raw: str, ctx: dict) -> dict:
    c = _checkmap["win_rdp_nla"]
    kv = _kv(raw.replace(";", "\n"))
    if kv.get("deny") == "1":
        return _finding(c, severity="info", status="info", detail="RDP is disabled.")
    if kv.get("nla") == "1":
        return _finding(c, severity="pass", status="pass", detail="RDP enabled with Network Level Authentication.")
    return _finding(c, severity="medium", status="warn",
                    detail="RDP enabled without Network Level Authentication.",
                    recommendation="Require NLA for RDP to mitigate pre-auth attacks.",
                    fix_command="Set-ItemProperty 'HKLM:\\System\\CurrentControlSet\\Control\\Terminal Server\\WinStations\\RDP-Tcp' -Name UserAuthentication -Value 1")


def _eval_win_smb1(raw: str, ctx: dict) -> dict:
    c = _checkmap["win_smb1"]
    kv = _kv(raw.replace(";", "\n"))
    if kv.get("smb1", "").lower() == "true":
        return _finding(c, severity="high", status="fail",
                        detail="SMBv1 is enabled (legacy, vulnerable).",
                        recommendation="Disable SMBv1 — it is obsolete and exploited by worms (e.g. WannaCry).",
                        fix_command="Set-SmbServerConfiguration -EnableSMB1Protocol $false -Force")
    return _finding(c, severity="pass", status="pass", detail="SMBv1 is disabled.")


def _eval_win_uac(raw: str, ctx: dict) -> dict:
    c = _checkmap["win_uac"]
    kv = _kv(raw.replace(";", "\n"))
    if kv.get("uac") == "1":
        return _finding(c, severity="pass", status="pass", detail="User Account Control is enabled.")
    return _finding(c, severity="medium", status="warn",
                    detail="User Account Control is disabled.",
                    recommendation="Enable UAC to require elevation for administrative actions.",
                    fix_command="Set-ItemProperty 'HKLM:\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Policies\\System' -Name EnableLUA -Value 1")


WINDOWS_CHECKS: list[Check] = [
    Check("win_firewall", "Windows Firewall", "firewall", "firewall", _eval_win_firewall,
          "Windows Firewall should be enabled for all profiles."),
    Check("win_defender", "Antivirus / Defender", "hardening", "defender", _eval_win_defender,
          "Real-time malware protection should be active."),
    Check("win_rdp_nla", "RDP Network Level Authentication", "services", "rdp", _eval_win_rdp,
          "RDP should require NLA."),
    Check("win_smb1", "SMBv1 protocol", "services", "smb1", _eval_win_smb1,
          "The legacy SMBv1 protocol should be disabled."),
    Check("win_uac", "User Account Control", "hardening", "uac", _eval_win_uac,
          "UAC should require elevation for admin actions."),
]


# Lookup of every check by id (used inside evaluators via _checkmap[...])
_checkmap: dict[str, Check] = {c.id: c for c in (LINUX_CHECKS + WINDOWS_CHECKS)}


# ── Script build / parse ────────────────────────────────────────────────────

def _build_script(sections: list[Section]) -> str:
    """Compose all sections into a single defensive POSIX-sh script."""
    parts: list[str] = ["export LC_ALL=C"]
    for s in sections:
        parts.append(f"printf '\\n{_marker(s.id)}\\n'")
        # Wrap each section in a subshell so variables don't leak and a failure
        # in one section never aborts the whole script.
        parts.append(f"( {s.command} ) 2>&1 || true")
    return "\n".join(parts)


def _build_ps_script(sections: list[Section]) -> str:
    """Compose all sections into a single PowerShell script."""
    parts: list[str] = ["$ErrorActionPreference = 'SilentlyContinue'"]
    for s in sections:
        parts.append(f'Write-Output "{_marker(s.id)}"')
        parts.append(f"try {{ {s.command} }} catch {{ }}")
    return "\n".join(parts)


def _parse_sections(output: str) -> dict[str, str]:
    """Split combined output back into {section_id: raw_text}."""
    sections: dict[str, str] = {}
    matches = list(_SECTION_RE.finditer(output))
    for i, m in enumerate(matches):
        sid = m.group(1)
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(output)
        sections[sid] = output[start:end].strip()
    return sections


def _grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 75:
        return "B"
    if score >= 60:
        return "C"
    if score >= 40:
        return "D"
    return "F"


def _score(findings: list[dict]) -> tuple[int, str, dict[str, int]]:
    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0, "pass": 0, "info": 0}
    penalty = 0
    for f in findings:
        sev = f["severity"]
        penalty += SEVERITY_WEIGHTS.get(sev, 0)
        if sev in counts:
            counts[sev] += 1
        elif sev == "unknown":
            counts["info"] += 1
    score = max(0, 100 - penalty)
    return score, _grade(score), counts


# ── Public API ──────────────────────────────────────────────────────────────

def _os_family(server: Server) -> str:
    shell = (server.shell or "").lower()
    os_type = (server.os_type or "").lower()
    if "powershell" in shell or os_type == "windows":
        return "windows"
    return "linux"


def _failed_result(started: float, error: str) -> dict:
    return {
        "score": 0, "grade": "F", "status": "failed", "error": error,
        "counts": {"critical": 0, "high": 0, "medium": 0, "low": 0, "pass": 0, "info": 0},
        "findings": [], "duration_ms": int((time.monotonic() - started) * 1000),
    }


async def run_scan(server: Server) -> dict:
    """Run a full security audit against ``server``.

    Returns a dict: ``{score, grade, counts, findings, duration_ms, status, error}``.
    Never raises — connection/transport failures are captured into the result.
    """
    started = time.monotonic()
    family = _os_family(server)
    sections = WINDOWS_SECTIONS if family == "windows" else LINUX_SECTIONS
    checks = WINDOWS_CHECKS if family == "windows" else LINUX_CHECKS
    script = _build_ps_script(sections) if family == "windows" else _build_script(sections)

    try:
        stdout, stderr, _exit = await connection_manager.execute(server, script)
    except NotImplementedError:
        return _failed_result(
            started,
            f"Security scan for '{server.connection_type}' connections is not supported yet.",
        )
    except Exception as exc:  # noqa: BLE001 — transport errors are reported, not raised
        logger.warning("Security scan failed for server %s: %s", server.id, exc)
        return _failed_result(started, f"Could not connect to the server: {exc}")

    raw_sections = _parse_sections(stdout or "")

    # Establish context from the meta section (Linux only).
    ctx: dict = {"os_family": family}
    meta = _kv(raw_sections.get("meta", ""))
    ctx["is_root"] = meta.get("uid") == "0"

    findings: list[dict] = []
    for check in checks:
        raw = raw_sections.get(check.section, "")
        try:
            findings.append(check.evaluate(raw, ctx))
        except Exception as exc:  # noqa: BLE001 — one bad evaluator must not kill the scan
            logger.exception("Evaluator '%s' raised", check.id)
            findings.append(_finding(check, severity="unknown", status="unknown",
                                     detail=f"Check failed to evaluate: {exc}"))

    # Order findings by severity (worst first) then category for display.
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4, "unknown": 5, "pass": 6}
    findings.sort(key=lambda f: (sev_order.get(f["severity"], 9), f["category"], f["title"]))

    score, grade, counts = _score(findings)
    return {
        "score": score,
        "grade": grade,
        "status": "completed",
        "error": None,
        "counts": counts,
        "findings": findings,
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
