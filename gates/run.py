from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from rag_harness.reliability import GateDecision, GateReason
from rag_harness.reliability import BaselineLifecycle

DEFAULT_THRESHOLDS = Path("eval/thresholds.yaml")
DEFAULT_BASELINE = Path("eval/baselines/ci.json")
DEFAULT_METRICS = Path("eval/last_run.json")

METRIC_KEYS = (
    "recall@5",
    "precision@5",
    "mrr",
    "groundedness",
    "refusal_accuracy",
    "drift_ok",
)


def load_thresholds(path: Path | str = DEFAULT_THRESHOLDS) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"thresholds file must be a mapping: {path}")
    return data


def load_baseline(path: Path | str = DEFAULT_BASELINE) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"baseline file must be a JSON object: {path}")
    return data


def load_baseline_lifecycle(path: Path | str) -> BaselineLifecycle:
    """Load the version-selection policy carried with a baseline artifact."""
    data = load_baseline(path)
    lifecycle = data.get("_lifecycle")
    if not isinstance(lifecycle, dict):
        raise ValueError("baseline lifecycle metadata is required")
    return BaselineLifecycle.from_dict(lifecycle)


def load_metrics(path: Path | str = DEFAULT_METRICS) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"metrics file must be a JSON object: {path}")
    return data


def check_gate(
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
    baseline: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Compatibility wrapper returning ``(passed, human-readable failures)``."""
    decision = decide_gate(metrics, thresholds, baseline)
    return decision.outcome == "pass", [reason.message for reason in decision.reasons]


def decide_gate(
    metrics: dict[str, Any],
    thresholds: dict[str, Any],
    baseline: dict[str, Any],
) -> GateDecision:
    """Evaluate a gate using stable reason codes and structured evidence."""
    failures: list[GateReason] = []

    if thresholds.get("require_drift_ok", False) and metrics.get("drift_ok") is not True:
        failures.append(
            GateReason("drift.required", "ingest", "drift_ok", metrics.get("drift_ok"), True, "ingest", "drift_ok required but metrics['drift_ok'] is not True")
        )

    floors = thresholds.get("floors") or {}
    for key, floor in floors.items():
        value = metrics.get(key)
        if value is None:
            failures.append(
                GateReason("metric.missing", _surface_for_metric(key), key, None, float(floor), _owner_for_metric(key), f"floor {key}: missing metric")
            )
            continue
        if float(value) < float(floor):
            failures.append(
                GateReason("floor_not_met", _surface_for_metric(key), key, float(value), float(floor), _owner_for_metric(key), f"floor {key}: {float(value):.4f} < {float(floor):.4f}")
            )

    max_slip = thresholds.get("max_slip") or {}
    for key, slip_limit in max_slip.items():
        current = metrics.get(key)
        base = baseline.get(key)
        if current is None:
            failures.append(
                GateReason("metric.missing", _surface_for_metric(key), key, None, float(slip_limit), _owner_for_metric(key), f"slip {key}: missing current metric")
            )
            continue
        if base is None:
            failures.append(
                GateReason("baseline.metric_missing", _surface_for_metric(key), key, None, float(slip_limit), _owner_for_metric(key), f"slip {key}: missing baseline metric")
            )
            continue
        slip = float(base) - float(current)
        if slip > float(slip_limit):
            failures.append(
                GateReason(
                    "baseline_slip_exceeded", _surface_for_metric(key), key, slip, float(slip_limit), _owner_for_metric(key), (
                        f"slip {key}: {slip:.4f} > max_slip {float(slip_limit):.4f} "
                        f"(baseline={float(base):.4f}, current={float(current):.4f})"
                    ),
                )
            )

    return GateDecision.approve() if not failures else GateDecision("block", tuple(failures), tuple(failures))


def _surface_for_metric(metric: str) -> str:
    if metric == "drift_ok":
        return "ingest"
    if any(token in metric for token in ("recall", "precision", "mrr", "ndcg")):
        return "retrieval"
    if any(token in metric for token in ("groundedness", "refusal", "citation")):
        return "generation"
    return "infra"


def _owner_for_metric(metric: str) -> str:
    return "generate" if _surface_for_metric(metric) == "generation" else _surface_for_metric(metric)


def check_gate_blind(metrics: dict[str, Any]) -> tuple[bool, list[str]]:
    """Blind path for Task 8 sims: always pass (no regression detection)."""
    _ = metrics
    return (True, [])


def metrics_for_baseline(metrics: dict[str, Any]) -> dict[str, Any]:
    """Extract the numeric gate metrics (+ drift_ok) for a baseline file."""
    out: dict[str, Any] = {}
    for key in METRIC_KEYS:
        if key in metrics:
            out[key] = metrics[key]
    return out


def run_gate(
    *,
    metrics_path: Path | str = DEFAULT_METRICS,
    thresholds_path: Path | str = DEFAULT_THRESHOLDS,
    baseline_path: Path | str = DEFAULT_BASELINE,
) -> tuple[bool, list[str]]:
    metrics = load_metrics(metrics_path)
    thresholds = load_thresholds(thresholds_path)
    baseline = load_baseline(baseline_path)
    return check_gate(metrics, thresholds, baseline)
