"""Stable retrieval and generation interfaces around the local RAG components."""

from __future__ import annotations

from typing import Protocol

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


class ExtractiveGeneratorAdapter:
    """Adapter exposing the local extractive generator through GeneratorAdapter."""

    def generate(self, query: str, hits: list[RetrievalHit]) -> str:
        return generate_answer(query, hits)


def _document_to_hit(document: object) -> RetrievalHit:
    metadata = dict(getattr(document, "metadata", None) or {})
    return RetrievalHit(
        chunk_id=str(metadata.pop("chunk_id", "")),
        score=float(metadata.pop("score", 0.0)),
        text=str(getattr(document, "page_content", "")),
        metadata=metadata,
    )
