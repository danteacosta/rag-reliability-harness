from rag_harness.embeddings.hash_embedder import HashEmbedder
from rag_harness.store.memory import InMemoryVectorStore
from rag_harness.types import Chunk


def test_topk_returns_lexical_match_first():
    emb = HashEmbedder()
    store = InMemoryVectorStore(emb)
    store.upsert(
        [
            Chunk(id="a", doc_id="d1", text="OAuth2 password flow", metadata={}),
            Chunk(id="b", doc_id="d2", text="Default request timeout is 60 seconds", metadata={}),
        ]
    )
    hits = store.similarity_search("request timeout", k=2)
    assert hits[0].chunk_id == "b"
