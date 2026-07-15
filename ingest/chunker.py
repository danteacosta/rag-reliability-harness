from __future__ import annotations

import hashlib
import re
from typing import Iterable

from rag_harness.types import Chunk

CHUNK_SIZE = 400
CHUNK_OVERLAP = 40
_HEADING_PATTERN = re.compile(r"(?=^## )", re.MULTILINE)


def chunk_document(text: str, *, doc_stem: str, doc_id: str) -> list[Chunk]:
    """Split markdown into stable chunks with IDs like ``{doc_stem}.{idx:02d}``."""
    sections = _split_sections(text)
    pieces: list[str] = []
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if len(section) <= CHUNK_SIZE:
            pieces.append(section)
        else:
            pieces.extend(_sliding_windows(section))

    if not pieces:
        stripped = text.strip()
        if stripped:
            pieces = _sliding_windows(stripped) if len(stripped) > CHUNK_SIZE else [stripped]

    chunks: list[Chunk] = []
    for idx, piece in enumerate(pieces, start=1):
        chunks.append(
            Chunk(
                id=f"{doc_stem}.{idx:02d}",
                doc_id=doc_id,
                text=piece,
                metadata={"doc_id": doc_id},
            )
        )
    return chunks


def _split_sections(text: str) -> list[str]:
    if "## " not in text:
        return [text]

    parts = _HEADING_PATTERN.split(text)
    if not parts or not parts[0].strip():
        parts = parts[1:] if parts else [text]
    return [part for part in parts if part.strip()]


def _sliding_windows(text: str) -> list[str]:
    if len(text) <= CHUNK_SIZE:
        return [text]

    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + CHUNK_SIZE, len(text))
        windows.append(text[start:end])
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return windows
