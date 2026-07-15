from __future__ import annotations

from typing import Protocol, Sequence

from rag_harness.types import Chunk, RetrievalHit


class VectorStore(Protocol):
    def upsert(self, chunks: Sequence[Chunk]) -> None: ...

    def similarity_search(self, query: str, k: int = 5) -> list[RetrievalHit]: ...
