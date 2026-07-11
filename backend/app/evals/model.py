"""Eval engine data model (docs/EVAL-DRIVEN-DEV.md).

A ``Case`` is pure data (input + expected outcome + category) — the runner knows how to
CHECK each category against the real services, so cases stay serializable for the Dev
Door's eval runner (Phase 3) and identical whether run from pytest, the CLI, or the UI.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The deterministic categories (offline, no API). Kept as constants so the runner,
# the CLI, and the tests agree on the names.
SKILL_ROUTING = "skill-routing"
SAFETY_BLOCK = "safety-block"
SAFETY_CONFIRM = "safety-confirm"
SAFETY_ALLOW = "safety-allow"
READONLY_ALLOW = "readonly-allow"
READONLY_DENY = "readonly-deny"

DETERMINISTIC_CATEGORIES = (
    SKILL_ROUTING,
    SAFETY_BLOCK,
    SAFETY_CONFIRM,
    SAFETY_ALLOW,
    READONLY_ALLOW,
    READONLY_DENY,
)


@dataclass(frozen=True)
class Case:
    """One eval case — pure data. ``input`` is the message/command; ``expected`` is the
    outcome the runner will compare against (a skill slug, a safety status, or a
    read-only verdict). ``os`` is the os_type (routing) / os_family (safety) context."""

    id: str
    category: str
    input: str
    expected: str
    os: str = "linux"
    provenance: str = ""


@dataclass
class Result:
    """The outcome of running one case."""

    case: Case
    passed: bool
    got: str
    error: str | None = None


@dataclass
class RunResult:
    """The outcome of a whole run — with per-category pass-rate helpers."""

    results: list[Result] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failures(self) -> list[Result]:
        return [r for r in self.results if not r.passed]

    @property
    def ok(self) -> bool:
        return not self.failures

    def by_category(self) -> dict[str, tuple[int, int]]:
        """category → (passed, total), in first-seen order."""
        agg: dict[str, tuple[int, int]] = {}
        for r in self.results:
            p, t = agg.get(r.case.category, (0, 0))
            agg[r.case.category] = (p + (1 if r.passed else 0), t + 1)
        return agg
