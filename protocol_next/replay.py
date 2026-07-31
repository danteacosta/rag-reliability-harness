"""Manifest validation and lifecycle replay without domain dependencies."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from agent_reliability_protocol import RunManifest as SharedRunManifest
from rag_harness.reliability import RunManifest as RagRunManifest
from protocol_next.events import collect_lifecycle_events


def replay_manifest(path: Path | str, *, reexecute: bool = False) -> dict[str, Any]:
    """Validate lifecycle evidence and optionally re-execute a standalone RAG run."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if "manifest" in payload:
        payload = payload["manifest"]
    is_rag_manifest = payload.get("rag_schema_version") == "rag-reliability/v1" or payload.get("schema_version") == "rag-reliability/v1"
    manifest = RagRunManifest.from_dict(payload) if is_rag_manifest else SharedRunManifest.from_dict(payload)
    manifest_root = Path(path).parent
    events_path = manifest.artifacts.get("events")
    if events_path and not Path(events_path).is_absolute():
        events_path = str(manifest_root / events_path)
    events = collect_lifecycle_events(events_path, run_id=manifest.run_id) if events_path else []
    if events:
        _validate_lifecycle(events, manifest)
    report = {
        "run_id": manifest.run_id,
        "outcome": manifest.decision.outcome,
        "events": len(events),
    }
    if reexecute:
        if not is_rag_manifest:
            raise ValueError("only standalone RAG manifests can be re-executed")
        from loop.run import run_closed_loop

        config = manifest.configuration
        def resolve(name: str) -> str:
            candidate = Path(str(config[name]))
            return str(candidate if candidate.is_absolute() else manifest_root / candidate)
        result = run_closed_loop(
            corpus_root=resolve("corpus_root"), golden_path=resolve("golden_path"), online_path=resolve("online_path"),
            thresholds_path=resolve("thresholds_path"), baseline_path=resolve("baseline_path"),
            runs_root=Path(path).parent / "replays", force_reingest=True,
        )
        report["reexecution"] = {"run_id": result["manifest"]["run_id"], "decision": result["decision"]["decision"]}
    return report


def _validate_lifecycle(events: list[Any], manifest: RunManifest) -> None:
    event_types = [event.type for event in events]
    required = ["run.started", "gate.decided", "run.completed"]
    if any(event_type not in event_types for event_type in required):
        raise ValueError("lifecycle stream is missing required events")
    if isinstance(manifest, RagRunManifest):
        seen: set[str] = set()
        for event in events:
            if not event.event_id or event.event_id in seen:
                raise ValueError("RAG lifecycle events require unique event IDs")
            if event.parent_event_id and event.parent_event_id not in seen:
                raise ValueError("RAG lifecycle parent must precede and reference an existing event")
            seen.add(event.event_id)
    gate = next(event for event in events if event.type == "gate.decided")
    completed = next(event for event in reversed(events) if event.type == "run.completed")
    # Legacy lifecycle streams encode outcome=pass/fail; v2 streams encode
    # decision=approve/warn/block. Compare like-for-like at the event boundary.
    use_legacy_outcome = any("outcome" in event.data for event in (gate, completed))
    expected = manifest.decision.outcome if use_legacy_outcome else manifest.decision.decision
    actual_gate = gate.data.get("outcome") if use_legacy_outcome else gate.data.get("decision")
    actual_completed = completed.data.get("outcome") if use_legacy_outcome else completed.data.get("decision")
    if actual_gate != expected or actual_completed != expected:
        raise ValueError("lifecycle decision does not match manifest")
