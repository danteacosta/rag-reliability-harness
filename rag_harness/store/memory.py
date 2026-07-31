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

    def index(self, chunks: Sequence[Chunk], *, namespace: str = "default") -> None:
        """Index chunks under a removable namespace."""
        namespaced = [
            Chunk(chunk.id, chunk.doc_id, chunk.text, {**chunk.metadata, "namespace": namespace})
            for chunk in chunks
        ]
        self.upsert(namespaced)

    def retrieve(self, query: str, *, k: int = 5, namespace: str = "default") -> list[RetrievalHit]:
        return [hit for hit in self.similarity_search(query, k=len(self._chunks)) if hit.metadata.get("namespace", "default") == namespace][:k]

    def delete_namespace(self, namespace: str) -> None:
        for chunk_id, chunk in list(self._chunks.items()):
            if chunk.metadata.get("namespace", "default") == namespace:
                del self._chunks[chunk_id]
                del self._vectors[chunk_id]

    def health(self) -> dict[str, int | str]:
        return {"status": "ok", "backend": "memory", "chunk_count": len(self._chunks)}

    @classmethod
    def from_vectors(
        cls,
        embedder: HashEmbedder,
        chunks: dict[str, Chunk],
        vectors: dict[str, np.ndarray],
    ) -> InMemoryVectorStore:
        store = cls(embedder)
        store._chunks = dict(chunks)
        store._vectors = {chunk_id: np.asarray(vec, dtype=np.float64) for chunk_id, vec in vectors.items()}
        return store

    def export_vectors(self) -> dict[str, np.ndarray]:
        return dict(self._vectors)

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
