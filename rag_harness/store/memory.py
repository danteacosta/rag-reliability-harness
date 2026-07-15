from __future__ import annotations

from typing import Sequence

import numpy as np

from rag_harness.embeddings.hash_embedder import HashEmbedder
from rag_harness.types import Chunk, RetrievalHit


class InMemoryVectorStore:
    """In-memory vector store backed by a HashEmbedder."""

    def __init__(self, embedder: HashEmbedder) -> None:
        self._embedder = embedder
        self._chunks: dict[str, Chunk] = {}
        self._vectors: dict[str, np.ndarray] = {}

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        for chunk in chunks:
            self._chunks[chunk.id] = chunk
            self._vectors[chunk.id] = self._embedder.embed(chunk.text)

    def similarity_search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        if not self._chunks or k <= 0:
            return []

        query_vec = self._embedder.embed(query)
        scored: list[tuple[str, float]] = []
        for chunk_id, vec in self._vectors.items():
            score = self._embedder.cosine(query_vec, vec)
            scored.append((chunk_id, score))

        scored.sort(key=lambda item: item[1], reverse=True)
        hits: list[RetrievalHit] = []
        for chunk_id, score in scored[:k]:
            chunk = self._chunks[chunk_id]
            hits.append(
                RetrievalHit(
                    chunk_id=chunk.id,
                    score=score,
                    text=chunk.text,
                    metadata=dict(chunk.metadata),
                )
            )
        return hits
