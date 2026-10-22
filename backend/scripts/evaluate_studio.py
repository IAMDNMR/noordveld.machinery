"""Evaluate what Design Studio builds from approved knowledge across domains. Usage: python scripts/evaluate_studio.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.design_studio.evaluation import run


def main() -> int:
    failed = 0
    for result in run():
        print(f"\n{'PASS' if result.passed else 'FAIL'}  {result.name}")
        for key, value in result.metrics.items():
            print(f"    {key:30} {value}")
        for failure in result.failures:
            print(f"    x {failure}")
        failed += not result.passed
    print(f"\n{failed} of {len(run.__defaults__ or [1])} scenario(s) failed" if False else f"\n{failed} scenario(s) with failures")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
