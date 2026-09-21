from __future__ import annotations

import pytest

from gates.run import check_gate, check_gate_blind, decide_gate, load_baseline, load_thresholds


@pytest.fixture
def thresholds() -> dict:
    return load_thresholds()


@pytest.fixture
def baseline() -> dict:
    return {
        "recall@5": 0.90,
        "mrr": 0.80,
        "groundedness": 0.95,
        "refusal_accuracy": 1.0,
        "precision@5": 0.40,
        "drift_ok": True,
    }


def test_gate_fails_below_threshold(thresholds, baseline):
    assert check_gate({"recall@5": 0.1, "drift_ok": True}, thresholds, baseline)[0] is False


def test_gate_fails_on_baseline_slip():
    thresholds = {
        "require_drift_ok": True,
        "floors": {
            "recall@5": 0.50,
            "mrr": 0.40,
            "groundedness": 0.50,
            "refusal_accuracy": 0.50,
            "precision@5": 0.10,
        },
        "max_slip": {
            "recall@5": 0.05,
            "mrr": 0.05,
            "groundedness": 0.05,
            "refusal_accuracy": 0.05,
        },
    }
    baseline = {
        "recall@5": 0.90,
        "mrr": 0.80,
        "groundedness": 0.95,
        "refusal_accuracy": 1.0,
        "precision@5": 0.40,
    }
    current = {**baseline, "recall@5": 0.80, "drift_ok": True}
    assert check_gate(current, thresholds, baseline)[0] is False


def test_gate_fails_when_drift_ok_false(thresholds, baseline):
    happy_enough_metrics = {
        "recall@5": 0.90,
        "precision@5": 0.40,
        "mrr": 0.80,
        "groundedness": 0.95,
        "refusal_accuracy": 1.0,
        "drift_ok": False,
    }
    assert check_gate(happy_enough_metrics, thresholds, baseline)[0] is False


def test_gate_passes_happy_path(thresholds):
    baseline = load_baseline()
    current = {**baseline, "drift_ok": True}
    ok, failures = check_gate(current, thresholds, baseline)
    assert ok is True, failures


def test_check_gate_blind_always_passes():
    ok, failures = check_gate_blind({"recall@5": 0.0, "drift_ok": False})
    assert ok is True
    assert failures == []


def test_decide_gate_returns_structured_reasons() -> None:
    decision = decide_gate(
        {"recall@5": 0.1, "drift_ok": True},
        {"floors": {"recall@5": 0.5}},
        {},
    )

    assert decision.outcome == "fail"
    assert decision.reasons[0].code == "floor_not_met"
    evidence = decision.reasons[0].evidence[0]
    assert evidence.subject == "recall@5"
    assert evidence.observed == 0.1
    assert evidence.expected == 0.5


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), -float("inf"), True, "0.9", "bad", [], {}, 10**400])
@pytest.mark.parametrize("source", ["metric", "baseline", "floor", "max_slip"])
def test_gate_blocks_invalid_numeric_evidence(invalid, source):
    import json

    metrics = {"mrr": 0.9}
    baseline = {"mrr": 0.9}
    thresholds = {"floors": {"mrr": 0.5}, "max_slip": {"mrr": 0.1}}
    if source == "metric":
        metrics["mrr"] = invalid
    elif source == "baseline":
        baseline["mrr"] = invalid
    elif source == "floor":
        thresholds["floors"]["mrr"] = invalid
    else:
        thresholds["max_slip"]["mrr"] = invalid

    decision = decide_gate(metrics, thresholds, baseline)

    assert decision.decision == "block"
    code = {"metric": "metric.invalid", "baseline": "baseline.metric_invalid", "floor": "threshold.invalid", "max_slip": "threshold.invalid"}[source]
    assert any(reason.code == code and reason.metric == "mrr" for reason in decision.reasons)
    json.dumps(decision.to_dict(), allow_nan=False)
    assert check_gate(metrics, thresholds, baseline)[0] is False


def test_gate_rejects_negative_slip_budget():
    decision = decide_gate({"mrr": 0.9}, {"max_slip": {"mrr": -0.1}}, {"mrr": 0.9})
    assert decision.decision == "block"
    assert decision.reasons[0].code == "threshold.invalid"


def test_gate_preserves_finite_boundaries_and_missing_reasons():
    assert decide_gate({"mrr": 1}, {"floors": {"mrr": 1}, "max_slip": {"mrr": 0}}, {"mrr": 1}).decision == "approve"
    missing = decide_gate({}, {"floors": {"mrr": 0.5}}, {})
    assert missing.reasons[0].code == "metric.missing"
    missing_baseline = decide_gate({"mrr": 0.9}, {"max_slip": {"mrr": 0.1}}, {})
    assert missing_baseline.reasons[0].code == "baseline.metric_missing"


def test_gate_cli_blocks_nonfinite_measurement(tmp_path, capsys):
    from gates.__main__ import main

    metrics = tmp_path / "metrics.json"
    metrics.write_text('{"mrr": NaN}', encoding="utf-8")
    baseline = tmp_path / "baseline.json"
    baseline.write_text('{"mrr": 0.9}', encoding="utf-8")
    thresholds = tmp_path / "thresholds.yaml"
    thresholds.write_text('floors:\n  mrr: 0.5\n', encoding="utf-8")

    assert main(["--metrics", str(metrics), "--baseline", str(baseline), "--thresholds", str(thresholds)]) == 1
    output = capsys.readouterr().out
    assert "GATE FAIL" in output
    assert "mrr" in output


def test_gate_blocks_unrepresentable_slip_without_nonfinite_evidence():
    import json

    decision = decide_gate({"score": -1e308}, {"max_slip": {"score": 0.1}}, {"score": 1e308})
    assert decision.decision == "block"
    json.dumps(decision.to_dict(), allow_nan=False)


@pytest.mark.parametrize("section", ["floors", "max_slip"])
@pytest.mark.parametrize("invalid", [[], "", 0, False, None, [0.5], "mrr"])
def test_gate_blocks_malformed_rule_sections(section, invalid):
    decision = decide_gate({"mrr": 0.9}, {section: invalid}, {"mrr": 0.9})
    assert decision.decision == "block"
    assert decision.reasons[0].code == "threshold.invalid"


@pytest.mark.parametrize("invalid", [float("nan"), float("inf"), "true", 1, {}, []])
def test_invalid_drift_evidence_is_strict_json(invalid):
    import json

    decision = decide_gate({"drift_ok": invalid}, {"require_drift_ok": True}, {})
    assert decision.decision == "block"
    json.dumps(decision.to_dict(), allow_nan=False)


@pytest.mark.parametrize("invalid", ["false", "", 0, None, [], {}])
def test_drift_requirement_must_be_boolean(invalid):
    assert decide_gate({}, {"require_drift_ok": invalid}, {}).decision == "block"


def test_empty_numeric_rule_mappings_remain_intentional():
    assert decide_gate({}, {"floors": {}, "max_slip": {}, "require_drift_ok": False}, {}).decision == "approve"


@pytest.mark.parametrize("key", [1, None, ""])
@pytest.mark.parametrize("section", ["floors", "max_slip"])
def test_gate_rejects_rule_names_that_are_not_metric_names(section, key):
    decision = decide_gate({}, {section: {key: 0.1}}, {})
    assert decision.decision == "block"
    assert decision.reasons[0].code == "threshold.invalid"
