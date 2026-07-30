"""Manifest validation and lifecycle replay without domain dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_reliability_protocol import RunManifest
from protocol_next.events import collect_lifecycle_events


def replay_manifest(path: Path | str) -> dict[str, Any]:
    """Validate a manifest and replay its recorded lifecycle event stream."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "manifest" in payload:
        payload = payload["manifest"]
    manifest = RunManifest.from_dict(payload)
    events_path = manifest.artifacts.get("events")
    events = collect_lifecycle_events(events_path, run_id=manifest.run_id) if events_path else []
    if events:
        _validate_lifecycle(events, manifest)
    return {
        "run_id": manifest.run_id,
        "outcome": manifest.decision.outcome,
        "events": len(events),
    }


def _validate_lifecycle(events: list[Any], manifest: RunManifest) -> None:
    event_types = [event.type for event in events]
    required = ["run.started", "gate.decided", "run.completed"]
    if any(event_type not in event_types for event_type in required):
        raise ValueError("lifecycle stream is missing required events")
    gate = next(event for event in events if event.type == "gate.decided")
    completed = next(event for event in reversed(events) if event.type == "run.completed")
    expected = manifest.decision.outcome
    if gate.data.get("outcome") != expected or completed.data.get("outcome") != expected:
        raise ValueError("lifecycle decision does not match manifest")
