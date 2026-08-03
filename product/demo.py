"""Deterministic product-layer demonstration artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from product.arp_adapter import build_arp_manifest
from product.gate import decide_product_gate
from product.report import ProductGateReport


_CASES: tuple[tuple[str, dict[str, Any]], ...] = (
    (
        "approve",
        {
            "metrics": {"recall@5": 0.92},
            "thresholds": {"threshold_version": "demo-v1", "floors": {"recall@5": 0.80}},
        },
    ),
    (
        "warn",
        {
            "metrics": {"recall@5": 0.84},
            "thresholds": {
                "threshold_version": "demo-v1",
                "floors": {"recall@5": 0.80},
                "warnings": {"recall@5": 0.85},
            },
        },
    ),
    (
        "block",
        {
            "metrics": {"recall@5": 0.62},
            "thresholds": {"threshold_version": "demo-v1", "floors": {"recall@5": 0.80}},
        },
    ),
)


def write_demo(output_dir: Path | str) -> dict[str, Any]:
    """Write approve/warn/block reports in JSON and SARIF formats.

    The fixtures are deterministic and intentionally synthetic; they exercise
    the product contract without claiming to be thesis evidence or a live run.
    """

    destination = Path(output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    exit_codes: dict[str, int] = {}
    for case, config in _CASES:
        decision = decide_product_gate(config["metrics"], config["thresholds"], {})
        if decision.decision != case:
            raise ValueError(f"product demo case {case!r} produced {decision.decision!r}")
        manifest = build_arp_manifest(
            run_id=f"product-demo-{case}",
            started_at="2026-07-31T00:00:00+00:00",
            decision=decision,
            identifiers={"git_commit": "demo", "model": "synthetic"},
            hashes={"corpus": "demo-corpus", "config": "demo-config"},
            metadata={"demo_case": case},
            configuration={"thresholds": config["thresholds"]},
            artifacts={},
        )
        report = ProductGateReport.from_run(
            manifest,
            [],
            metrics=config["metrics"],
            rag={"demo": True, "demo_case": case},
        )
        (destination / f"{case}.json").write_text(report.to_json(), encoding="utf-8")
        (destination / f"{case}.sarif").write_text(
            json.dumps(report.to_sarif(), indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )
        exit_codes[case] = report.exit_code

    summary = {
        "schema_version": "rag-product-demo/v1",
        "synthetic": True,
        "decisions": exit_codes,
        "reports": [f"{case}.{format_name}" for case, _ in _CASES for format_name in ("json", "sarif")],
    }
    (destination / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )
    return summary
