from __future__ import annotations

import json
from pathlib import Path

from protocol_next import GateDecision, RunManifest, replay_manifest
from protocol_next.__main__ import main


def test_replay_manifest_validates_decision_and_lifecycle_stream(tmp_path: Path) -> None:
    events_path = tmp_path / "events.jsonl"
    events_path.write_text(
        "\n".join(
            json.dumps(
                {
                    "type": kind,
                    "run_id": "run-123",
                    "occurred_at": "now",
                    "data": {"outcome": "pass"} if kind != "run.started" else {},
                }
            )
            for kind in ("run.started", "gate.decided", "run.completed")
        )
        + "\n",
        encoding="utf-8",
    )
    manifest = RunManifest(
        run_id="run-123",
        started_at="now",
        decision=GateDecision.passed(),
        identifiers={"build": "build-123"},
        hashes={"input": "hash"},
        artifacts={"events": str(events_path)},
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    replay = replay_manifest(manifest_path)

    assert replay["outcome"] == "pass"
    assert replay["events"] == 3

    assert main(["check", "--manifest", str(manifest_path)]) == 0
