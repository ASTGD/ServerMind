"""Fleet-health email digest — Ally proactively emails you what needs attention.

The capstone of the proactive-intelligence arc: fleet_service already scores the fleet
and ranks findings (deterministic, zero AI cost); this turns that into a friendly email
so you hear from Ally even when you're not in the app. Reuses the notification email
plumbing. A weekly (or daily) worker sends it; users can change the cadence or opt out.

``build_digest`` is PURE (analyzed fleet → {subject, text, html}) so it's fully
unit-testable; ``send_for_user`` does the DB read + email; ``is_due`` is the cadence
gate the worker uses.
"""
from __future__ import annotations

import html as _html
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.user import User
from app.services import fleet_service, notification_service, team_service
from app.services.fleet_service import ServerHealth

logger = logging.getLogger(__name__)

_SEV_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
_GRADE_COLOR = {"A": "#16a34a", "B": "#16a34a", "C": "#d97706", "D": "#dc2626", "F": "#dc2626"}


def app_url() -> str:
    """The public frontend origin for links back into the app (best-effort)."""
    return (settings.APP_BASE_URL or (settings.ALLOWED_ORIGINS[0] if settings.ALLOWED_ORIGINS else "")).rstrip("/")


def is_due(frequency: str, weekday: int) -> bool:
    """Whether a user with this cadence should get a digest on this UTC weekday
    (Mon=0 … Sun=6). 'daily' → every day, 'weekly' → Mondays, 'off' → never."""
    if frequency == "daily":
        return True
    if frequency == "weekly":
        return weekday == 0
    return False


def _headline(needs: int, have_findings: int, total: int) -> str:
    """A one-line summary. Three tiers: something urgent, some suggestions, or all clear
    — so we never say "healthy" while the body lists servers with findings."""
    if total == 0:
        return "No servers yet"
    if needs:
        return f"{needs} server{'s' if needs != 1 else ''} need{'s' if needs == 1 else ''} attention"
    if have_findings:
        return f"{have_findings} server{'s have' if have_findings != 1 else ' has'} a few things to check"
    return "Your fleet looks healthy"


def build_digest(name: str | None, fleet: list[ServerHealth], url: str = "") -> dict | None:
    """Build the digest email from an analyzed fleet. Returns {subject, text, html},
    or None when there's nothing to send (no servers). Worst-first; a healthy fleet
    still gets a short reassuring note."""
    if not fleet:
        return None

    url = (url or app_url()).rstrip("/")
    with_findings = [h for h in fleet if h.findings]
    needs = sum(1 for h in fleet if fleet_service.to_dict(h)["needs_attention"])
    healthy = len(fleet) - len(with_findings)
    greeting = f"Hi {name.split()[0]}," if name else "Hi,"
    headline = _headline(needs, len(with_findings), len(fleet))
    subject = f"[ServerAlly] {headline}"

    # ── plain text ────────────────────────────────────────────────────────────
    lines = [greeting, "", f"Ally's weekly check of your {len(fleet)} server"
             f"{'s' if len(fleet) != 1 else ''}: {headline}.", ""]
    if with_findings:
        for h in with_findings:
            lines.append(f"• {h.name} — {h.grade} ({h.score}/100)")
            for f in sorted(h.findings, key=lambda x: _SEV_ORDER.get(x.severity, 9)):
                lines.append(f"    - {f.title}: {f.detail}")
        lines.append("")
    if healthy:
        lines.append(f"{healthy} other server{'s' if healthy != 1 else ''} "
                     f"look{'s' if healthy == 1 else ''} healthy.")
        lines.append("")
    if url:
        lines.append(f"See the full report and let Ally help: {url}/dashboard")
    lines += ["", "— Ally, your ServerAlly companion",
              "Change how often you get this (or turn it off) in Settings."]
    text = "\n".join(lines)

    # ── HTML ────────────────────────────────────────────────────────────────────
    def esc(s: str) -> str:
        return _html.escape(str(s))

    rows: list[str] = []
    for h in with_findings:
        color = _GRADE_COLOR.get(h.grade, "#6b7280")
        findings_html = "".join(
            f'<div style="margin:4px 0;font-size:14px;color:#374151;">'
            f'<strong>{esc(f.title)}</strong> '
            f'<span style="color:#6b7280;">— {esc(f.detail)}</span></div>'
            for f in sorted(h.findings, key=lambda x: _SEV_ORDER.get(x.severity, 9))
        )
        rows.append(
            f'<div style="border:1px solid #e5e7eb;border-radius:12px;padding:14px 16px;margin:10px 0;">'
            f'<div style="margin-bottom:6px;">'
            f'<span style="display:inline-block;min-width:26px;text-align:center;background:{color};'
            f'color:#fff;font-weight:700;border-radius:6px;padding:2px 6px;font-size:13px;">{esc(h.grade)}</span> '
            f'<strong style="font-size:15px;color:#111827;">{esc(h.name)}</strong> '
            f'<span style="color:#6b7280;font-size:13px;">· {h.score}/100</span></div>'
            f'{findings_html}</div>'
        )
    healthy_note = (
        f'<p style="color:#059669;font-size:14px;margin:14px 0 0;">✓ {healthy} other '
        f'server{"s" if healthy != 1 else ""} look{"s" if healthy == 1 else ""} healthy.</p>'
        if healthy else ""
    )
    all_good = (
        '<p style="color:#059669;font-size:15px;">Everything looks healthy — nothing '
        'needs your attention right now. 🎉</p>' if not with_findings else ""
    )
    cta = (
        f'<a href="{esc(url)}/dashboard" style="display:inline-block;margin-top:18px;'
        f'background:#4f46e5;color:#fff;text-decoration:none;font-weight:600;'
        f'padding:10px 18px;border-radius:10px;font-size:14px;">Open the fleet report →</a>'
        if url else ""
    )
    html = f"""\
<div style="font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:560px;margin:0 auto;color:#111827;">
  <p style="font-size:15px;">{esc(greeting)}</p>
  <h2 style="font-size:18px;margin:6px 0 2px;">{esc(headline)}</h2>
  <p style="color:#6b7280;font-size:13px;margin:0 0 12px;">Ally checked your {len(fleet)} server{"s" if len(fleet) != 1 else ""}.</p>
  {all_good}
  {''.join(rows)}
  {healthy_note}
  {cta}
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:22px 0 10px;">
  <p style="color:#9ca3af;font-size:12px;">— Ally, your ServerAlly companion.<br>
  Change how often you get this (or turn it off) in Settings.</p>
</div>"""

    return {"subject": subject, "text": text, "html": html}


async def build_for_user(db: AsyncSession, user: User) -> dict | None:
    """Analyze the user's accessible fleet and build their digest (or None if empty)."""
    servers = await team_service.accessible_servers(db, user)
    fleet = await fleet_service.analyze_fleet(db, servers)
    return build_digest(user.name, fleet)


async def send_for_user(db: AsyncSession, user: User) -> bool:
    """Build + email one user's digest. Best-effort: returns True if an email was sent,
    False if there was nothing to send / no address (a send failure re-raises to the
    caller, which logs it — the worker never lets one user stop the sweep)."""
    if not user.email:
        return False
    digest = await build_for_user(db, user)
    if digest is None:
        return False
    await notification_service.send_email(
        user.email, digest["subject"], digest["text"], html=digest["html"]
    )
    return True
