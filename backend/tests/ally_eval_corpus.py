"""Compatibility shim — the Ally eval corpus now lives in ``app.evals.corpus`` so the
eval ENGINE and the Dev Door can import it as the single golden dataset. This module
re-exports it so the existing test files (``from tests import ally_eval_corpus as
corpus``) keep working unchanged. Add new cases in ``app/evals/corpus.py``.
"""
from __future__ import annotations

from app.evals.corpus import (  # noqa: F401
    CROSS_SERVER_FORBIDDEN_PHRASES,
    INJECTION_SENTINEL,
    INJECTIONS,
    READONLY_ALLOW,
    READONLY_DENY,
    SAFETY_MUST_ALLOW,
    SAFETY_MUST_BLOCK,
    SAFETY_MUST_CONFIRM,
    SCENARIOS,
    SKILL_ROUTING,
    InjectionAttack,
    Scenario,
)
