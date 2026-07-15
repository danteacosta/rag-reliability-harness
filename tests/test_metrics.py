from eval.metrics import (
    aggregate_retrieval_metrics,
    drift_ok,
    groundedness,
    mrr,
    precision_at_k,
    recall_at_k,
    refusal_accuracy,
)


def test_recall_at_k():
    assert recall_at_k(["a", "b"], ["b", "c", "d"], k=2) == 0.5


def test_precision_at_k():
    assert precision_at_k(["a", "x"], ["a", "b"], k=2) == 0.5


def test_mrr():
    assert mrr(["x", "a"], ["a"]) == 0.5


def test_retrieval_metrics_skip_empty_relevant():
    items = [
        {"relevant_chunk_ids": [], "retrieved": ["a"]},
        {"relevant_chunk_ids": ["a"], "retrieved": ["a", "b"]},
    ]
    m = aggregate_retrieval_metrics(items, k=2)
    assert m["recall@2"] == 1.0


def test_refusal_accuracy():
    assert (
        refusal_accuracy(
            [
                {"relevant_chunk_ids": [], "answer": "INSUFFICIENT_CONTEXT"},
                {"relevant_chunk_ids": [], "answer": "something made up"},
            ]
        )
        == 0.5
    )


def test_groundedness_refusal_is_grounded():
    assert groundedness("INSUFFICIENT_CONTEXT", contexts=["x"]) == 1.0


def test_groundedness_lexical_containment():
    assert (
        groundedness(
            "timeout is 60 seconds",
            contexts=["Default request timeout is 60 seconds."],
        )
        == 1.0
    )
    assert (
        groundedness(
            "timeout is 99 hours",
            contexts=["Default request timeout is 60 seconds."],
        )
        < 1.0
    )


def test_drift_match():
    assert drift_ok(active_fp="abc", expected_fp="abc") is True
    assert drift_ok(active_fp="abc", expected_fp="xyz") is False
