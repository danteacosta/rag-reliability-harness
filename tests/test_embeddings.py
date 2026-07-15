from rag_harness.embeddings.hash_embedder import HashEmbedder


def test_similar_text_ranks_higher_than_unrelated():
    emb = HashEmbedder(dim=256)
    q = emb.embed("default request timeout seconds")
    near = emb.embed("The default request timeout is 60 seconds.")
    far = emb.embed("OAuth2 password flow with JWT tokens")
    assert emb.cosine(q, near) > emb.cosine(q, far)


def test_embed_is_deterministic():
    emb = HashEmbedder(dim=256)
    assert (emb.embed("abc") == emb.embed("abc")).all()
