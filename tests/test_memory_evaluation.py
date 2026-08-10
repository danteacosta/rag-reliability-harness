from product_memory.candidates import CandidateMemoryStore, MemoryCandidate
from product_memory.evaluation import evaluate_retrieval


def test_memory_retrieval_evaluation_reports_precision_and_recall(tmp_path):
    store = CandidateMemoryStore(tmp_path / "candidates.jsonl")
    target = store.add(
        MemoryCandidate(
            user_id="u1",
            category="target_company",
            content="Acme role",
            confidence=0.9,
            source_refs=[{"kind": "session", "identifier": "s1"}],
        )
    )
    store.review(target["candidate_id"], status="accepted", reviewer="reviewer-1")

    report = evaluate_retrieval(
        store,
        [
            {
                "query": "Acme",
                "user_id": "u1",
                "category": "target_company",
                "relevant_candidate_ids": [target["candidate_id"]],
            }
        ],
    )

    assert report["cases"] == 1
    assert report["precision_at_k"] == 1.0
    assert report["recall_at_k"] == 1.0
