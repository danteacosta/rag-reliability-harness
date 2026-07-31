"""A product-facing RAG gate backed by the shared ARP decision contract."""

from __future__ import annotations

from typing import Any, Mapping

from agent_reliability_protocol import DecisionReason, Evidence, GateDecision


def decide_product_gate(
    metrics: Mapping[str, Any],
    thresholds: Mapping[str, Any],
    baseline: Mapping[str, Any],
) -> GateDecision:
    """Evaluate RAG metrics and return the shared ARP v2 gate decision.

    RAG-specific metric names and ownership remain evidence payloads.  The
    returned decision and reasons are always neutral ARP objects, allowing a
    CI consumer to render the result without importing ``rag_harness`` types.
    """

    reasons: list[DecisionReason] = []
    if thresholds.get("require_drift_ok", False) and metrics.get("drift_ok") is not True:
        reasons.append(
            _reason(
                "drift.required",
                "drift_ok required but metrics['drift_ok'] is not True",
                kind="condition",
                subject="drift_ok",
                observed=metrics.get("drift_ok"),
                expected=True,
                comparator="==",
            )
        )

    for key, floor in (thresholds.get("floors") or {}).items():
        value = metrics.get(key)
        if value is None:
            reasons.append(
                _reason(
                    "metric.missing",
                    f"floor {key}: missing metric",
                    kind="metric",
                    subject=key,
                    expected=float(floor),
                    comparator=">=",
                )
            )
        elif float(value) < float(floor):
            reasons.append(
                _reason(
                    "floor_not_met",
                    f"floor {key}: {float(value):.4f} < {float(floor):.4f}",
                    kind="metric",
                    subject=key,
                    observed=float(value),
                    expected=float(floor),
                    comparator=">=",
                )
            )

    for key, slip_limit in (thresholds.get("max_slip") or {}).items():
        current = metrics.get(key)
        base = baseline.get(key)
        if current is None:
            reasons.append(
                _reason(
                    "metric.missing",
                    f"slip {key}: missing current metric",
                    kind="metric",
                    subject=key,
                    expected=float(slip_limit),
                    comparator="<=",
                )
            )
        elif base is None:
            reasons.append(
                _reason(
                    "baseline.metric_missing",
                    f"slip {key}: missing baseline metric",
                    kind="baseline",
                    subject=key,
                    observed=float(current),
                    expected=float(slip_limit),
                    comparator="<=",
                )
            )
        else:
            slip = float(base) - float(current)
            if slip > float(slip_limit):
                reasons.append(
                    _reason(
                        "baseline_slip_exceeded",
                        f"slip {key}: {slip:.4f} > max_slip {float(slip_limit):.4f} "
                        f"(baseline={float(base):.4f}, current={float(current):.4f})",
                        kind="metric",
                        subject=key,
                        observed=slip,
                        expected=float(slip_limit),
                        comparator="<=",
                    )
                )

    threshold_version = str(
        thresholds.get("threshold_version")
        or (thresholds.get("provenance") or {}).get("threshold_version")
        or "rag-product"
    )
    if not reasons:
        return GateDecision(
            decision="approve",
            checkpoint="gate.decided",
            threshold_version=threshold_version,
        )
    return GateDecision(
        decision="block",
        reasons=tuple(reasons),
        checkpoint="gate.decided",
        threshold_version=threshold_version,
    )


def _reason(
    code: str,
    message: str,
    *,
    kind: str,
    subject: str,
    observed: Any = None,
    expected: Any = None,
    comparator: str | None = None,
) -> DecisionReason:
    return DecisionReason(
        code=code,
        message=message,
        evidence=(
            Evidence(
                kind=kind,
                subject=subject,
                observed=observed,
                expected=expected,
                comparator=comparator,
                source="rag-reliability",
            ),
        ),
    )
