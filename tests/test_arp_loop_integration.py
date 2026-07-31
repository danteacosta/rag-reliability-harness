from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_reliability_protocol import LifecycleEvent, RunManifest
from loop.run import run_closed_loop
from product.arp_adapter import read_arp_events, read_arp_manifest


ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"
GOLDEN = ROOT / "data" / "golden" / "set.jsonl"
THRESHOLDS = ROOT / "eval" / "thresholds.yaml"
BASELINE = ROOT / "eval" / "baselines" / "ci.json"
ONLINE = ROOT / "data" / "online" / "traffic_sample.jsonl"


def test_closed_loop_emits_arp_v2_manifest_and_events(tmp_path: Path) -> None:
    result = run_closed_loop(
        corpus_root=CORPUS,
        index_dir=tmp_path / "index",
        golden_path=GOLDEN,
        online_path=ONLINE,
        thresholds_path=THRESHOLDS,
        baseline_path=BASELINE,
        runs_root=tmp_path / "runs",
        force_reingest=True,
    )

    manifest_path = Path(result["manifest_path"])
    manifest = read_arp_manifest(manifest_path)
    events_path = manifest_path.parent / manifest.artifacts["events"]
    events = read_arp_events(events_path, run_id=manifest.run_id)

    assert isinstance(manifest, RunManifest)
    assert manifest.schema_version == "2.0.5"
    assert manifest.metadata["rag"]["drift_classification"] in {"none", "index_missing", "corpus_index_mismatch"}
    assert events
    assert all(isinstance(event, LifecycleEvent) for event in events)
    assert all(event.schema_version == "2.0.5" for event in events)
    assert events[-1].event_type == "episode.completed"
    assert any(event.event_type == "gate.decided" for event in events)


def test_invalid_arp_event_envelope_fails_closed(tmp_path: Path) -> None:
    event_path = tmp_path / "events.jsonl"
    event_path.write_text(
        json.dumps(
            {
                "event_id": "evt-1",
                "schema_version": "not-semver",
                "experiment_id": "exp",
                "run_id": "run",
                "episode_id": "run",
                "replication_id": 0,
                "sequence_number": 1,
                "checkpoint": "episode.started",
                "event_type": "episode.started",
                "started_at": "now",
                "ended_at": "now",
                "attributes": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid ARP lifecycle envelope"):
        read_arp_events(event_path, run_id="run")
