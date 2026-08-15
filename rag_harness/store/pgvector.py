"""Optional persistent pgvector adapter with deterministic local embeddings."""

from __future__ import annotations

import os
import json
import re
from collections.abc import Callable, Sequence
from typing import Any

from rag_harness.embeddings.hash_embedder import HashEmbedder
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
    """Persistent implementation of the same contract as the memory store.

    Construction validates configuration but defers all network I/O until an
    operation. SQL identifiers are allowlisted and all values are bound
    parameters. The optional ``.[pgvector]`` extra supplies psycopg.
    """

    def __init__(
        self,
        dsn: str | None = None,
        *,
        embedder: HashEmbedder | None = None,
        table: str = "rag_chunks",
        connect: Callable[[str], Any] | None = None,
    ) -> None:
        self._dsn = resolve_dsn(dsn)
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,62}", table):
            raise ValueError("pgvector table must be a simple PostgreSQL identifier")
        self._table = table
        self._embedder = embedder or HashEmbedder()
        self._connect_override = connect

    @property
    def dsn(self) -> str:
        return self._dsn

    def upsert(self, chunks: Sequence[Chunk]) -> None:
        if not chunks:
            return
        rows = [
            (
                chunk.id,
                chunk.doc_id,
                chunk.text,
                json.dumps(chunk.metadata, sort_keys=True),
                _vector_literal(self._embedder.embed(chunk.text)),
            )
            for chunk in chunks
        ]
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                cursor.executemany(
                    f"""INSERT INTO {self._table}
                    (chunk_id, doc_id, text_content, metadata, embedding)
                    VALUES (%s, %s, %s, %s::jsonb, %s::vector)
                    ON CONFLICT (chunk_id) DO UPDATE SET
                      doc_id = EXCLUDED.doc_id,
                      text_content = EXCLUDED.text_content,
                      metadata = EXCLUDED.metadata,
                      embedding = EXCLUDED.embedding""",
                    rows,
                )

    def similarity_search(self, query: str, k: int = 5) -> list[RetrievalHit]:
        if k <= 0:
            return []
        vector = _vector_literal(self._embedder.embed(query))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                cursor.execute(
                    f"""SELECT chunk_id, text_content, metadata,
                    1 - (embedding <=> %s::vector) AS score
                    FROM {self._table}
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s""",
                    (vector, vector, k),
                )
                rows = cursor.fetchall()
        return [
            RetrievalHit(
                chunk_id=str(chunk_id),
                text=str(text),
                score=float(score),
                metadata=(json.loads(metadata) if isinstance(metadata, str) else dict(metadata or {})),
            )
            for chunk_id, text, metadata, score in rows
        ]

    def health(self) -> dict[str, int | str]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                cursor.execute(f"SELECT COUNT(*) FROM {self._table}")
                row = cursor.fetchone()
        return {
            "status": "ok",
            "backend": "pgvector",
            "chunk_count": int(row[0] if row else 0),
        }

    def _connect(self) -> Any:
        if self._connect_override is not None:
            return self._connect_override(self._dsn)
        try:
            import psycopg
        except ImportError as exc:
            raise NotConfiguredError(
                "PgVectorStore requires the optional dependency: pip install -e '.[pgvector]'"
            ) from exc
        return psycopg.connect(self._dsn)

    def _ensure_schema(self, cursor: Any) -> None:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            f"""CREATE TABLE IF NOT EXISTS {self._table} (
              chunk_id TEXT PRIMARY KEY,
              doc_id TEXT NOT NULL,
              text_content TEXT NOT NULL,
              metadata JSONB NOT NULL DEFAULT '{{}}'::jsonb,
              embedding VECTOR({self._embedder.dim}) NOT NULL
            )"""
        )


def _vector_literal(vector: Sequence[float]) -> str:
    return "[" + ",".join(format(float(value), ".17g") for value in vector) + "]"
