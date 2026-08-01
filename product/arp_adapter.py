"""Producer-side adapter from RAG lifecycle labels to ARP v2 envelopes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from agent_reliability_protocol import (
    GateDecision,
    LifecycleEvent,
    RunManifest,
    validate_lifecycle_sequence,
)

ARP_SCHEMA_VERSION = "2.0.5"

_CHECKPOINTS = {
    "run.started": "episode.started",
    "corpus.fingerprint.computed": "input.received",
    "drift.detected": "input.received",
    "ingest.started": "tool.completed",
    "ingest.completed": "tool.completed",
    "evaluation.started": "execution.started",
    "retrieval.completed": "retrieval.completed",
    "generation.completed": "artifact.completed",
    "gate.decided": "gate.decided",
    "alert.emitted": "tool.completed",
    "run.completed": "episode.completed",
}


class ArpV2EventLog:
    """Write RAG lifecycle observations as shared ARP v2 events."""

    def __init__(self, path: Path | str, *, experiment_id: str, run_id: str, episode_id: str | None = None) -> None:
        self.path = Path(path)
        self.experiment_id = experiment_id
        self.run_id = run_id
        self.episode_id = episode_id or run_id
        self._sequence = 0
        self._last_event_id: str | None = None

    def emit(self, event_type: str, data: Mapping[str, Any] | None = None, *, parent_event_id: str | None = None) -> LifecycleEvent:
        try:
            checkpoint = _CHECKPOINTS[event_type]
        except KeyError as exc:
            raise ValueError(f"unsupported RAG lifecycle event: {event_type}") from exc
        now = datetime.now(timezone.utc).isoformat()
        attributes = dict(data or {})
        attributes["rag_event_type"] = event_type
        event = LifecycleEvent(
            event_id=str(uuid.uuid4()),
            schema_version=ARP_SCHEMA_VERSION,
            experiment_id=self.experiment_id,
            run_id=self.run_id,
            episode_id=self.episode_id,
            replication_id=0,
            sequence_number=self._sequence,
            checkpoint=checkpoint,
            event_type=checkpoint,
            started_at=now,
            ended_at=now,
            attributes=attributes,
            parent_event_id=parent_event_id or self._last_event_id,
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=True) + "\n")
        self._sequence += 1
        self._last_event_id = event.event_id
        return event


def build_arp_manifest(
    *,
    run_id: str,
    started_at: str,
    decision: GateDecision,
    identifiers: Mapping[str, str],
    hashes: Mapping[str, str],
    metadata: Mapping[str, Any],
    configuration: Mapping[str, Any],
    artifacts: Mapping[str, str],
) -> RunManifest:
    """Construct the neutral manifest while retaining RAG fields under namespaces."""
    rag_metadata = dict(metadata)
    rag_configuration = dict(configuration)
    return RunManifest(
        schema_version=ARP_SCHEMA_VERSION,
        experiment_id="rag-reliability",
        run_id=run_id,
        created_at=started_at,
        git_sha=str(identifiers.get("git_commit", "unavailable")),
        harness_name="rag-reliability-harness",
        harness_version="0.2.0",
        dataset_id="rag-corpus",
        dataset_hash=str(hashes["corpus"]),
        configuration_hash=str(hashes["config"]),
        model_provider="local",
        model_name=str(identifiers.get("model", "unknown")),
        model_version="1",
        random_seed=0,
        replication_count=1,
        environment={"runtime": "python"},
        decision=decision,
        artifacts=dict(artifacts),
        # ``rag`` is the canonical namespace. Flat keys remain a read-only
        # compatibility projection for existing loop/status consumers.
        metadata={"rag": rag_metadata, **rag_metadata, "identifiers": dict(identifiers), "hashes": dict(hashes)},
        configuration={"rag": rag_configuration},
        identifiers=dict(identifiers),
        hashes=dict(hashes),
    )


def read_arp_manifest(path: Path | str) -> RunManifest:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid ARP manifest envelope: expected object")
    required = {"schema_version", "experiment_id", "run_id", "created_at", "decision", "git_sha", "harness_name", "harness_version", "dataset_id", "dataset_hash", "configuration_hash", "model_provider", "model_name", "model_version", "random_seed", "replication_count", "environment"}
    if not required.issubset(payload):
        raise ValueError("invalid ARP manifest envelope: missing required fields")
    if isinstance(payload.get("decision"), dict):
        payload["decision"] = GateDecision.from_dict(payload["decision"])
    try:
        return RunManifest.from_dict(payload)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"invalid ARP manifest envelope: {exc}") from exc


def read_arp_events(path: Path | str, *, run_id: str) -> list[LifecycleEvent]:
    events: list[LifecycleEvent] = []
    for line_number, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
            required = {"event_id", "schema_version", "experiment_id", "run_id", "episode_id", "replication_id", "sequence_number", "checkpoint", "event_type", "started_at", "ended_at", "attributes"}
            if not isinstance(payload, dict) or not required.issubset(payload):
                raise ValueError("missing required fields")
            event = LifecycleEvent.from_dict(payload)
            if event.run_id != run_id:
                raise ValueError(f"run_id mismatch: {event.run_id!r}")
            if event.schema_version != ARP_SCHEMA_VERSION:
                raise ValueError(f"schema_version must be {ARP_SCHEMA_VERSION}")
            if events and event.sequence_number != events[-1].sequence_number + 1:
                raise ValueError("sequence_number must be contiguous")
            events.append(event)
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid ARP lifecycle envelope at line {line_number}: {exc}") from exc
    if events:
        validate_lifecycle_sequence(events)
    return events
