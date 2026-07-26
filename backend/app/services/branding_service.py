"""White-label branding — validate it, and serve only what is safe to publish.

Two jobs, both small but both security-relevant because this data is rendered on a
**public** page (a status page) for strangers:

1. **Validate on write.** ``primary_color`` is interpolated into client-facing styling and
   ``logo_url`` into an ``<img src>``. A colour that is not a hex literal, or a URL with a
   ``javascript:`` scheme, must never be stored — rejecting at the boundary is the only
   place it can be done once for every consumer.
2. **Publish an allowlist.** :func:`public_branding` returns the handful of fields a visitor
   may see. The owner's account email is never among them; ``support_email`` is separate and
   opt-in precisely so publishing a contact address is a deliberate act.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
# Only ever http(s). Blocks javascript:, data:, vbscript: and scheme-relative //evil.com.
_URL_RE = re.compile(r"^https?://[^\s<>\"']+$", re.IGNORECASE)


def valid_color(value: str | None) -> bool:
    """A CSS hex colour, or nothing. Deliberately strict: this string is interpolated into
    styling, so 'red; background:url(javascript:...)' must not pass."""
    return value is None or value == "" or bool(_HEX_RE.match(value))


def valid_url(value: str | None) -> bool:
    """An absolute http(s) URL, or nothing. A logo goes into <img src> and a support link
    into <a href>, so a javascript:/data: scheme must be impossible."""
    return value is None or value == "" or bool(_URL_RE.match(value))


def normalise_color(value: str | None) -> str | None:
    """Lowercase, and expand #abc → #aabbcc so consumers get one shape."""
    if not value:
        return None
    v = value.lower()
    if len(v) == 4:  # #abc
        return "#" + "".join(ch * 2 for ch in v[1:])
    return v


def public_branding(branding, *, app_name: str = "ServerAlly") -> dict:
    """The ONLY branding a stranger receives. An allowlist, not a model dump.

    ``show_credit`` is computed here rather than published as the raw flag, so a consumer
    cannot accidentally invert it.
    """
    if branding is None:
        return {
            "company_name": None, "logo_url": None, "primary_color": None,
            "support_url": None, "support_email": None, "footer_text": None,
            "show_credit": True, "app_name": app_name,
        }
    return {
        "company_name": (branding.company_name or "").strip() or None,
        "logo_url": branding.logo_url or None,
        "primary_color": normalise_color(branding.primary_color),
        "support_url": branding.support_url or None,
        "support_email": (branding.support_email or "").strip() or None,
        "footer_text": (branding.footer_text or "").strip() or None,
        "show_credit": not bool(branding.hide_serverally_branding),
        "app_name": app_name,
    }
