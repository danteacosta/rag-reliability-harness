import pytest

from product.utility import summarize_utility


def test_utility_summary_reports_alert_rate_lead_time_and_review_latency():
    summary = summarize_utility(
        [
            {"run_id": "r1", "alerted": True, "true_incident": True, "lead_time_ms": 100, "review_latency_ms": 50},
            {"run_id": "r2", "alerted": True, "true_incident": False, "lead_time_ms": 200, "review_latency_ms": 150},
            {"run_id": "r3", "alerted": False, "true_incident": True, "lead_time_ms": None, "review_latency_ms": 80},
        ]
    )
    assert summary["runs"] == 3
    assert summary["false_alerts_per_100_runs"] == pytest.approx(33.33333333333333)
    assert summary["miss_rate"] == pytest.approx(0.3333333333333333)
    assert summary["lead_time_ms_median"] == 150.0
    assert summary["review_latency_ms_p95"] == 143.0
    assert summary["captured_regressions"] == 1
    assert summary["escaped_incidents"] == 1
    assert summary["cost_usd_total"] == pytest.approx(0.0)


def test_utility_summary_reports_cost_and_capture_efficiency():
    summary = summarize_utility(
        [
            {"run_id": "r1", "alerted": True, "true_incident": True, "cost_usd": 0.01},
            {"run_id": "r2", "alerted": True, "true_incident": False, "cost_usd": 0.02},
        ]
    )
    assert summary["captured_regressions"] == 1
    assert summary["escaped_incidents"] == 0
    assert summary["cost_usd_total"] == pytest.approx(0.03)
    assert summary["cost_usd_per_captured_regression"] == pytest.approx(0.03)


@pytest.mark.parametrize(
    "row",
    [
        {"alerted": 1, "true_incident": False},
        {"alerted": False, "true_incident": False, "cost_usd": -1},
        {"alerted": False, "true_incident": False, "review_latency_ms": float("nan")},
    ],
)
def test_utility_rejects_malformed_observations(row):
    with pytest.raises(ValueError):
        summarize_utility([row])
