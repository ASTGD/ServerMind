"""A Windows playbook must produce output a person can read.

`win-audit` was written, syntax-checked, and never run. The first live run on a real
Windows Server 2022 box returned a "security audit" whose OS table appeared underneath the
*Local Users* heading and whose remaining sections were blank padded rows. It exited 0 and
was recorded as a success, which is the worst shape for a bug to have: nothing reports a
problem and the report is useless.

Two PowerShell behaviours cause it, and neither shows up locally:

1. **`Write-Host` and the pipeline are different streams.** `Write-Host` writes to the
   information stream; `Get-*` sends objects down the success pipeline. Remoting renders
   them separately and merges at the end, so a heading and its data arrive apart.
2. **One pipeline formats to the FIRST object's shape.** Send several different object
   types and everything after the first renders as blank rows.

`| Out-String` at the point each block is produced fixes both. These tests keep every
PowerShell playbook on that rule, because the same trap is one careless line away in any of
them — and only a live Windows box would ever reveal it again.
"""
import re

import pytest

from app.services.playbook_service import OFFICIAL_PLAYBOOKS

PS_PLAYBOOKS = [p for p in OFFICIAL_PLAYBOOKS if p.get("script_powershell")]

#: A line that sends objects down the pipeline for PowerShell to format on its own terms.
#: `Out-String`, an assignment, a `Section` call and a comment are all fine.
_EMITS_OBJECTS = re.compile(r"^\s*(?:Get-|\S+\s*\|\s*Select-Object)")


def code(script: str) -> str:
    """The script's executable lines.

    A comment EXPLAINING why not to use `Write-Host` contains the words `Write-Host`, so a
    check over the whole text fails on its own documentation. That has now caught this
    codebase five times in one day (`pgrep`, `sshd -t`, an import line, a Python comment,
    and this) — every one of them a search that matched prose instead of code.
    """
    return "\n".join(ln for ln in script.splitlines() if not ln.strip().startswith("#"))


def offending_lines(script: str) -> list[str]:
    out = []
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "Out-String" in stripped or stripped.startswith("Section "):
            continue
        # Captured into a variable, or consumed by something else — not emitted.
        if re.match(r"^\s*(?:\$\w+\s*=|if|foreach|while|function|\})", stripped):
            continue
        if _EMITS_OBJECTS.match(stripped):
            out.append(stripped)
    return out


def test_the_audit_report_is_readable():
    """The one that was broken. Every section must be produced as text, in order."""
    script = next(p for p in PS_PLAYBOOKS if p["slug"] == "win-audit")["script_powershell"]
    assert offending_lines(script) == []
    # Headings and data must travel in the SAME stream, so no Write-Host in a report.
    assert "Write-Host" not in code(script), (
        "Write-Host puts headings in a different stream from the data they label")


@pytest.mark.parametrize("pb", PS_PLAYBOOKS, ids=lambda p: p["slug"])
def test_no_playbook_emits_raw_objects(pb):
    bad = offending_lines(pb["script_powershell"])
    assert bad == [], (
        f"{pb['slug']} sends objects down the pipeline instead of text: {bad}. "
        f"Over WinRM these are formatted separately from any surrounding output and land "
        f"out of order, and mixed object types render as blank rows. "
        f"Wrap it: (… | Format-Table -AutoSize | Out-String).Trim()")


def test_the_audit_says_so_when_a_section_finds_nothing():
    """A blank gap reads as the audit having failed. An empty section has to say it is
    empty — the same 'absent is not the same as unknown' rule the scanners follow."""
    script = next(p for p in PS_PLAYBOOKS if p["slug"] == "win-audit")["script_powershell"]
    assert "nothing to report" in code(script)


def test_the_audit_survives_a_cmdlet_that_is_not_there():
    """Trimmed editions of Windows lack some of these cmdlets. One missing must cost one
    section, not the whole report."""
    script = next(p for p in PS_PLAYBOOKS if p["slug"] == "win-audit")["script_powershell"]
    for cmdlet in ("Get-LocalUser", "Get-LocalGroupMember", "Get-NetTCPConnection",
                   "Get-NetFirewallProfile"):
        line = next(ln for ln in code(script).splitlines() if cmdlet in ln)
        assert "-ErrorAction SilentlyContinue" in line, f"{cmdlet} can take the report down"


def test_every_powershell_playbook_declares_its_version():
    for pb in PS_PLAYBOOKS:
        assert pb["script_powershell"].lstrip().startswith("#Requires -Version"), pb["slug"]
