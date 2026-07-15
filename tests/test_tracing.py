from __future__ import annotations

import os

import pytest

from observability.tracing import LangfuseTracer, NoOpTracer, get_tracer
from rag_harness.store.pgvector import NotConfiguredError, PgVectorStore, resolve_dsn


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
