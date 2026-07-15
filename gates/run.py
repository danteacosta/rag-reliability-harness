from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

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
    """Return (passed, failure_reasons)."""
    failures: list[str] = []

    if thresholds.get("require_drift_ok", False) and metrics.get("drift_ok") is not True:
        failures.append("drift_ok required but metrics['drift_ok'] is not True")

    floors = thresholds.get("floors") or {}
    for key, floor in floors.items():
        value = metrics.get(key)
        if value is None:
            failures.append(f"floor {key}: missing metric")
            continue
        if float(value) < float(floor):
            failures.append(f"floor {key}: {float(value):.4f} < {float(floor):.4f}")

    max_slip = thresholds.get("max_slip") or {}
    for key, slip_limit in max_slip.items():
        current = metrics.get(key)
        base = baseline.get(key)
        if current is None:
            failures.append(f"slip {key}: missing current metric")
            continue
        if base is None:
            failures.append(f"slip {key}: missing baseline metric")
            continue
        slip = float(base) - float(current)
        if slip > float(slip_limit):
            failures.append(
                f"slip {key}: {slip:.4f} > max_slip {float(slip_limit):.4f} "
                f"(baseline={float(base):.4f}, current={float(current):.4f})"
            )

    return (len(failures) == 0, failures)


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
