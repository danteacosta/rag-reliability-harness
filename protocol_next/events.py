"""RAG event-log compatibility layer over shared ARP event primitives."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_reliability_protocol import JsonlExporter, LifecycleEvent, new_event


class EventLog:
    """Local append-only convenience wrapper retained for the closed-loop API."""

    def __init__(self, path: Path | str, *, run_id: str) -> None:
        self.path = Path(path)
        self.run_id = run_id
        self._exporter = JsonlExporter(self.path)

    def emit(self, event_type: str, data: Mapping[str, Any] | None = None) -> LifecycleEvent:
        event = new_event(event_type, self.run_id, data)
        self._exporter.export(event)
        return event


def collect_lifecycle_events(path: Path | str, *, run_id: str) -> list[LifecycleEvent]:
    events: list[LifecycleEvent] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = LifecycleEvent.from_dict(json.loads(line))
            if event.run_id == run_id:
                events.append(event)
    return events
