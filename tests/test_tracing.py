from __future__ import annotations

import os

import pytest

from observability.tracing import LangfuseTracer, NoOpTracer, get_tracer
from rag_harness.store.pgvector import NotConfiguredError, PgVectorStore, resolve_dsn
from rag_harness.types import Chunk


class _FakeCursor:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object | None]] = []
        self.upserted: list[tuple[object, ...]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, params: object | None = None) -> None:
        self.executed.append((sql, params))

    def executemany(self, sql: str, params: list[tuple[object, ...]]) -> None:
        self.executed.append((sql, params))
        self.upserted.extend(params)

    def fetchall(self):
        return [("chunk-1", "alpha beta", {"source": "test"}, 0.875)]

    def fetchone(self):
        return (len(self.upserted),)


class _FakeConnection:
    def __init__(self, cursor: _FakeCursor) -> None:
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def cursor(self) -> _FakeCursor:
        return self._cursor


def test_noop_tracer_records_spans() -> None:
    tracer = NoOpTracer()
    with tracer.span("retrieve", k=5) as span:
        assert span.name == "retrieve"
        assert span.attributes["k"] == 5
    assert len(tracer.spans) == 1
    assert tracer.spans[0].ended_at is not None
    assert tracer.spans[0].duration_ms is not None


def test_langfuse_tracer_noops_without_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    tracer = LangfuseTracer()
    assert tracer.enabled is False
    with tracer.span("generate"):
        pass
    assert len(tracer.spans) == 1


def test_get_tracer_defaults_to_noop(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LANGFUSE_PUBLIC_KEY", raising=False)
    monkeypatch.delenv("LANGFUSE_SECRET_KEY", raising=False)
    assert isinstance(get_tracer(), NoOpTracer)


def test_pgvector_raises_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("PGVECTOR_DSN", raising=False)
    with pytest.raises(NotConfiguredError):
        PgVectorStore()
    with pytest.raises(NotConfiguredError):
        resolve_dsn()


def test_pgvector_accepts_env_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("PGVECTOR_DSN", "postgresql://rag:rag@localhost:5432/rag_harness")
    store = PgVectorStore()
    assert "rag_harness" in store.dsn


def test_pgvector_upserts_and_searches_with_bound_values() -> None:
    cursor = _FakeCursor()
    store = PgVectorStore(
        "postgresql://example",
        connect=lambda _dsn: _FakeConnection(cursor),
    )

    store.upsert([Chunk("chunk-1", "doc-1", "alpha beta", {"source": "test"})])
    hits = store.similarity_search("alpha", k=3)

    assert cursor.upserted[0][:4] == (
        "chunk-1",
        "doc-1",
        "alpha beta",
        '{"source": "test"}',
    )
    search_sql, search_params = next(
        item for item in cursor.executed if "ORDER BY embedding" in item[0]
    )
    assert "%s::vector" in search_sql
    assert search_params is not None and search_params[-1] == 3
    assert hits[0].chunk_id == "chunk-1"
    assert hits[0].score == pytest.approx(0.875)
    assert hits[0].metadata == {"source": "test"}


def test_pgvector_rejects_unsafe_table_identifier() -> None:
    with pytest.raises(ValueError, match="identifier"):
        PgVectorStore("postgresql://example", table="chunks; DROP TABLE chunks")


@pytest.mark.skipif(
    not os.environ.get("PGVECTOR_TEST_DSN"),
    reason="requires the disposable CI pgvector service",
)
def test_pgvector_round_trip_against_disposable_database() -> None:
    store = PgVectorStore(
        os.environ["PGVECTOR_TEST_DSN"],
        table="rag_chunks_acceptance",
    )
    store.upsert(
        [
            Chunk("chunk-alpha", "doc-1", "alpha beta gamma", {"rank": 1}),
            Chunk("chunk-zulu", "doc-2", "zulu yankee xray", {"rank": 2}),
        ]
    )

    hits = store.similarity_search("alpha beta", k=1)

    assert hits[0].chunk_id == "chunk-alpha"
    assert hits[0].metadata == {"rank": 1}
    assert store.health() == {
        "status": "ok",
        "backend": "pgvector",
        "chunk_count": 2,
    }
