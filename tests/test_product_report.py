from __future__ import annotations

import json

from agent_reliability_protocol import DecisionReason, Evidence, GateDecision, LifecycleEvent, RunManifest
from product.report import ProductGateReport


def _manifest(decision: GateDecision) -> RunManifest:
    return RunManifest(
        schema_version="2.0.5",
        experiment_id="rag-product",
        run_id="run-123",
        created_at="2026-07-31T00:00:00+00:00",
        git_sha="abc123",
        harness_name="rag-reliability-harness",
        harness_version="0.2.0",
        dataset_id="demo",
        dataset_hash="dataset-hash",
        configuration_hash="config-hash",
        model_provider="local",
        model_name="hash-embedder",
        model_version="1",
        random_seed=7,
        replication_count=1,
        environment={"python": "3.11"},
        decision=decision,
    )


def test_product_report_serializes_shared_manifest_events_and_rag_payload() -> None:
    reason = DecisionReason(
        "floor_not_met",
        "recall@5 is below its required floor",
        (Evidence("metric", "recall@5", 0.2, 0.8, ">="),),
    )
    decision = GateDecision(decision="block", reasons=(reason,), checkpoint="gate.decided", threshold_version="ci-v1")
    manifest = _manifest(decision)
    events = [
        LifecycleEvent(
            event_id="evt-1", schema_version="2.0.5", experiment_id="rag-product", run_id="run-123",
            episode_id="run-123", replication_id=0, sequence_number=1, checkpoint="episode.started",
            event_type="episode.started", started_at="2026-07-31T00:00:00+00:00", ended_at="2026-07-31T00:00:00+00:00",
            attributes={"component": "closed_loop"},
        ),
        LifecycleEvent(
            event_id="evt-2", schema_version="2.0.5", experiment_id="rag-product", run_id="run-123",
            episode_id="run-123", replication_id=0, sequence_number=2, checkpoint="gate.decided",
            event_type="gate.decided", started_at="2026-07-31T00:00:01+00:00", ended_at="2026-07-31T00:00:01+00:00",
            attributes={"decision": "block"}, parent_event_id="evt-1",
        ),
    ]
    report = ProductGateReport.from_run(
        manifest,
        events,
        metrics={"recall@5": 0.2},
        rag={"drift_classification": "none", "owners": ["retrieval"]},
    )

    payload = report.to_dict()
    assert payload["manifest"]["run_id"] == "run-123"
    assert payload["events"][1]["event_type"] == "gate.decided"
    assert payload["decision"]["decision"] == "block"
    assert payload["rag"]["owners"] == ["retrieval"]
    assert json.loads(report.to_json())["metrics"]["recall@5"] == 0.2


def test_product_report_emits_sarif_result_for_each_shared_reason() -> None:
    reason = DecisionReason(
        "drift.required",
        "corpus drift must be resolved",
        (Evidence("condition", "drift_ok", False, True, "=="),),
    )
    report = ProductGateReport.from_run(
        _manifest(GateDecision(decision="block", reasons=(reason,), checkpoint="gate.decided", threshold_version="ci-v1")),
        [],
        metrics={},
    )

    sarif = report.to_sarif()
    assert sarif["version"] == "2.1.0"
    result = sarif["runs"][0]["results"][0]
    assert result["ruleId"] == "drift.required"
    assert result["level"] == "error"
    assert result["properties"]["runId"] == "run-123"


def test_product_report_rejects_events_from_another_run() -> None:
    manifest = _manifest(GateDecision(decision="approve", checkpoint="gate.decided", threshold_version="ci-v1"))
    event = LifecycleEvent(
        event_id="evt-1", schema_version="2.0.5", experiment_id="rag-product", run_id="other-run",
        episode_id="other-run", replication_id=0, sequence_number=1, checkpoint="episode.started",
        event_type="episode.started", started_at="2026-07-31T00:00:00+00:00", ended_at="2026-07-31T00:00:00+00:00",
        attributes={},
    )

    try:
        ProductGateReport.from_run(manifest, [event], metrics={})
    except ValueError as exc:
        assert "run_id" in str(exc)
    else:
        raise AssertionError("events from another run must be rejected")
