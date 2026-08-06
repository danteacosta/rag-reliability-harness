from __future__ import annotations

import json

import pytest

from product_memory.candidates import CandidateMemoryStore, MemoryCandidate


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
