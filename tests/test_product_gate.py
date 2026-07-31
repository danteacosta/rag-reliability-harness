from __future__ import annotations

from product.gate import decide_product_gate


def test_product_gate_returns_shared_approve_decision_when_thresholds_hold() -> None:
    decision = decide_product_gate(
        {"recall@5": 0.9, "drift_ok": True},
        {"floors": {"recall@5": 0.8}, "require_drift_ok": True},
        {},
    )

    assert decision.decision == "approve"
    assert decision.to_dict()["decision"] == "approve"


def test_product_gate_returns_shared_block_decision_with_structured_metric_evidence() -> None:
    decision = decide_product_gate(
        {"recall@5": 0.2},
        {"floors": {"recall@5": 0.8}},
        {},
    )

    assert decision.decision == "block"
    assert decision.reasons[0].code == "floor_not_met"
    evidence = decision.reasons[0].evidence[0]
    assert evidence.subject == "recall@5"
    assert evidence.observed == 0.2
    assert evidence.expected == 0.8


def test_product_gate_preserves_rag_metric_reason_without_local_gate_type() -> None:
    decision = decide_product_gate(
        {"mrr": 0.4, "baseline_mrr": 0.7},
        {"max_slip": {"mrr": 0.1}, "threshold_version": "ci-v1"},
        {"mrr": 0.7},
    )

    assert decision.decision == "block"
    assert decision.threshold_version == "ci-v1"
    assert decision.reasons[0].evidence[0].subject == "mrr"
