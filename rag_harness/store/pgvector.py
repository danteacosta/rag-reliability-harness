"""Optional pgvector adapter. Not used in CI; requires a configured DSN."""

from __future__ import annotations

import os
from typing import Sequence

from rag_harness.types import Chunk, RetrievalHit


class NotConfiguredError(RuntimeError):
    """Raised when pgvector is used without DATABASE_URL / PGVECTOR_DSN."""


def resolve_dsn(dsn: str | None = None) -> str:
    """Resolve DSN from argument or environment.

    Checks ``DATABASE_URL`` then ``PGVECTOR_DSN``.
    """
    resolved = dsn or os.environ.get("DATABASE_URL") or os.environ.get("PGVECTOR_DSN")
    if not resolved:
        raise NotConfiguredError(
            "pgvector requires DATABASE_URL or PGVECTOR_DSN. "
            "Copy .env.example, set a DSN, and start docker-compose (pgvector image) for a local demo."
        )
    return resolved


class PgVectorStore:
    """Thin optional adapter behind the VectorStore protocol.

    Construction requires a DSN. Actual SQL I/O is deferred until upsert/search
    and needs the optional ``.[pgvector]`` extra (psycopg) plus a running Postgres.
    """

    def __init__(self, dsn: str | None = None) -> None:
        self._dsn = resolve_dsn(dsn)

    @property
    def dsn(self) -> str:
        return self._dsn

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        raise NotImplementedError(
            "PgVectorStore.upsert needs a running Postgres+pgvector instance. "
            "Use InMemoryVectorStore for CI/offline, or implement SQL upsert against self.dsn."
        )

    def similarity_search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        raise NotImplementedError(
            "PgVectorStore.similarity_search needs a running Postgres+pgvector instance. "
            "Use InMemoryVectorStore for CI/offline."
        )
