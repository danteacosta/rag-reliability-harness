from rag_harness.types import RetrievalHit

from retrieval.generate import generate_answer


def test_generate_refuses_when_scores_low():
    hits = [RetrievalHit(chunk_id="x", score=0.01, text="unrelated", metadata={})]
    assert generate_answer("pricing of Acme Cloud?", hits) == "INSUFFICIENT_CONTEXT"


def test_generate_extracts_from_top_hit():
    hits = [
        RetrievalHit(
            chunk_id="b",
            score=0.9,
            text="Default request timeout is 60 seconds.",
            metadata={},
        )
    ]
    ans = generate_answer("What is the default request timeout?", hits)
    assert "60" in ans
    assert ans != "INSUFFICIENT_CONTEXT"
