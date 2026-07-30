"""Domain-neutral lifecycle events that can be persisted as JSON Lines."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


LIFECYCLE_EVENT_TYPES = frozenset(
    {"run.started", "input.changed", "work.completed", "gate.decided", "run.completed"}
)


@dataclass(frozen=True)
class LifecycleEvent:
    type: str
    run_id: str
    occurred_at: str
    data: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.type not in LIFECYCLE_EVENT_TYPES:
            raise ValueError(f"unsupported lifecycle event: {self.type}")
        if not self.run_id.strip():
            raise ValueError("event run_id must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "run_id": self.run_id,
            "occurred_at": self.occurred_at,
            "data": dict(self.data),
        }

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "LifecycleEvent":
        return cls(
            type=str(value["type"]),
            run_id=str(value["run_id"]),
            occurred_at=str(value["occurred_at"]),
            data=dict(value.get("data") or {}),
        )


class EventLog:
    """Append-only JSONL event sink for one run."""

    def __init__(self, path: Path | str, *, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id

    def emit(self, event_type: str, data: Mapping[str, Any] | None = None) -> LifecycleEvent:
        event = LifecycleEvent(
            type=event_type,
            run_id=self.run_id,
            occurred_at=datetime.now(timezone.utc).isoformat(),
            data=dict(data or {}),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
        return event


def collect_lifecycle_events(path: Path | str, *, run_id: str) -> list[LifecycleEvent]:
    events: list[LifecycleEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = LifecycleEvent.from_dict(json.loads(line))
            if event.run_id == run_id:
                events.append(event)
    return events
