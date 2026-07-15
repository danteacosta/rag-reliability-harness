from __future__ import annotations

import argparse
from pathlib import Path

from gates.run import (
    DEFAULT_BASELINE,
    DEFAULT_METRICS,
    DEFAULT_THRESHOLDS,
    run_gate,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="CI quality gate: compare eval metrics against thresholds and baseline.",
    )
    parser.add_argument("--metrics", type=Path, default=DEFAULT_METRICS)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)

    ok, failures = run_gate(
        metrics_path=args.metrics,
        thresholds_path=args.thresholds,
        baseline_path=args.baseline,
    )
    if ok:
        print("GATE PASS")
        return 0

    print("GATE FAIL")
    for reason in failures:
        print(f"  - {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
