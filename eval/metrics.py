from __future__ import annotations

import re
from typing import Any, Iterable

from retrieval.generate import REFUSAL

_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def recall_at_k(retrieved: list[str], relevant: list[str], *, k: int) -> float:
    if not relevant or k <= 0:
        return 0.0
    top = set(retrieved[:k])
    hits = sum(1 for r in relevant if r in top)
    return hits / min(k, len(relevant))


def precision_at_k(retrieved: list[str], relevant: list[str], *, k: int) -> float:
    if k <= 0:
        return 0.0
    top = retrieved[:k]
    if not top:
        return 0.0
    relevant_set = set(relevant)
    hits = sum(1 for item in top if item in relevant_set)
    return hits / k


def mrr(retrieved: list[str], relevant: list[str]) -> float:
    relevant_set = set(relevant)
    for rank, item in enumerate(retrieved, start=1):
        if item in relevant_set:
            return 1.0 / rank
    return 0.0


def aggregate_retrieval_metrics(
    items: Iterable[dict[str, Any]],
    *,
    k: int,
) -> dict[str, float]:
    recalls: list[float] = []
    precisions: list[float] = []
    mrrs: list[float] = []

    for item in items:
        relevant = list(item.get("relevant_chunk_ids") or [])
        if not relevant:
            continue
        retrieved = list(item.get("retrieved") or [])
        recalls.append(recall_at_k(retrieved, relevant, k=k))
        precisions.append(precision_at_k(retrieved, relevant, k=k))
        mrrs.append(mrr(retrieved, relevant))

    n = len(recalls)
    if n == 0:
        return {f"recall@{k}": 0.0, f"precision@{k}": 0.0, "mrr": 0.0}

    return {
        f"recall@{k}": sum(recalls) / n,
        f"precision@{k}": sum(precisions) / n,
        "mrr": sum(mrrs) / n,
    }


def refusal_accuracy(items: Iterable[dict[str, Any]]) -> float:
    cohort = [
        item
        for item in items
        if not list(item.get("relevant_chunk_ids") or [])
    ]
    if not cohort:
        return 0.0
    correct = sum(1 for item in cohort if item.get("answer") == REFUSAL)
    return correct / len(cohort)


def groundedness(answer: str, *, contexts: list[str]) -> float:
    if answer == REFUSAL:
        return 1.0
    answer_tokens = _tokenize(answer)
    if not answer_tokens:
        return 1.0
    context_tokens = set(_tokenize(" ".join(contexts)))
    if not context_tokens:
        return 0.0
    supported = sum(1 for token in answer_tokens if token in context_tokens)
    return supported / len(answer_tokens)


def drift_ok(*, active_fp: str, expected_fp: str) -> bool:
    return active_fp == expected_fp


def _tokenize(text: str) -> list[str]:
    return [m.group(0).lower() for m in _TOKEN_RE.finditer(text)]
