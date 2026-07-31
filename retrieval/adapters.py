"""Stable retrieval and generation interfaces around the local RAG components."""

from __future__ import annotations

from typing import Callable, Mapping, Protocol

from rag_harness.types import RetrievalHit
from retrieval.generate import generate_answer
from retrieval.retriever import HarnessRetriever


class RetrievalAdapter(Protocol):
    def retrieve(self, query: str) -> list[RetrievalHit]: ...


class GeneratorAdapter(Protocol):
    def generate(self, query: str, hits: list[RetrievalHit]) -> str: ...


class HarnessRetrievalAdapter:
    """Adapter from the LangChain retriever boundary to plain retrieval hits."""

    def __init__(self, retriever: HarnessRetriever) -> None:
        self._retriever = retriever

    def retrieve(self, query: str) -> list[RetrievalHit]:
        return [_document_to_hit(document) for document in self._retriever.invoke(query)]


class ExtractiveGenerator:
    """Adapter exposing the local extractive generator through GeneratorAdapter."""

    def generate(self, query: str, hits: list[RetrievalHit]) -> str:
        return generate_answer(query, hits)


ExtractiveGeneratorAdapter = ExtractiveGenerator


class ReplayGenerator:
    """Deterministic generator for recorded answers and CI replay."""

    def __init__(self, answers: Mapping[str, str]) -> None:
        self._answers = dict(answers)

    def generate(self, query: str, hits: list[RetrievalHit]) -> str:
        return self._answers.get(query, "INSUFFICIENT_CONTEXT")


class LLMGenerator:
    """Optional live generator; without an injected callable it safely refuses."""

    def __init__(self, complete: Callable[[str, list[RetrievalHit]], str] | None = None) -> None:
        self._complete = complete

    def generate(self, query: str, hits: list[RetrievalHit]) -> str:
        return self._complete(query, hits) if self._complete is not None else "INSUFFICIENT_CONTEXT"


def _document_to_hit(document: object) -> RetrievalHit:
    metadata = dict(getattr(document, "metadata", None) or {})
    return RetrievalHit(
        chunk_id=str(metadata.pop("chunk_id", "")),
        score=float(metadata.pop("score", 0.0)),
        text=str(getattr(document, "page_content", "")),
        metadata=metadata,
    )
