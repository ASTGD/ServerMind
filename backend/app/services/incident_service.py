"""Incidents — raising something that needs a human, and closing it.

A detector (uptime, threats, metric thresholds, expiring certificates) calls ``raise_for``.
If an escalation policy applies, an incident is opened and the worker starts climbing the
ladder. If no policy applies — no policy configured, or the severity is below what the user
asked to be paged about — ``raise_for`` returns ``None`` and the caller sends its ordinary
one-shot email exactly as before. **Nothing gets quieter than it is today.**

Three rules, each of which exists because breaking it would make every alert untrustworthy:

- **One open incident per problem.** Enforced by a partial unique index, so even two
  workers racing cannot double-page. A detector that fires every minute while a site is
  down produces one incident.
- **Acknowledging or resolving stops paging at once.** Both clear ``next_action_at`` *and*
  move the status out of ``open``; the worker's query requires both, so there is no tick
  window in which an acknowledged incident can page again.
- **The acknowledge token is never stored in plaintext.** Someone who can silence your
  alerts can hide a break-in, so a database read alone must not be enough to acknowledge on
  your behalf: we keep a SHA-256 for lookup and an AES-256-GCM copy so later rungs of the
  ladder can carry the link too.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import (
    STATUS_ACKNOWLEDGED, STATUS_OPEN, STATUS_RESOLVED,
    EscalationPolicy, EscalationStep, Incident,
)
from app.models.server import Server
from app.services import crypto_service, escalation_service as esc, webhook_service

logger = logging.getLogger(__name__)


# ── The acknowledge token ────────────────────────────────────────────────────

def mint_ack_token() -> tuple[str, str]:
    """Return ``(token, sha256_hex)``. Only the hash is ever stored."""
    token = secrets.token_urlsafe(32)
    return token, hash_ack_token(token)


def hash_ack_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def read_ack_token(incident: Incident) -> str | None:
    """The plaintext token, for putting the acknowledge link in a message.

    Best-effort: if the ciphertext can't be read (a rotated key, say), the page still goes
    out without a link rather than not going out at all — a page with no shortcut beats
    silence, and the incident can still be acknowledged in the app.
    """
    if not incident.ack_token_enc:
        return None
    try:
        return crypto_service.decrypt(incident.ack_token_enc)
    except Exception:  # noqa: BLE001
        logger.warning("Could not read the ack token for incident %s", incident.id)
        return None


# ── Which policy applies ─────────────────────────────────────────────────────

async def policy_for(db: AsyncSession, user_id: uuid.UUID, server: Server | None) -> EscalationPolicy | None:
    """The server's own policy, else the user's default. None means "don't escalate".

    An inactive policy is treated as absent rather than falling through to the default —
    switching a policy off must mean "stop paging", not "page via something else".
    """
    if server is not None and server.escalation_policy_id:
        policy = await db.get(EscalationPolicy, server.escalation_policy_id)
        if policy and policy.is_active:
            return policy
        return None

    return (await db.execute(
        select(EscalationPolicy).where(
            EscalationPolicy.user_id == user_id,
            EscalationPolicy.is_default.is_(True),
            EscalationPolicy.is_active.is_(True),
        ).limit(1)
    )).scalar_one_or_none()


async def steps_for(db: AsyncSession, policy: EscalationPolicy) -> list[esc.Step]:
    rows = (await db.execute(
        select(EscalationStep).where(EscalationStep.policy_id == policy.id)
        .order_by(EscalationStep.position)
    )).scalars().all()
    return [
        esc.Step(after_minutes=r.after_minutes, channel=r.channel, target=r.target, label=r.label)
        for r in rows
    ]


# ── Raising ──────────────────────────────────────────────────────────────────

async def raise_for(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    server: Server | None,
    source: str,
    dedup_key: str,
    title: str,
    message: str = "",
    severity: str = "high",
) -> tuple[Incident, str] | None:
    """Open an incident and start escalation. Returns ``(incident, ack_token)``.

    Returns ``None`` when escalation does not apply, which tells the caller to fall back to
    its ordinary one-shot notification. Also returns ``None`` when this problem already has
    an open incident — the detector is simply still seeing the same thing.
    """
    policy = await policy_for(db, user_id, server)
    if policy is None:
        return None
    if not esc.severity_allows(policy.min_severity, severity):
        logger.debug("Incident %s below %s — not escalating", dedup_key, policy.min_severity)
        return None

    steps = await steps_for(db, policy)
    if not steps:
        # A policy with no rungs would open incidents nobody is ever told about — worse
        # than not escalating, because it also suppresses nothing and helps nobody.
        logger.info("Policy %s has no steps — not escalating %s", policy.id, dedup_key)
        return None

    existing = await open_incident(db, user_id, dedup_key)
    if existing is not None:
        return None

    token, token_hash = mint_ack_token()
    now = esc.utcnow()
    incident = Incident(
        user_id=user_id,
        server_id=server.id if server is not None else None,
        source=source, dedup_key=dedup_key,
        title=title[:255], message=message or "", severity=severity,
        status=STATUS_OPEN, policy_id=policy.id,
        ack_token_hash=token_hash, ack_token_enc=crypto_service.encrypt(token),
        next_action_at=esc.first_action_at(steps, now),
        created_at=now,
    )
    db.add(incident)
    try:
        await db.commit()
    except IntegrityError:
        # Another worker opened the same incident between our check and our insert. The
        # partial unique index caught it; that is the index doing its job, not an error.
        await db.rollback()
        logger.info("Incident %s already open (raced) — not double-paging", dedup_key)
        return None
    await db.refresh(incident)
    logger.info("Incident opened: %s (%s, %s)", incident.title, source, severity)
    await webhook_service.emit(db, user_id, "incident.opened", _event(incident))
    return incident, token


async def open_incident(db: AsyncSession, user_id: uuid.UUID, dedup_key: str) -> Incident | None:
    return (await db.execute(
        select(Incident).where(
            Incident.user_id == user_id,
            Incident.dedup_key == dedup_key,
            Incident.status == STATUS_OPEN,
        ).limit(1)
    )).scalar_one_or_none()


# ── Closing ──────────────────────────────────────────────────────────────────

def _stop_escalating(incident: Incident) -> None:
    """Clear the schedule. The worker requires BOTH an open status and a due
    ``next_action_at``, so clearing either is enough — we clear both deliberately, because
    "it stopped paging" is the promise this feature is built on."""
    incident.next_action_at = None


async def acknowledge(db: AsyncSession, incident: Incident, by: str) -> Incident:
    """"I've seen it, stop paging me." Does not resolve — the problem is still there."""
    if incident.status == STATUS_OPEN:
        incident.status = STATUS_ACKNOWLEDGED
        incident.acknowledged_at = esc.utcnow()
        incident.acknowledged_by = by[:255]
        _stop_escalating(incident)
        await db.commit()
        await db.refresh(incident)
        logger.info("Incident %s acknowledged by %s", incident.id, by)
        await webhook_service.emit(db, incident.user_id, "incident.acknowledged", _event(incident))
    return incident


async def acknowledge_by_token(db: AsyncSession, token: str) -> Incident | None:
    """Acknowledge from the link in a message. Returns None if the token matches nothing.

    Deliberately the only thing a token can do: it is not a login, carries no session, and
    reaches exactly one incident.
    """
    if not token or len(token) > 128:
        return None
    incident = (await db.execute(
        select(Incident).where(Incident.ack_token_hash == hash_ack_token(token)).limit(1)
    )).scalar_one_or_none()
    if incident is None:
        return None
    if incident.status == STATUS_OPEN:
        await acknowledge(db, incident, by="the link we sent")
    return incident


async def resolve(db: AsyncSession, incident: Incident, *, auto: bool, by: str = "") -> Incident:
    """The problem is over. Stops escalation whether or not anyone acknowledged."""
    if incident.status != STATUS_RESOLVED:
        incident.status = STATUS_RESOLVED
        incident.resolved_at = esc.utcnow()
        incident.auto_resolved = auto
        if by and not incident.acknowledged_by:
            incident.acknowledged_by = by[:255]
        _stop_escalating(incident)
        await db.commit()
        await db.refresh(incident)
        logger.info("Incident %s resolved (%s)", incident.id, "automatically" if auto else by)
        await webhook_service.emit(db, incident.user_id, "incident.resolved", _event(incident))
    return incident


async def resolve_key(db: AsyncSession, user_id: uuid.UUID, dedup_key: str) -> Incident | None:
    """Auto-resolve by problem identity — what a detector calls when the thing it was
    complaining about has cleared. Safe to call when nothing is open."""
    incident = await open_incident(db, user_id, dedup_key)
    if incident is None:
        # Also close one that was acknowledged but never resolved, so the list reflects
        # reality rather than accumulating problems that fixed themselves.
        incident = (await db.execute(
            select(Incident).where(
                Incident.user_id == user_id, Incident.dedup_key == dedup_key,
                Incident.status == STATUS_ACKNOWLEDGED,
            ).limit(1)
        )).scalar_one_or_none()
    if incident is None:
        return None
    return await resolve(db, incident, auto=True)


# ── Reading ──────────────────────────────────────────────────────────────────

def _event(incident: Incident) -> dict:
    """The webhook body for an incident.

    Deliberately narrower than ``serialize``: a webhook goes to a third-party endpoint, so it
    carries what is needed to react (what, where, how bad) and nothing more.
    """
    return {
        "incident_id": str(incident.id),
        "title": incident.title,
        "severity": incident.severity,
        "status": incident.status,
        "source": incident.source,
        "server_id": str(incident.server_id) if incident.server_id else None,
        "acknowledged_by": incident.acknowledged_by,
        "auto_resolved": incident.auto_resolved,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
    }


def serialize(incident: Incident, *, server_name: str | None = None) -> dict:
    """An incident for the API.

    An explicit allowlist, and the reason is ``ack_token_hash``: dumping the model would
    publish it, and while a hash is not the token, a field that gates silencing alerts has
    no business in a response body.
    """
    return {
        "id": str(incident.id),
        "server_id": str(incident.server_id) if incident.server_id else None,
        "server_name": server_name,
        "source": incident.source,
        "title": incident.title,
        "message": incident.message,
        "severity": incident.severity,
        "status": incident.status,
        "notifications_sent": incident.notifications_sent,
        "acknowledged_at": incident.acknowledged_at.isoformat() if incident.acknowledged_at else None,
        "acknowledged_by": incident.acknowledged_by,
        "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
        "auto_resolved": incident.auto_resolved,
        "next_action_at": incident.next_action_at.isoformat() if incident.next_action_at else None,
        "created_at": incident.created_at.isoformat() if incident.created_at else None,
    }


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)
