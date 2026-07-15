"""Tracing stubs: in-memory no-op tracer and optional Langfuse adapter."""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, Iterator


@dataclass
class SpanRecord:
    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    started_at: float = 0.0
    ended_at: float | None = None

    @property
    def duration_ms(self) -> float | None:
        if self.ended_at is None:
            return None
        return (self.ended_at - self.started_at) * 1000.0


class NoOpTracer:
    """Records spans in a list for tests; never sends telemetry."""

    def __init__(self) -> None:
        self.spans: list[SpanRecord] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        record = SpanRecord(name=name, attributes=dict(attributes), started_at=time.perf_counter())
        self.spans.append(record)
        try:
            yield record
        finally:
            record.ended_at = time.perf_counter()


class LangfuseTracer:
    """Langfuse adapter that no-ops unless LANGFUSE_* credentials are set."""

    def __init__(
        self,
        *,
        public_key: str | None = None,
        secret_key: str | None = None,
        host: str | None = None,
    ) -> None:
        self.public_key = public_key or os.environ.get("LANGFUSE_PUBLIC_KEY", "")
        self.secret_key = secret_key or os.environ.get("LANGFUSE_SECRET_KEY", "")
        self.host = host or os.environ.get("LANGFUSE_HOST", "https://cloud.langfuse.com")
        self.enabled = bool(self.public_key and self.secret_key)
        self.spans: list[SpanRecord] = []
        self._client: Any | None = None
        if self.enabled:
            self._client = self._try_create_client()

    def _try_create_client(self) -> Any | None:
        """Best-effort Langfuse client; stay silent if the SDK is not installed."""
        try:
            from langfuse import Langfuse  # type: ignore[import-not-found]
        except ImportError:
            return None
        return Langfuse(
            public_key=self.public_key,
            secret_key=self.secret_key,
            host=self.host,
        )

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[SpanRecord]:
        record = SpanRecord(name=name, attributes=dict(attributes), started_at=time.perf_counter())
        self.spans.append(record)
        # Without credentials (or without the SDK), behave like NoOpTracer.
        try:
            yield record
        finally:
            record.ended_at = time.perf_counter()
            if self._client is not None:
                try:
                    self._client.trace(name=name, metadata=dict(attributes))
                except Exception:
                    # Never break the app path for optional observability.
                    pass


def get_tracer(*, prefer_langfuse: bool = True) -> NoOpTracer | LangfuseTracer:
    """Return LangfuseTracer when keys exist; otherwise NoOpTracer."""
    if prefer_langfuse and os.environ.get("LANGFUSE_PUBLIC_KEY") and os.environ.get(
        "LANGFUSE_SECRET_KEY"
    ):
        return LangfuseTracer()
    return NoOpTracer()
