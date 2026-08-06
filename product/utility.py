"""Operational utility metrics for the product gate."""

from __future__ import annotations

from statistics import median
from typing import Any, Iterable


def summarize_utility(observations: Iterable[dict[str, Any]]) -> dict[str, Any]:
    rows = list(observations)
    runs = len(rows)
    if not runs:
        return {
            "runs": 0,
            "false_alerts_per_100_runs": 0.0,
            "miss_rate": 0.0,
            "lead_time_ms_median": None,
            "review_latency_ms_p95": None,
        }
    false_alerts = sum(bool(row.get("alerted")) and not bool(row.get("true_incident")) for row in rows)
    misses = sum(not bool(row.get("alerted")) and bool(row.get("true_incident")) for row in rows)
    lead_times = sorted(float(row["lead_time_ms"]) for row in rows if row.get("lead_time_ms") is not None)
    review_latencies = sorted(float(row["review_latency_ms"]) for row in rows if row.get("review_latency_ms") is not None)
    return {
        "runs": runs,
        "false_alerts_per_100_runs": false_alerts * 100.0 / runs,
        "miss_rate": misses / runs,
        "lead_time_ms_median": float(median(lead_times)) if lead_times else None,
        "review_latency_ms_p95": _percentile(review_latencies, 95) if review_latencies else None,
    }


def _percentile(values: list[float], pct: float) -> float:
    if len(values) == 1:
        return values[0]
    rank = (pct / 100.0) * (len(values) - 1)
    lo, hi = int(rank), min(int(rank) + 1, len(values) - 1)
    return values[lo] + (values[hi] - values[lo]) * (rank - lo)
