from __future__ import annotations

import hashlib
import json
from typing import Iterable


def content_hash(text: str) -> str:
    return hashlib.blake2b(text.encode("utf-8"), digest_size=16).hexdigest()


def corpus_fingerprint(doc_pairs: Iterable[tuple[str, str]]) -> str:
    """Hash sorted (doc_id, content_hash) pairs for stable corpus fingerprints."""
    payload = json.dumps(sorted(doc_pairs), separators=(",", ":"), ensure_ascii=True)
    return hashlib.blake2b(payload.encode("utf-8"), digest_size=16).hexdigest()
