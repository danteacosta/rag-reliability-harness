from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ingest.chunker import chunk_document
from ingest.fingerprint import content_hash, corpus_fingerprint
from rag_harness.embeddings.hash_embedder import HashEmbedder
from rag_harness.store.memory import InMemoryVectorStore
from rag_harness.types import Chunk


@dataclass(frozen=True)
class IngestResult:
    fingerprint: str
    chunks: list[Chunk]
    doc_count: int
    mutable_version: str


def ingest_corpus(
    *,
    corpus_root: Path | str,
    index_dir: Path | str,
    mutable_version: str = "v2",
) -> IngestResult:
    corpus_root = Path(corpus_root)
    index_dir = Path(index_dir)
    index_dir.mkdir(parents=True, exist_ok=True)

    documents = _discover_documents(corpus_root, mutable_version)
    all_chunks: list[Chunk] = []
    doc_pairs: list[tuple[str, str]] = []

    for doc_path in documents:
        text = doc_path.read_text(encoding="utf-8")
        doc_id = _doc_id(doc_path, corpus_root)
        doc_stem = _doc_stem(doc_path, corpus_root)
        chunks = chunk_document(text, doc_stem=doc_stem, doc_id=doc_id)
        all_chunks.extend(chunks)
        doc_pairs.append((doc_id, content_hash(text)))

    embedder = HashEmbedder()
    store = InMemoryVectorStore(embedder)
    store.upsert(all_chunks)

    fingerprint = corpus_fingerprint(doc_pairs)
    _save_index(
        index_dir=index_dir,
        store=store,
        chunks=all_chunks,
        fingerprint=fingerprint,
        mutable_version=mutable_version,
        doc_pairs=doc_pairs,
    )

    return IngestResult(
        fingerprint=fingerprint,
        chunks=all_chunks,
        doc_count=len(documents),
        mutable_version=mutable_version,
    )


def load_fingerprint(index_dir: Path | str) -> str:
    metadata = _load_metadata(index_dir)
    return metadata["fingerprint"]


def load_index(index_dir: Path | str) -> tuple[InMemoryVectorStore, dict]:
    index_dir = Path(index_dir)
    metadata = _load_metadata(index_dir)

    chunks_data = json.loads((index_dir / "chunks.json").read_text(encoding="utf-8"))
    chunks = {item["id"]: Chunk.from_dict(item) for item in chunks_data}

    vectors_npz = np.load(index_dir / "vectors.npz")
    vectors = {chunk_id: vectors_npz[chunk_id] for chunk_id in chunks}

    embedder = HashEmbedder()
    store = InMemoryVectorStore.from_vectors(embedder, chunks, vectors)
    return store, metadata


def _discover_documents(corpus_root: Path, mutable_version: str) -> list[Path]:
    roots = [
        corpus_root / "fastapi",
        corpus_root / "mutable" / mutable_version,
    ]
    documents: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        documents.extend(sorted(root.rglob("*.md")))
    return documents


def _doc_id(doc_path: Path, corpus_root: Path) -> str:
    relative = doc_path.relative_to(corpus_root)
    return relative.with_suffix("").as_posix()


def _doc_stem(doc_path: Path, corpus_root: Path) -> str:
    relative = doc_path.relative_to(corpus_root)
    parts = list(relative.with_suffix("").parts)
    if len(parts) >= 3 and parts[0] == "mutable" and parts[1].startswith("v"):
        parts = [parts[0], *parts[2:]]
    return ".".join(parts)


def _save_index(
    *,
    index_dir: Path,
    store: InMemoryVectorStore,
    chunks: list[Chunk],
    fingerprint: str,
    mutable_version: str,
    doc_pairs: list[tuple[str, str]],
) -> None:
    chunks_payload = [
        {
            "id": chunk.id,
            "doc_id": chunk.doc_id,
            "text": chunk.text,
            "metadata": chunk.metadata,
        }
        for chunk in chunks
    ]
    (index_dir / "chunks.json").write_text(
        json.dumps(chunks_payload, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )

    vectors = store.export_vectors()
    np.savez(index_dir / "vectors.npz", **vectors)

    metadata = {
        "fingerprint": fingerprint,
        "mutable_version": mutable_version,
        "doc_count": len(doc_pairs),
        "chunk_count": len(chunks),
        "documents": [{"doc_id": doc_id, "content_hash": digest} for doc_id, digest in doc_pairs],
    }
    (index_dir / "fingerprint.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )


def _load_metadata(index_dir: Path | str) -> dict:
    index_dir = Path(index_dir)
    return json.loads((index_dir / "fingerprint.json").read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ingest markdown corpus into a vector index.")
    parser.add_argument(
        "--corpus-root",
        default="data/corpus",
        help="Root directory containing fastapi/ and mutable/ subdirectories.",
    )
    parser.add_argument(
        "--mutable-version",
        default="v2",
        help="Mutable corpus version to include (e.g. v2).",
    )
    parser.add_argument(
        "--index-dir",
        default=".index",
        help="Directory where fingerprint and index artifacts are written.",
    )
    args = parser.parse_args(argv)

    result = ingest_corpus(
        corpus_root=args.corpus_root,
        index_dir=args.index_dir,
        mutable_version=args.mutable_version,
    )
    print(
        f"Ingested {result.doc_count} documents into {args.index_dir} "
        f"(fingerprint={result.fingerprint})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
