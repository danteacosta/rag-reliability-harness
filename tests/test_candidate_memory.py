from __future__ import annotations

import json

import pytest

from product_memory.candidates import CandidateMemoryStore, MemoryCandidate
from product_memory.ingress import ingest_session_handoff


def test_candidate_memory_requires_provenance_and_review_for_acceptance(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl")
    candidate = MemoryCandidate(
        user_id="u1",
        category="target_company",
        content="Company X",
        confidence=0.8,
        source_refs=[{"kind": "session", "identifier": "s1"}],
    )
    record = store.add(candidate)
    assert record["status"] == "candidate"
    with pytest.raises(ValueError, match="reviewer"):
        store.review(record["candidate_id"], status="accepted")
    accepted = store.review(record["candidate_id"], status="accepted", reviewer="human-1")
    assert accepted["status"] == "accepted"
    assert json.loads((tmp_path / "candidates.jsonl").read_text().splitlines()[-1])["reviewer"] == "human-1"


def test_candidate_memory_rejects_missing_source_refs(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl")
    with pytest.raises(ValueError, match="source_refs"):
        store.add(MemoryCandidate(user_id="u1", category="gap", content="x", confidence=0.5))


def test_retrieve_returns_only_reviewed_candidates_for_matching_category_and_terms(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl")
    target = store.add(
        MemoryCandidate(
            user_id="u1",
            category="target_company",
            content="Target company is Acme",
            confidence=0.9,
            source_refs=[{"kind": "session", "identifier": "s1"}],
        )
    )
    store.add(
        MemoryCandidate(
            user_id="u1",
            category="story_gap",
            content="Needs stronger metrics story",
            confidence=0.8,
            source_refs=[{"kind": "session", "identifier": "s2"}],
        )
    )
    store.review(target["candidate_id"], status="accepted", reviewer="human-1")
    hits = store.retrieve("Acme", category="target_company")
    assert [item["candidate_id"] for item in hits] == [target["candidate_id"]]


def test_session_handoff_ingress_creates_provenanced_candidates_and_retrieval_audit(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl", retention_days=30)
    records = ingest_session_handoff(
        store,
        user_id="user-hash",
        session={
            "session_id_hash": "session-hash",
            "handoff": {
                "decision": "Target Acme platform role",
                "next_step": "Send the recruiter a follow-up",
                "risk": "No quantified impact story",
                "facts": ["Salary floor is 120k"],
            },
        },
    )
    assert {record["category"] for record in records} == {"decision", "next_step", "risk", "fact"}
    assert all(record["source_refs"][0]["identifier"] == "session-hash" for record in records)
    assert all(record["expires_at"] for record in records)
    store.retrieve("Acme", user_id="user-hash")
    audit = store.audit_log()
    assert audit[-1]["action"] == "retrieve"
    assert audit[-1]["user_id"] == "user-hash"


def test_candidate_memory_rejects_unbounded_payload_and_can_delete(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl", max_payload_bytes=300)
    with pytest.raises(ValueError, match="payload"):
        store.add(MemoryCandidate(
            user_id="u1", category="gap", content="x" * 400, confidence=0.5,
            source_refs=[{"kind": "session", "identifier": "s1"}],
        ))
    store = CandidateMemoryStore(tmp_path / "safe.jsonl")
    record = store.add(MemoryCandidate(
        user_id="u1", category="gap", content="x", confidence=0.5,
        source_refs=[{"kind": "session", "identifier": "s1"}],
    ))
    deleted = store.delete(record["candidate_id"], actor="privacy-job", reason="user_request")
    assert deleted["status"] == "deleted"
    assert store.retrieve("x", user_id="u1") == []
