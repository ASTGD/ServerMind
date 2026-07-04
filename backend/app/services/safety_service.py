"""Safety service — validates AI-generated commands against blocklists."""
from __future__ import annotations

import re
from dataclasses import dataclass

# ── Blocklists ────────────────────────────────────────────────────────────────

LINUX_BLOCKED = [
    r"rm\s+-[rf]+\s+/\s*$",
    r"rm\s+-[rf]+\s+/\*",
    r"mkfs\.",
    r"dd\s+if=/dev/(zero|random)\s+of=/dev/[a-z]+\b",
    r":\(\)\s*\{\s*:\|:&\s*\}",
    r"chmod\s+-R\s+[0-7]*7[0-7]*\s+/",
    r">\s*/dev/sd[a-z]",
    r"mv\s+/\s+",
    r"chown\s+-R\s+.+\s+/\s*$",
]

WINDOWS_BLOCKED = [
    r"Format-Volume",
    r"Remove-Item\s+C:\\Windows",
    r"Remove-Item\s+C:\\\*",
    r"rd\s+/s\s+/q\s+C:\\",
    r"del\s+/f\s+/s\s+/q\s+C:\\Windows",
    r"Stop-Computer",
    r"Disable-NetAdapter",
    r"Clear-Disk",
    r"Initialize-Disk",
]

CONFIRM_PATTERNS = [
    r"apt.*(remove|purge|autoremove)",
    r"(systemctl|service)\s+(stop|disable)",
    r"ufw\s+(disable|reset)",
    r"passwd\s+root",
    r"(wget|curl).+\|\s*(ba)?sh",
    r"Uninstall-WindowsFeature",
    r"Stop-Service",
    r"Disable-WindowsOptionalFeature",
    r"Remove-WindowsFeature",
    r"DROP\s+(TABLE|DATABASE)",
    r"crontab\s+-r",
    r"Restart-Computer",
]


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    status: str          # 'ok' | 'blocked' | 'confirm'
    reason: str | None = None
    pattern: str | None = None


def validate_command(cmd: str, os_family: str = "linux") -> ValidationResult:
    """Check a single command against blocklists."""
    blocked = WINDOWS_BLOCKED if os_family == "windows" else LINUX_BLOCKED

    for pattern in blocked:
        if re.search(pattern, cmd, re.IGNORECASE):
            return ValidationResult(
                status="blocked",
                pattern=pattern,
                reason=f"Command matches blocked pattern: {pattern}",
            )

    for pattern in CONFIRM_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return ValidationResult(
                status="confirm",
                pattern=pattern,
                reason="Command requires explicit confirmation before running",
            )

    return ValidationResult(status="ok")


# ── Read-only guard (mission verification) ────────────────────────────────────
# A mission's verification pass may only OBSERVE — it gathers fresh evidence that
# the goal was achieved, and must never change the server's state. This is a
# DEFAULT-DENY guard: any hint of mutation → not read-only. A wrongly-rejected
# check just means "couldn't confirm" (safe, honest); a wrongly-accepted mutation
# would let a "verification" step delete or reconfigure data — so we bias hard
# toward rejecting. Network reads (curl/wget to stdout or /dev/null) are allowed
# so an HTTP "is the site up?" check works; writing a file or piping to a shell is not.
# Case-INSENSITIVE mutating tokens (shell verbs, SQL, redirects, pipe-to-shell).
_MUTATION_TOKENS_I = [
    # Filesystem / ownership
    r"\brm\b", r"\brmdir\b", r"\bmv\b", r"\bcp\b", r"\bdd\b", r"\bmkfs\b",
    r"\bchmod\b", r"\bchown\b", r"\bchgrp\b", r"\bln\b", r"\btouch\b", r"\bmkdir\b",
    r"\btee\b", r"\btruncate\b", r"\bshred\b", r"\bsetfacl\b", r"\binstall\s+-\S",
    r"\bsed\b[^|;]*\s-i", r"\bperl\b[^|;]*\s-i",
    # Services / packages / power
    r"\b(systemctl|service)\s+\S*\s*(start|stop|restart|reload|enable|disable|mask|unmask)",
    r"\b(apt|apt-get|dnf|yum|apk|zypper|snap)\b[^|;]*\b(install|remove|purge|update|upgrade|autoremove)\b",
    r"\bpip\d?\s+install\b", r"\bnpm\s+(install|i|ci|update|run)\b", r"\byarn\s+(add|install)\b",
    r"\b(reboot|shutdown|halt|poweroff|init)\b", r"\bkill(all)?\b", r"\bpkill\b",
    # Accounts / firewall / mounts / cron writes — `passwd` must not match /etc/passwd.
    r"\b(useradd|usermod|userdel|groupadd|groupdel|adduser|deluser|chpasswd)\b",
    r"(?<![\w/])passwd(?![\w/])",
    r"\b(iptables|ip6tables|nft|ufw|firewall-cmd)\b",
    r"\bmount\b", r"\bumount\b", r"\bswapon\b", r"\bswapoff\b", r"\bsetcap\b",
    r"\bcrontab\b(?!\s+-l)",
    # Data stores (SQL writes, dumps that write a file)
    r"\b(DROP|DELETE|INSERT|UPDATE|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|REPLACE)\s",
    r"\bmysqldump\b", r"\bpg_dump\b", r"\bmysqladmin\b",
    # WordPress / git / docker state changes
    r"\bwp\s+[\w-]+\s+(install|activate|deactivate|update|delete|create|import|reset|add|regenerate|download|scaffold|flush|set)\b",
    r"\bgit\s+(clone|pull|fetch|checkout|reset|merge|push|apply|clean|rm|commit)\b",
    r"\bdocker(-compose)?\s+(run|rm|start|stop|restart|kill|exec|pull|build|up|down|create)\b",
    # Shell-level mutation: redirect into a real file, pipe to a shell, background exec
    r">\s*/(?!dev/null)", r">>", r"\|\s*(ba|z|c|k)?sh\b", r"\beval\b", r"\bnohup\b",
]
# Case-SENSITIVE tokens — curl -O vs -o and PowerShell PascalCase cmdlets carry
# meaning in their case, so matching case-insensitively would flag benign reads.
_MUTATION_TOKENS_CS = [
    r"\bwget\b(?![^|;]*O-(\s|$))",          # wget that SAVES a file (not `-O-` to stdout)
    r"\bcurl\b[^|;]*\s-O\b",                # curl -O (save as remote name)
    r"\bcurl\b[^|;]*-o\s+(?!/dev/null)\S",  # curl -o <file> (but /dev/null is fine)
    r"\b(Remove|Set|Stop|Start|Restart|New|Install|Uninstall|Clear|Format|Disable|Enable|Rename|Move|Copy|Add|Export|Out)-\w+",
    r"\bOut-File\b", r"\bSet-Content\b",
]
_MUTATION_RE = (
    [re.compile(p, re.IGNORECASE) for p in _MUTATION_TOKENS_I]
    + [re.compile(p) for p in _MUTATION_TOKENS_CS]
)


def is_read_only_command(cmd: str) -> bool:
    """True only if `cmd` merely OBSERVES — safe to run as a mission verification
    check. Default-deny: blank, blocklisted, or anything carrying a mutating token
    is rejected. Used by the mission engine so a verification pass can never change
    the server it's checking."""
    cmd = (cmd or "").strip()
    if not cmd:
        return False
    if validate_command(cmd, "linux").status == "blocked":
        return False
    if validate_command(cmd, "windows").status == "blocked":
        return False
    return not any(rx.search(cmd) for rx in _MUTATION_RE)


def validate_plan(commands: list[dict], os_family: str = "linux") -> ValidationResult:
    """Validate all commands in a plan. Blocked takes priority over confirm."""
    confirm_result: ValidationResult | None = None

    for item in commands:
        cmd = item.get("cmd", "")
        result = validate_command(cmd, os_family)
        if result.status == "blocked":
            return result
        if result.status == "confirm" and confirm_result is None:
            confirm_result = result

    return confirm_result or ValidationResult(status="ok")


def highest_risk(commands: list[dict]) -> str:
    """Return the highest risk_level across all commands in a plan."""
    levels = {"low": 0, "medium": 1, "high": 2}
    best = 0
    for item in commands:
        lvl = levels.get(item.get("risk_level", "low"), 0)
        if lvl > best:
            best = lvl
    return ["low", "medium", "high"][best]
