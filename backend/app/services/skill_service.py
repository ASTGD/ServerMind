"""Ally Skills (Phase A) — packaged expert procedures for specific jobs.

A skill is a markdown file in ``app/skills/`` with a small frontmatter header
(slug, title, triggers, os) and an expert body: diagnostic order, procedure,
pitfalls, verification, rollback. When a chat message matches a skill's triggers,
the body is injected into the planning prompt so Ally follows the specialist's
procedure instead of improvising.

Design points:
- **Deterministic matching, zero cost** — trigger phrases are matched in code
  against the user's message; no extra AI call, no latency.
- **One skill per message** — the best match only; prompts stay lean (we meter tokens).
- **Trusted content** — skills are OUR authored files (repo-reviewed, shipped with the
  app). Unlike page context/memories, this is the one block Ally is meant to follow.
  The safety layer still validates every command regardless.
- Files are loaded once and cached; a malformed file is skipped with a warning,
  never a crash.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_SKILLS_DIR = Path(__file__).resolve().parent.parent / "skills"
_BODY_MAX = 5000  # hard cap on injected skill text

# Mission step budgets. Ad-hoc missions use the default; a mission-mode skill may
# declare its own `budget:` (a deep investigation or multi-stage install needs more
# than a quick fix) — always clamped to a safe range so no skill can remove the bound.
MISSION_BUDGET_DEFAULT = 20
MISSION_BUDGET_MIN = 10
MISSION_BUDGET_MAX = 40


def _parse_budget(raw: str | None) -> int | None:
    """Parse + clamp a skill's declared mission budget; None if unset/invalid."""
    if not raw:
        return None
    try:
        return max(MISSION_BUDGET_MIN, min(MISSION_BUDGET_MAX, int(raw)))
    except (TypeError, ValueError):
        return None

_SKILL_BLOCK = """\

EXPERT PROCEDURE — "{title}" (ServerAlly's specialist playbook for this kind of task):
{body}

Follow this procedure: diagnose in the given order, prefer read-only checks first,
respect the listed pitfalls, and always end with the verification step. If the user's
request turns out NOT to match this procedure, ignore it and handle the request
normally. All normal safety rules still apply.
"""


@dataclass
class Skill:
    slug: str
    title: str
    triggers: list[str]
    os_family: str  # 'linux' | 'windows' | 'any'
    body: str
    priority: int = 0
    # 'knowledge' = injected into normal chat planning as an expert procedure.
    # 'mission'   = a runbook for the mission engine (chat only OFFERS a mission;
    #               the body is injected into each mission step-planning call).
    mode: str = "knowledge"
    # Mission-mode only: the step budget this runbook needs (clamped), or None → default.
    budget: int | None = None
    path: str = field(default="", repr=False)


def resolve_mission_budget(skill: "Skill | None") -> int:
    """The step budget for a mission: the skill's declared budget, else the default."""
    if skill is not None and skill.budget:
        return skill.budget
    return MISSION_BUDGET_DEFAULT


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse a minimal ``--- key: value ---`` frontmatter header. No YAML dependency —
    values are plain strings; ``triggers`` is comma-separated."""
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict = {}
    for line in parts[1].strip().splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        meta[key.strip().lower()] = value.strip()
    return meta, parts[2].strip()


_cache: list[Skill] | None = None


def load_skills() -> list[Skill]:
    """Load and cache all skills from app/skills/*.md (sorted by priority desc)."""
    global _cache
    if _cache is not None:
        return _cache
    skills: list[Skill] = []
    if _SKILLS_DIR.is_dir():
        for path in sorted(_SKILLS_DIR.glob("*.md")):
            try:
                meta, body = _parse_frontmatter(path.read_text(encoding="utf-8"))
                slug = meta.get("slug") or path.stem
                triggers = [t.strip().lower() for t in meta.get("triggers", "").split(",") if t.strip()]
                if not body or not triggers:
                    logger.warning("skill %s skipped — missing triggers or body", path.name)
                    continue
                skills.append(
                    Skill(
                        slug=slug,
                        title=meta.get("title", slug),
                        triggers=triggers,
                        os_family=(meta.get("os") or "any").lower(),
                        body=body[:_BODY_MAX],
                        priority=int(meta.get("priority", "0") or 0),
                        mode=(meta.get("mode") or "knowledge").lower(),
                        budget=_parse_budget(meta.get("budget")),
                        path=str(path),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — one bad file must not kill chat
                logger.warning("skill %s failed to load: %s", path.name, exc)
    skills.sort(key=lambda s: s.priority, reverse=True)
    _cache = skills
    logger.info("loaded %d Ally skills", len(skills))
    return skills


def reset_cache() -> None:
    global _cache
    _cache = None


_WINDOWS_OS = ("windows",)


def _os_ok(skill: Skill, os_type: str | None) -> bool:
    if skill.os_family == "any":
        return True
    is_windows = (os_type or "").lower() in _WINDOWS_OS
    return (skill.os_family == "windows") == is_windows


def match(user_input: str, os_type: str | None = None) -> Skill | None:
    """The best-matching skill for a message, or None.

    Deterministic: counts whole trigger phrases present in the lowercased message;
    highest hit count wins (priority breaks ties). Requires at least one hit — most
    messages match nothing and get no injection.
    """
    text = " " + re.sub(r"\s+", " ", (user_input or "").lower()) + " "
    best: Skill | None = None
    best_score = 0
    for skill in load_skills():
        if not _os_ok(skill, os_type):
            continue
        score = sum(1 for t in skill.triggers if t in text)
        if score > best_score:
            best, best_score = skill, score
    return best


def skill_block(skill: Skill | None) -> str:
    """Render the prompt block for a matched knowledge skill ('' when none or when the
    skill is a mission runbook — those inject via the mission engine instead)."""
    if skill is None or skill.mode == "mission":
        return ""
    return _SKILL_BLOCK.format(title=skill.title, body=skill.body)


def get(slug: str) -> Skill | None:
    """Look a skill up by slug (for mission starts)."""
    for skill in load_skills():
        if skill.slug == slug:
            return skill
    return None


def get_for_os(slug: str, os_type: str | None) -> Skill | None:
    """Look a skill up by slug, honoring the OS gate (for model-requested skills)."""
    skill = get(slug)
    return skill if (skill and _os_ok(skill, os_type)) else None


def menu_for(os_type: str | None) -> str:
    """A one-line-per-skill menu for the prompt (Skills Phase B) — the model itself
    picks a skill when keyword matching missed (any language, any phrasing).
    Only OS-compatible skills are listed. ~100 tokens for the whole library."""
    lines = [
        f"- {s.slug} — {s.title}" + (" [multi-step mission]" if s.mode == "mission" else "")
        for s in load_skills()
        if _os_ok(s, os_type)
    ]
    return "\n".join(lines)
