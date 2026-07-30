"""RAG lifecycle events with replayable IDs and parent relationships."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from uuid import uuid4


EVENT_TYPES = frozenset({
    "corpus.fingerprint.computed", "drift.detected", "ingest.started", "ingest.completed",
    "evaluation.started", "retrieval.completed", "generation.completed", "gate.decided",
    "alert.emitted", "run.completed", "run.started", "input.changed", "work.completed",
})


@dataclass(frozen=True)
class LifecycleEvent:
    type: str
    run_id: str
    occurred_at: str
    data: Mapping[str, Any] = field(default_factory=dict)
    event_id: str | None = None
    parent_event_id: str | None = None
    schema_version: str = "rag-reliability-events/v1"

    def __post_init__(self) -> None:
        if self.type not in EVENT_TYPES:
            raise ValueError(f"unsupported lifecycle event: {self.type}")
        if not self.run_id.strip() or (self.event_id is not None and not self.event_id.strip()):
            raise ValueError("event identifiers must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LifecycleEvent":
        return cls(str(value["type"]), str(value["run_id"]), str(value["occurred_at"]), dict(value.get("data") or {}), value.get("event_id"), value.get("parent_event_id"), str(value["schema_version"]) if "schema_version" in value else None)  # type: ignore[arg-type]


class EventLog:
    def __init__(self, path: Path | str, *, run_id: str) -> None:
        self.path, self.run_id, self._last_event_id = Path(path), run_id, None

    def emit(self, event_type: str, data: Mapping[str, Any] | None = None, *, parent_event_id: str | None = None) -> LifecycleEvent:
        event = LifecycleEvent(event_type, self.run_id, datetime.now(timezone.utc).isoformat(), dict(data or {}), str(uuid4()), parent_event_id or self._last_event_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
        self._last_event_id = event.event_id
        return event


def collect_lifecycle_events(path: Path | str, *, run_id: str) -> list[LifecycleEvent]:
    return [event for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip() for event in (LifecycleEvent.from_dict(json.loads(line)),) if event.run_id == run_id]
