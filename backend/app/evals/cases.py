"""Build ``Case`` objects from the golden corpus (docs/EVAL-DRIVEN-DEV.md).

The corpus is DATA; this turns it into the engine's ``Case`` list. Grows automatically
as the corpus grows — a new corpus row becomes a new eval case with no code change.
"""
from __future__ import annotations

from app.evals import corpus
from app.evals.model import (
    READONLY_ALLOW,
    READONLY_DENY,
    SAFETY_ALLOW,
    SAFETY_BLOCK,
    SAFETY_CONFIRM,
    SKILL_ROUTING,
    Case,
)


def deterministic_cases() -> list[Case]:
    """Every offline eval case: skill routing, the three safety buckets, and the two
    read-only-guard buckets — the exact tables the CI evals have always checked."""
    cases: list[Case] = []

    for i, (message, os_type, expected) in enumerate(corpus.SKILL_ROUTING):
        cases.append(Case(
            id=f"skill-{i:02d}",
            category=SKILL_ROUTING,
            input=message,
            expected=expected or "None",
            os=os_type,
            provenance="corpus.SKILL_ROUTING",
        ))

    for category, table, expected in (
        (SAFETY_BLOCK, corpus.SAFETY_MUST_BLOCK, "blocked"),
        (SAFETY_CONFIRM, corpus.SAFETY_MUST_CONFIRM, "confirm"),
        (SAFETY_ALLOW, corpus.SAFETY_MUST_ALLOW, "ok"),
    ):
        for i, (cmd, os_family) in enumerate(table):
            cases.append(Case(
                id=f"{category}-{i:02d}",
                category=category,
                input=cmd,
                expected=expected,
                os=os_family,
                provenance=f"corpus.{category.replace('-', '_').upper()}",
            ))

    for i, cmd in enumerate(corpus.READONLY_ALLOW):
        cases.append(Case(
            id=f"ro-allow-{i:02d}",
            category=READONLY_ALLOW,
            input=cmd,
            expected="read-only",
            provenance="corpus.READONLY_ALLOW",
        ))
    for i, cmd in enumerate(corpus.READONLY_DENY):
        cases.append(Case(
            id=f"ro-deny-{i:02d}",
            category=READONLY_DENY,
            input=cmd,
            expected="mutating",
            provenance="corpus.READONLY_DENY",
        ))

    return cases
