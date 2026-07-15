from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class GoldenItem:
    id: str
    question: str
    answer: str
    relevant_chunk_ids: list[str]
    failure_mode: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> GoldenItem:
        return cls(
            id=data["id"],
            question=data["question"],
            answer=data["answer"],
            relevant_chunk_ids=list(data["relevant_chunk_ids"]),
            failure_mode=data["failure_mode"],
        )


@dataclass(frozen=True)
class Chunk:
    id: str
    doc_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Chunk:
        return cls(
            id=data["id"],
            doc_id=data["doc_id"],
            text=data["text"],
            metadata=dict(data.get("metadata") or {}),
        )


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    score: float
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrievalHit:
        return cls(
            chunk_id=data["chunk_id"],
            score=float(data["score"]),
            text=data["text"],
            metadata=dict(data.get("metadata") or {}),
        )
