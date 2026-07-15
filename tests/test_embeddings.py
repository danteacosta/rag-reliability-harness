import json
import os
import subprocess
import sys

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


def test_separate_instances_produce_identical_vectors():
    a = HashEmbedder(dim=256)
    b = HashEmbedder(dim=256)
    assert (a.embed("request timeout") == b.embed("request timeout")).all()


def test_embed_stable_across_python_hash_seeds():
    """Cross-process stability for CI baselines (independent of PYTHONHASHSEED)."""
    text = "default request timeout seconds"
    script = (
        "import json, sys\n"
        "from rag_harness.embeddings.hash_embedder import HashEmbedder\n"
        "print(json.dumps(HashEmbedder(dim=256).embed(sys.argv[1]).tolist()))\n"
    )
    vectors = []
    for seed in ("0", "1", "42"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.check_output(
            [sys.executable, "-c", script, text],
            env=env,
            cwd=os.path.dirname(os.path.dirname(__file__)),
        )
        vectors.append(json.loads(out))
    assert vectors[0] == vectors[1] == vectors[2]
