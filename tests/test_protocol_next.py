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
        identifiers={"git_commit": "abc123", "model": "hash-embedder"},
        hashes={
            "corpus": "corpus-hash",
            "golden": "golden-hash",
            "config": "config-hash",
            "index": "index-hash",
            "baseline": "baseline-hash",
            "thresholds": "thresholds-hash",
        },
        metadata={"index_backend": "memory"},
        configuration={"retrieval_k": 5},
    )

    payload = manifest.to_dict()

    assert payload["schema_version"] == "arp/v1"
    assert payload["decision"]["outcome"] == "pass"
    assert payload["identifiers"]["git_commit"] == "abc123"
    assert payload["hashes"]["corpus"] == "corpus-hash"
    assert payload["metadata"] == {"index_backend": "memory"}
    assert payload["configuration"] == {"retrieval_k": 5}
    assert "recall@5" not in payload


def test_run_manifest_rejects_empty_required_identifier_or_hash() -> None:
    with pytest.raises(ValueError, match="run_id"):
        RunManifest(
            run_id="",
            started_at="2026-07-30T00:00:00+00:00",
            decision=GateDecision.passed(),
            identifiers={},
            hashes={"input": "hash"},
        )

    with pytest.raises(ValueError, match="identifiers"):
        RunManifest(
            run_id="run-123",
            started_at="2026-07-30T00:00:00+00:00",
            decision=GateDecision.passed(),
            identifiers={},
            hashes={"input": "hash"},
        )

    with pytest.raises(ValueError, match="hashes"):
        RunManifest(
            run_id="run-123",
            started_at="2026-07-30T00:00:00+00:00",
            decision=GateDecision.passed(),
            identifiers={"build": "build-123"},
            hashes={"input": ""},
        )


@pytest.mark.parametrize(
    ("outcome", "reasons", "message"),
    [
        ("pass", (DecisionReason("unexpected", "unexpected"),), "passed"),
        ("fail", (), "failed"),
        ("unknown", (), "outcome"),
    ],
)
def test_gate_decision_rejects_invalid_states(
    outcome: str, reasons: tuple[DecisionReason, ...], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        GateDecision(outcome=outcome, reasons=reasons)  # type: ignore[arg-type]
