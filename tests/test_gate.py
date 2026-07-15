from __future__ import annotations

import pytest

from gates.run import check_gate, check_gate_blind, load_baseline, load_thresholds


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
