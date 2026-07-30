from __future__ import annotations

import pytest

from protocol_next import DecisionReason, Evidence, GateDecision, RunManifest


def test_gate_decision_keeps_structured_reason_and_evidence() -> None:
    evidence = Evidence(
        kind="metric",
        subject="recall@5",
        observed=0.1,
        expected=0.5,
        comparator=">=",
    )
    reason = DecisionReason(
        code="floor_not_met",
        message="recall@5 is below its required floor",
        evidence=(evidence,),
    )

    decision = GateDecision.failed(reason)

    assert decision.outcome == "fail"
    assert decision.exit_code == 1
    assert decision.reasons[0].to_dict()["evidence"][0]["subject"] == "recall@5"


def test_run_manifest_captures_complete_neutral_provenance() -> None:
    manifest = RunManifest(
        run_id="run-123",
        started_at="2026-07-30T00:00:00+00:00",
        decision=GateDecision.passed(),
        provenance={
            "git": {"commit": "abc123"},
            "corpus": {"hash": "corpus-hash"},
            "golden": {"hash": "golden-hash"},
            "config": {"hash": "config-hash"},
            "model": {"name": "hash-embedder"},
            "index": {"hash": "index-hash"},
            "baseline": {"hash": "baseline-hash"},
            "thresholds": {"hash": "thresholds-hash"},
        },
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == "protocol_next/v1"
    assert payload["decision"]["outcome"] == "pass"
    assert set(payload["provenance"]) == {
        "git", "corpus", "golden", "config", "model", "index", "baseline", "thresholds"
    }
    assert "recall@5" not in payload


def test_run_manifest_rejects_incomplete_provenance() -> None:
    with pytest.raises(ValueError, match="missing required provenance"):
        RunManifest(
            run_id="run-123",
            started_at="2026-07-30T00:00:00+00:00",
            decision=GateDecision.passed(),
            provenance={"git": {"commit": "abc123"}},
        )
