"""Offline precision/recall evaluation for reviewed candidate retrieval."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from product_memory.candidates import CandidateMemoryStore


def evaluate_retrieval(
    store: CandidateMemoryStore,
    cases: Iterable[Mapping[str, Any]],
    *,
    limit: int = 5,
) -> dict[str, float | int]:
    rows = list(cases)
    if limit <= 0:
        raise ValueError("limit must be positive")
    if not rows:
        return {"cases": 0, "precision_at_k": 0.0, "recall_at_k": 0.0}
    precisions: list[float] = []
    recalls: list[float] = []
    for case in rows:
        relevant = {str(value) for value in case.get("relevant_candidate_ids", [])}
        retrieved = store.retrieve(
            str(case.get("query", "")),
            user_id=str(case["user_id"]) if case.get("user_id") is not None else None,
            category=str(case["category"]) if case.get("category") is not None else None,
            limit=limit,
        )
        retrieved_ids = [str(row["candidate_id"]) for row in retrieved]
        hits = len(set(retrieved_ids) & relevant)
        precisions.append(hits / len(retrieved_ids) if retrieved_ids else 0.0)
        recalls.append(hits / len(relevant) if relevant else 0.0)
    return {
        "cases": len(rows),
        "precision_at_k": sum(precisions) / len(precisions),
        "recall_at_k": sum(recalls) / len(recalls),
    }


__all__ = ("evaluate_retrieval",)
