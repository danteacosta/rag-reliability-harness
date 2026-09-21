from __future__ import annotations

import json
import math
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
        floor_number = _finite_number(floor)
        if floor_number is None:
            failures.append(_invalid_number_reason("threshold.invalid", key, "floor"))
            continue
        floor = floor_number
        value = metrics.get(key)
        if value is None:
            failures.append(
                GateReason("metric.missing", _surface_for_metric(key), key, None, float(floor), _owner_for_metric(key), f"floor {key}: missing metric")
            )
            continue
        value_number = _finite_number(value)
        if value_number is None:
            failures.append(_invalid_number_reason("metric.invalid", key, "current metric"))
            continue
        value = value_number
        if value < floor:
            failures.append(
                GateReason("floor_not_met", _surface_for_metric(key), key, float(value), float(floor), _owner_for_metric(key), f"floor {key}: {float(value):.4f} < {float(floor):.4f}")
            )

    max_slip = thresholds.get("max_slip") or {}
    for key, slip_limit in max_slip.items():
        limit_number = _finite_number(slip_limit)
        if limit_number is None or limit_number < 0:
            failures.append(_invalid_number_reason("threshold.invalid", key, "max_slip", nonnegative=True))
            continue
        slip_limit = limit_number
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
        current_number = _finite_number(current)
        base_number = _finite_number(base)
        if current_number is None:
            failures.append(_invalid_number_reason("metric.invalid", key, "current metric"))
        if base_number is None:
            failures.append(_invalid_number_reason("baseline.metric_invalid", key, "baseline metric"))
        if current_number is None or base_number is None:
            continue
        current, base = current_number, base_number
        slip = base - current
        if not math.isfinite(slip):
            failures.append(_invalid_number_reason("metric.comparison_invalid", key, "computed slip"))
            continue
        if slip > slip_limit:
            failures.append(
                GateReason(
                    "baseline_slip_exceeded", _surface_for_metric(key), key, slip, float(slip_limit), _owner_for_metric(key), (
                        f"slip {key}: {slip:.4f} > max_slip {float(slip_limit):.4f} "
                        f"(baseline={float(base):.4f}, current={float(current):.4f})"
                    ),
                )
            )

    return GateDecision.approve() if not failures else GateDecision("block", tuple(failures), tuple(failures))


def _finite_number(value: Any) -> float | None:
    """Accept JSON numbers only, without coercing labels or booleans."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except OverflowError:
        return None
    return number if math.isfinite(number) else None


def _invalid_number_reason(
    code: str, metric: str, source: str, *, nonnegative: bool = False,
) -> GateReason:
    constraint = "a finite nonnegative number" if nonnegative else "a finite number"
    return GateReason(
        code=code, surface=_surface_for_metric(metric), metric=metric,
        owner=_owner_for_metric(metric),
        message=f"{source} {metric}: must be {constraint} (booleans and strings are not measurements)",
    )


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
