from __future__ import annotations

from rag_harness.reliability import RetrievalStore
from typing import Protocol, Sequence

from rag_harness.types import Chunk, RetrievalHit


class VectorStore(Protocol):
    def upsert(self, chunks: Sequence[Chunk]) -> None: ...

    def similarity_search(self, query: str, k: int = 5) -> list[RetrievalHit]: ...


__all__ = ["RetrievalStore", "VectorStore"]
