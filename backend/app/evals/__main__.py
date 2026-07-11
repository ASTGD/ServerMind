"""Eval CLI (docs/EVAL-DRIVEN-DEV.md):

    python -m app.evals run [--category CATEGORY] [-v]

Runs the deterministic Ally evals offline (no API), prints a pass-rate table by
category, and exits non-zero if anything fails — so it can gate CI or be run by hand
while iterating on prompts/skills/blocklists.
"""
from __future__ import annotations

import argparse
import sys

from app.evals import DETERMINISTIC_CATEGORIES, run


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.evals", description="Ally deterministic evals (offline)"
    )
    sub = parser.add_subparsers(dest="cmd")
    runp = sub.add_parser("run", help="run the deterministic eval suite")
    runp.add_argument(
        "--category", choices=DETERMINISTIC_CATEGORIES, help="run only this category"
    )
    runp.add_argument("-v", "--verbose", action="store_true", help="print every case")
    args = parser.parse_args(argv)

    if args.cmd != "run":
        parser.print_help()
        return 2

    result = run(category=args.category)

    print()
    print(f"{'category':<18} {'pass':>5} {'total':>6}  rate")
    print("-" * 42)
    for cat, (p, t) in result.by_category().items():
        rate = f"{100 * p / t:.0f}%" if t else "—"
        print(f"{cat:<18} {p:>5} {t:>6}  {rate}")
    print("-" * 42)
    total_rate = f"{100 * result.passed / result.total:.0f}%" if result.total else "—"
    print(f"{'TOTAL':<18} {result.passed:>5} {result.total:>6}  {total_rate}")

    if args.verbose:
        print()
        for r in result.results:
            print(f"  [{'ok ' if r.passed else 'FAIL'}] {r.case.category} :: {r.case.input[:60]}")

    if result.failures:
        print(f"\n{len(result.failures)} FAILURE(S):")
        for r in result.failures:
            extra = f"  ({r.error})" if r.error else ""
            print(
                f"  ✗ [{r.case.category}] {r.case.input!r}\n"
                f"      got {r.got!r}, expected {r.case.expected!r}{extra}"
            )
        return 1

    print("\nAll deterministic evals passed.")
    return 0


if __name__ == "__main__":
    sys.exit(_main())
