from __future__ import annotations

from rag_harness.types import RetrievalHit

REFUSAL = "INSUFFICIENT_CONTEXT"
REFUSAL_SCORE_THRESHOLD = 0.12


def generate_answer(
    query: str,
    hits: list[RetrievalHit],
    *,
    force_answer: bool = False,
) -> str:
    """Extract an answer from retrieval hits, refusing when confidence is low."""
    if not force_answer and (not hits or hits[0].score < REFUSAL_SCORE_THRESHOLD):
        return REFUSAL

    texts = [hit.text for hit in hits[:2] if hit.text]
    if not texts:
        return REFUSAL if not force_answer else ""

    return " ".join(texts)
