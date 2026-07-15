from __future__ import annotations

from typing import Any

from pydantic import Field

from langchain_core.callbacks import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever

from rag_harness.embeddings.hash_embedder import HashEmbedder
from rag_harness.store.memory import InMemoryVectorStore
from rag_harness.types import Chunk, RetrievalHit

from retrieval.cache import QueryCache
from retrieval.rewrite import rewrite

DEFAULT_K = 5


class HarnessRetriever(BaseRetriever):
    """LangChain retriever that rewrites queries and searches a vector store."""

    store: InMemoryVectorStore
    k: int = DEFAULT_K
    cache: QueryCache = Field(default_factory=QueryCache)

    def _get_relevant_documents(
        self,
        query: str,
        *,
        run_manager: CallbackManagerForRetrieverRun | None = None,
    ) -> list[Document]:
        rewritten = rewrite(query)

        hits = self.cache.get(rewritten)
        if hits is None:
            hits = self.store.similarity_search(rewritten, k=self.k)
            self.cache.set(rewritten, hits)

        return [_hit_to_document(hit) for hit in hits]


def _hit_to_document(hit: RetrievalHit) -> Document:
    metadata: dict[str, Any] = {
        "chunk_id": hit.chunk_id,
        "score": hit.score,
        **hit.metadata,
    }
    return Document(page_content=hit.text, metadata=metadata)


def build_test_retriever() -> HarnessRetriever:
    """Build a retriever preloaded with timeout fixture data for tests."""
    embedder = HashEmbedder()
    store = InMemoryVectorStore(embedder)
    store.upsert(
        [
            Chunk(
                id="b",
                doc_id="d2",
                text="Default request timeout is 60 seconds",
                metadata={},
            ),
        ]
    )
    return HarnessRetriever(store=store)
