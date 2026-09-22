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
    assert recall_at_k(["a", "b"], ["b", "c", "d"], k=2) == 1/3


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


def test_recall_counts_all_unique_relevant_documents():
    assert recall_at_k(list('abcde'), list('abcdefghijklmnopqrst'), k=5) == 0.25
    assert recall_at_k(['a'], ['a', 'a', 'b'], k=5) == 0.5


def test_duplicate_hits_consume_rank_without_extra_credit():
    from math import log2
    from eval.metrics import ndcg_at_k
    assert precision_at_k(['a', 'a'], ['a'], k=2) == 0.5
    assert ndcg_at_k(['a'] * 5, ['a'], k=5) == 1.0
    assert ndcg_at_k(['a', 'a', 'b'], ['a', 'b', 'b'], k=3) == (1 + 1/log2(4))/(1 + 1/log2(3))


def test_duplicate_metric_bounds_exhaustively():
    from itertools import product
    from eval.metrics import ndcg_at_k
    for length in range(5):
        for ranking in product('abx', repeat=length):
            for relevant in ([], ['a'], ['a', 'a'], ['a', 'b', 'b']):
                for k in range(1, 5):
                    for metric in (recall_at_k, precision_at_k, ndcg_at_k):
                        assert 0 <= metric(list(ranking), relevant, k=k) <= 1
