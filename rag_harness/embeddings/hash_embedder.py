from __future__ import annotations

import re

import numpy as np
from numpy.typing import NDArray


class HashEmbedder:
    """Lexical hashing-trick embedder (no ML downloads)."""

    DIM = 256
    NGRAM_RANGE = range(3, 6)  # 3, 4, 5

    def __init__(self, dim: int = DIM) -> None:
        self.dim = dim

    @staticmethod
    def normalize(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def embed(self, text: str) -> NDArray[np.floating]:
        normalized = self.normalize(text)
        vec = np.zeros(self.dim, dtype=np.float64)
        for n in self.NGRAM_RANGE:
            if len(normalized) < n:
                continue
            for i in range(len(normalized) - n + 1):
                gram = normalized[i : i + n]
                idx = hash(gram) % self.dim
                vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec /= norm
        return vec

    @staticmethod
    def cosine(a: NDArray[np.floating], b: NDArray[np.floating]) -> float:
        return float(np.dot(a, b))
