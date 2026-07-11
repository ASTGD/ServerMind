"""The eval engine (docs/EVAL-DRIVEN-DEV.md) — ONE place that knows how to CHECK a case
against the real services, shared by pytest, the CLI, and (Phase 3) the Dev Door UI.

Deterministic + offline: every check is a pure call into ``skill_service`` /
``safety_service`` — no API, no network, no DB.
"""
from __future__ import annotations

from app.evals.cases import deterministic_cases
from app.evals.model import (
    READONLY_ALLOW,
    READONLY_DENY,
    SAFETY_ALLOW,
    SAFETY_BLOCK,
    SAFETY_CONFIRM,
    SKILL_ROUTING,
    Case,
    Result,
    RunResult,
)
from app.services import safety_service, skill_service

_SAFETY = {SAFETY_BLOCK, SAFETY_CONFIRM, SAFETY_ALLOW}
_READONLY = {READONLY_ALLOW, READONLY_DENY}


def _check(case: Case) -> tuple[bool, str]:
    """Run the real service for this case's category and return (passed, got)."""
    if case.category == SKILL_ROUTING:
        match = skill_service.match(case.input, case.os)
        got = match.slug if match else "None"
        return got == case.expected, got
    if case.category in _SAFETY:
        got = safety_service.validate_command(case.input, case.os).status
        return got == case.expected, got
    if case.category in _READONLY:
        got = "read-only" if safety_service.is_read_only_command(case.input) else "mutating"
        return got == case.expected, got
    raise ValueError(f"unknown eval category: {case.category!r}")


def run_case(case: Case) -> Result:
    """Run one case. A raised exception is a FAILURE (never crashes the run)."""
    try:
        passed, got = _check(case)
        return Result(case=case, passed=passed, got=got)
    except Exception as exc:  # noqa: BLE001 — an error in a case is a failed case
        return Result(case=case, passed=False, got="error", error=f"{type(exc).__name__}: {exc}")


def run(cases: list[Case] | None = None, category: str | None = None) -> RunResult:
    """Run the deterministic suite (or a subset). Loads skills fresh so a warm cache from
    elsewhere can't skew routing."""
    if cases is None:
        cases = deterministic_cases()
    if category:
        cases = [c for c in cases if c.category == category]
    skill_service.reset_cache()
    return RunResult([run_case(c) for c in cases])
