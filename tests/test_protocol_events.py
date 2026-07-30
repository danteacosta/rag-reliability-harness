from __future__ import annotations

import json
from pathlib import Path

from protocol_next import EventLog, LifecycleEvent, collect_lifecycle_events


def test_event_log_emits_replayable_lifecycle_events(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = EventLog(path, run_id="run-123")

    events.emit("run.started", {"actor": "loop"})
    events.emit("gate.decided", {"outcome": "pass"})
    events.emit("run.completed", {"outcome": "pass"})

    replayed = collect_lifecycle_events(path, run_id="run-123")
    assert [event.type for event in replayed] == ["run.started", "gate.decided", "run.completed"]
    assert json.loads(path.read_text().splitlines()[0])["run_id"] == "run-123"


def test_lifecycle_event_rejects_unknown_type() -> None:
    try:
        LifecycleEvent(type="not-a-lifecycle-event", run_id="run-123", occurred_at="now")
    except ValueError as exc:
        assert "unsupported lifecycle event" in str(exc)
    else:
        raise AssertionError("expected invalid event type to fail")
