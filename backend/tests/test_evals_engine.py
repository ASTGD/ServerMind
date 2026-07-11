"""The eval ENGINE itself (app.evals) — proves it reproduces the corpus results and that
its runner/report behave, so the CLI (`python -m app.evals run`) and the Dev Door (Phase 3)
can trust it. Offline, no API. (The per-case assertions live in test_ally_evals.py, which
now runs through this same engine.)"""
from __future__ import annotations

from app.evals import DETERMINISTIC_CATEGORIES, Case, deterministic_cases, run, run_case
from app.evals.model import SKILL_ROUTING


def test_deterministic_suite_is_all_green():
    result = run()
    assert result.total == len(deterministic_cases())
    assert result.ok, "unexpected eval failures:\n" + "\n".join(
        f"  {r.case.category}: {r.case.input!r} → {r.got!r} (want {r.case.expected!r})"
        for r in result.failures
    )


def test_report_has_every_category_fully_passing():
    by_cat = run().by_category()
    for cat in DETERMINISTIC_CATEGORIES:
        assert cat in by_cat, f"category {cat} missing from the report"
        passed, total = by_cat[cat]
        assert total > 0 and passed == total, f"{cat}: {passed}/{total}"


def test_category_filter_runs_only_that_category():
    result = run(category=SKILL_ROUTING)
    assert result.total > 0
    assert all(r.case.category == SKILL_ROUTING for r in result.results)


def test_run_case_marks_a_wrong_expectation_as_failed_not_error():
    """A wrong expectation is a clean FAILURE (passed False, no error) — the property the
    Dev Door relies on to show red cases without the run crashing."""
    bad = Case(
        id="x", category=SKILL_ROUTING, input="install nginx",
        expected="wordpress-rescue", os="ubuntu",
    )
    r = run_case(bad)
    assert r.passed is False and r.error is None
    assert r.got == "None"  # "install nginx" matches no skill


def test_run_case_unknown_category_is_a_failure_not_a_crash():
    r = run_case(Case(id="x", category="bogus", input="x", expected="x"))
    assert r.passed is False and r.error is not None
