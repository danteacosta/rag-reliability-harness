from rag_harness.types import RetrievalHit

from retrieval.generate import generate_answer


def test_generate_refuses_when_scores_low():
    hits = [RetrievalHit(chunk_id="x", score=0.01, text="unrelated", metadata={})]
    assert generate_answer("pricing of Acme Cloud?", hits) == "INSUFFICIENT_CONTEXT"


def test_generate_refuses_high_score_without_content_overlap():
    hits = [
        RetrievalHit(
            chunk_id="x",
            score=0.58,
            text="Middleware records elapsed time after awaiting call_next.",
            metadata={},
        )
    ]
    assert (
        generate_answer("What is the list price of Acme Cloud Enterprise?", hits)
        == "INSUFFICIENT_CONTEXT"
    )


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
