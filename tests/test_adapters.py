from __future__ import annotations

from rag_harness.types import RetrievalHit
from retrieval.adapters import ExtractiveGeneratorAdapter, HarnessRetrievalAdapter
from retrieval.retriever import build_test_retriever


def test_retrieval_and_generator_adapters_expose_provider_neutral_operations() -> None:
    retriever = HarnessRetrievalAdapter(build_test_retriever())
    generator = ExtractiveGeneratorAdapter()

    hits = retriever.retrieve("What is the request timeout?")
    answer = generator.generate("What is the request timeout?", hits)

    assert hits and isinstance(hits[0], RetrievalHit)
    assert "60 seconds" in answer
