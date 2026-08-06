"""Session-handoff ingress into provenance-first memory candidates."""

from __future__ import annotations

from typing import Any

from product_memory.candidates import CandidateMemoryStore, MemoryCandidate


def ingest_session_handoff(
    store: CandidateMemoryStore,
    *,
    user_id: str,
    session: dict[str, Any],
) -> list[dict[str, Any]]:
    session_id = str(session.get("session_id_hash", "")).strip()
    handoff = session.get("handoff")
    if not session_id:
        raise ValueError("session_id_hash is required")
    if not isinstance(handoff, dict):
        return []
    source = [{"kind": "session", "identifier": session_id}]
    records: list[dict[str, Any]] = []
    for field, category in (("decision", "decision"), ("next_step", "next_step"), ("risk", "risk")):
        value = handoff.get(field)
        if isinstance(value, str) and value.strip():
            records.append(store.add(MemoryCandidate(user_id, category, value.strip(), 0.6, source)))
    facts = handoff.get("facts", [])
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, str) and fact.strip():
                records.append(store.add(MemoryCandidate(user_id, "fact", fact.strip(), 0.5, source)))
    return records
