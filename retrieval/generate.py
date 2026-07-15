from __future__ import annotations

import re

from rag_harness.types import RetrievalHit

REFUSAL = "INSUFFICIENT_CONTEXT"
# Plan locked 0.12 as a cosine starting point. HashEmbedder scores on this corpus
# land ~0.52–0.80 for answerable queries and ~0.57–0.59 for unsupported ones
# (overlapping), so 0.12 never refuses. Floor calibrated below the answerable
# minimum; unsupported queries in the overlapping band are refused via the
# content-word overlap check below.
REFUSAL_SCORE_THRESHOLD = 0.50

_CONTENT_TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)


def generate_answer(
    query: str,
    hits: list[RetrievalHit],
    *,
    force_answer: bool = False,
) -> str:
    """Extract an answer from retrieval hits, refusing when confidence is low."""
    if not force_answer and (
        not hits
        or hits[0].score < REFUSAL_SCORE_THRESHOLD
        or not _shares_content_words(query, hits[0].text)
    ):
        return REFUSAL

    texts = [hit.text for hit in hits[:2] if hit.text]
    if not texts:
        return REFUSAL if not force_answer else ""

    return " ".join(texts)


def _content_tokens(text: str) -> set[str]:
    """Content-ish tokens: length > 3 filters stopwords like the/for/and."""
    return {m.group(0).lower() for m in _CONTENT_TOKEN_RE.finditer(text) if len(m.group(0)) > 3}


def _shares_content_words(query: str, text: str) -> bool:
    query_tokens = _content_tokens(query)
    if not query_tokens:
        return True
    return bool(query_tokens & _content_tokens(text))
