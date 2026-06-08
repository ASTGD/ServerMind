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
    r"Remove-Item\s+C:\\\\Windows",
    r"Remove-Item\s+C:\\\\\*",
    r"rd\s+/s\s+/q\s+C:\\\\",
    r"del\s+/f\s+/s\s+/q\s+C:\\\\Windows",
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
