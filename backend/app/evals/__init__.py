"""Ally eval engine (docs/EVAL-DRIVEN-DEV.md).

The corpus is the golden dataset; ``deterministic_cases()`` turns it into ``Case``s; the
``runner`` checks each against the real services. One engine, three interfaces: pytest
(``tests/test_evals_engine.py``), the CLI (``python -m app.evals run``), and — Phase 3 —
the Dev Door UI.
"""
from __future__ import annotations

from app.evals import corpus
from app.evals.cases import deterministic_cases
from app.evals.model import (
    DETERMINISTIC_CATEGORIES,
    Case,
    Result,
    RunResult,
)
from app.evals.runner import run, run_case

__all__ = [
    "corpus",
    "deterministic_cases",
    "DETERMINISTIC_CATEGORIES",
    "Case",
    "Result",
    "RunResult",
    "run",
    "run_case",
]
