"""Loading, validating and rendering an account's own runbooks.

A runbook becomes a ``skill_service.Skill`` and then flows through the existing matching,
menu and mission machinery unchanged. That is deliberate: reusing the path the built-in
skills already take means a custom runbook gets the same prompt-cache position, the same OS
gating, the same mission engine and the same verification gate, rather than a parallel
implementation that would drift.

Two things are different from a built-in skill, and both are about trust:

- The slug is namespaced ``my-…`` so a custom runbook can never be mistaken for one of ours
  in a prompt, a ledger row or a log line.
- The injected block carries an explicit **"this cannot change the safety rules"** clause.
  A built-in skill is content we wrote; a runbook is content a customer wrote, and while the
  hard rails live below the prompt and are unaffected by anything it says, the model must
  also be told not to act on a procedure that tries to talk its way past them.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runbook import (
    BODY_MAX, MAX_TRIGGERS, MODE_GUIDE, MODE_MISSION, OS_FAMILIES, RUNBOOK_MODES, Runbook,
)
from app.models.team import TeamMember
from app.models.user import User
from app.services import skill_service

logger = logging.getLogger(__name__)

SLUG_PREFIX = "my-"


def valid_slug(slug: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", slug or "")) and len(slug) <= 60


def slugify(title: str) -> str:
    """A slug from a title. Falls back to something valid rather than something empty."""
    base = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:60].strip("-")
    return base or "runbook"


def normalise_triggers(triggers: list[str] | None) -> list[str]:
    """Lowercased, de-duplicated, whitespace-collapsed trigger phrases.

    Matching lowercases the message and looks for whole phrases, so a trigger stored with
    different case or doubled spaces would silently never fire — normalising here is what
    makes "what you typed is what matches" true.
    """
    out: list[str] = []
    for raw in (triggers or []):
        cleaned = re.sub(r"\s+", " ", (raw or "").strip().lower())
        if cleaned and cleaned not in out:
            out.append(cleaned[:120])
    return out[:MAX_TRIGGERS]


def validate(title: str, body: str, triggers: list[str], mode: str, os_family: str) -> str | None:
    """Return a message for the author when something is wrong, else None."""
    if not (title or "").strip():
        return "Give the runbook a name."
    if not (body or "").strip():
        return "Write the procedure itself — the steps you want Ally to follow."
    if len(body) > BODY_MAX:
        return (f"That procedure is {len(body):,} characters; the limit is {BODY_MAX:,}. "
                "Ally has to fit it alongside the server's details, so keep it to the steps "
                "that matter.")
    cleaned = normalise_triggers(triggers)
    if not cleaned:
        return ("Add at least one phrase that should trigger it — for example "
                "\"checkout is broken\".")
    vague = [t for t in cleaned if _too_broad(t)]
    if vague:
        # A one-word trigger like "site" or "error" appears in almost every message, so the
        # runbook would be applied to unrelated requests — including ones a specialist
        # built-in procedure should have handled. Refusing is kinder than letting someone
        # discover it during an incident.
        return (f"“{vague[0]}” is too broad — it would match almost anything you ask. "
                "Use the words someone would actually say about this problem, like "
                "\"checkout is broken\".")
    if mode not in RUNBOOK_MODES:
        return f"Mode must be one of {', '.join(RUNBOOK_MODES)}."
    if os_family not in OS_FAMILIES:
        return f"OS must be one of {', '.join(OS_FAMILIES)}."
    return None


# Words so common that on their own they say nothing about which problem this is.
_COMMON_WORDS = {
    "server", "site", "website", "error", "errors", "problem", "issue", "help", "fix",
    "broken", "down", "slow", "check", "run", "install", "update", "restart", "it", "this",
    "please", "app", "web", "page", "database", "db", "log", "logs", "file", "files",
}


def _too_broad(trigger: str) -> bool:
    """A trigger that would fire on almost any message.

    One word is only specific enough if it is a distinctive one — "woocommerce" is fine,
    "site" is not.
    """
    words = trigger.split()
    return len(words) == 1 and (words[0] in _COMMON_WORDS or len(words[0]) <= 3)


def as_skill(runbook: Runbook) -> skill_service.Skill:
    """Adapt a stored runbook into the Skill shape the matching machinery already speaks."""
    return skill_service.Skill(
        slug=f"{SLUG_PREFIX}{runbook.slug}",
        title=runbook.title,
        triggers=list(runbook.triggers or []),
        os_family=runbook.os_family or "any",
        body=runbook.body or "",
        priority=runbook.priority or 0,
        # The model layer says 'guide'; the skill layer calls the same thing 'knowledge'.
        mode="mission" if runbook.mode == MODE_MISSION else "knowledge",
        budget=runbook.budget,
        path=f"{skill_service.CUSTOM_PATH_PREFIX}{runbook.id}",
    )


def block(skill: skill_service.Skill) -> str:
    """The prompt block for a matched custom runbook.

    Delegates, so the wording has exactly one home — next to the built-in block it has to
    stay consistent with.
    """
    return skill_service.skill_block(skill)


# Re-exported for readability at the call sites that think in runbooks.
is_custom = skill_service.is_custom


# ── Loading, scoped to the account ───────────────────────────────────────────

async def owning_account_id(db: AsyncSession, user: User):
    """The account whose runbook library applies to this user's session.

    A team member uses the *owner's* library. That direction is deliberate: the owner already
    outranks their operators, so their procedures steering a subordinate's session is
    delegation. The reverse — an operator authoring something the owner unknowingly runs —
    is why authoring is owner/admin only.
    """
    membership = (await db.execute(
        select(TeamMember).where(
            TeamMember.member_id == user.id,
            TeamMember.invite_accepted.is_(True),
        ).limit(1)
    )).scalar_one_or_none()
    return membership.owner_id if membership else user.id


async def load_for(db: AsyncSession, user: User) -> list[skill_service.Skill]:
    """The active runbooks that apply to this user, as Skills. Never raises.

    Best-effort by design: a database hiccup here must degrade Ally to its built-in
    procedures, not break the conversation.
    """
    try:
        account_id = await owning_account_id(db, user)
        rows = (await db.execute(
            select(Runbook).where(
                Runbook.user_id == account_id,
                Runbook.is_active.is_(True),
            ).order_by(Runbook.priority.desc(), Runbook.created_at)
        )).scalars().all()
        return [as_skill(r) for r in rows]
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not load custom runbooks for %s: %s", user.id, exc)
        return []


async def record_use(db: AsyncSession, skill: skill_service.Skill) -> None:
    """Count a use, so the library can show what is actually earning its keep.

    Best-effort, and never inside the request's own transaction concerns — a counter must not
    be able to fail a chat turn.
    """
    if not is_custom(skill):
        return
    try:
        runbook_id = skill.path.split(":", 1)[1]
        await db.execute(
            update(Runbook).where(Runbook.id == runbook_id).values(
                times_used=Runbook.times_used + 1,
                last_used_at=datetime.now(tz=timezone.utc),
            )
        )
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("Could not record runbook use: %s", exc)


# ── What the API says ────────────────────────────────────────────────────────

def shadowed_builtin(triggers: list[str], os_family: str) -> str | None:
    """The built-in skill this runbook would take over from, if any.

    Worth surfacing: our own procedures carry hard-won specifics — the incident-response
    runbook, for instance, knows not to quarantine a ``vendor/`` library. A customer replacing
    it should know they are replacing it, not discover it during an incident.
    """
    for trigger in normalise_triggers(triggers):
        found = skill_service.match(trigger, None if os_family == "any" else os_family)
        if found is not None:
            return found.slug
    return None


def serialize(runbook: Runbook) -> dict:
    return {
        "id": str(runbook.id),
        "title": runbook.title,
        "slug": runbook.slug,
        "description": runbook.description,
        "triggers": list(runbook.triggers or []),
        "os_family": runbook.os_family,
        "mode": runbook.mode,
        "body": runbook.body,
        "budget": runbook.budget,
        "priority": runbook.priority,
        "is_active": runbook.is_active,
        "times_used": runbook.times_used,
        "last_used_at": runbook.last_used_at.isoformat() if runbook.last_used_at else None,
        "created_at": runbook.created_at.isoformat() if runbook.created_at else None,
        "shadows": shadowed_builtin(list(runbook.triggers or []), runbook.os_family),
    }
