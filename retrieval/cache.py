from __future__ import annotations

from rag_harness.types import RetrievalHit


class QueryCache:
    """In-memory cache keyed by exact rewritten query string."""

    def __init__(self) -> None:
        self._store: dict[str, list[RetrievalHit]] = {}

    def get(self, query: str) -> list[RetrievalHit] | None:
        return self._store.get(query)

    def set(self, query: str, hits: list[RetrievalHit]) -> None:
        self._store[query] = list(hits)

    def clear(self) -> None:
        self._store.clear()
