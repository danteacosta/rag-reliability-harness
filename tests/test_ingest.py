from __future__ import annotations

import json
from pathlib import Path

import pytest

from ingest.pipeline import ingest_corpus, load_fingerprint, load_index

FIXTURES_CORPUS = Path(__file__).parent / "fixtures" / "corpus"


def test_fingerprint_changes_when_doc_changes(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    config_dir = corpus_root / "mutable" / "v2"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.md"
    config_path.write_text("default_request_timeout_seconds = 60\n", encoding="utf-8")

    index_dir = tmp_path / "index"
    result1 = ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_dir,
        mutable_version="v2",
    )
    f1 = result1.fingerprint

    config_path.write_text("default_request_timeout_seconds = 30\n", encoding="utf-8")
    result2 = ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_dir,
        mutable_version="v2",
    )
    f2 = result2.fingerprint

    assert f1 != f2


def test_chunk_ids_stable_across_runs(tmp_path: Path) -> None:
    corpus_root = tmp_path / "corpus"
    doc_dir = corpus_root / "fastapi"
    doc_dir.mkdir(parents=True)
    doc_path = doc_dir / "routing.md"
    doc_path.write_text(
        "# Routing\n\n## Path parameters\n\nUse curly braces.\n",
        encoding="utf-8",
    )

    index_a = tmp_path / "index_a"
    index_b = tmp_path / "index_b"

    result_a = ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_a,
        mutable_version="v2",
    )
    result_b = ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_b,
        mutable_version="v2",
    )

    assert [chunk.id for chunk in result_a.chunks] == [
        chunk.id for chunk in result_b.chunks
    ]


def test_fingerprint_stable_for_same_corpus(tmp_path: Path) -> None:
    index_a = tmp_path / "index_a"
    index_b = tmp_path / "index_b"

    result_a = ingest_corpus(
        corpus_root=FIXTURES_CORPUS,
        index_dir=index_a,
        mutable_version="v2",
    )
    result_b = ingest_corpus(
        corpus_root=FIXTURES_CORPUS,
        index_dir=index_b,
        mutable_version="v2",
    )

    assert result_a.fingerprint == result_b.fingerprint


def test_ingest_writes_persisted_index(tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    ingest_corpus(
        corpus_root=FIXTURES_CORPUS,
        index_dir=index_dir,
        mutable_version="v2",
    )

    assert (index_dir / "fingerprint.json").is_file()
    assert (index_dir / "chunks.json").is_file()
    assert (index_dir / "vectors.npz").is_file()


def test_load_index_round_trip(tmp_path: Path) -> None:
    index_dir = tmp_path / "index"
    ingest_corpus(
        corpus_root=FIXTURES_CORPUS,
        index_dir=index_dir,
        mutable_version="v2",
    )

    store, metadata = load_index(index_dir)
    hits = store.similarity_search("default request timeout", k=1)

    assert hits
    assert "60" in hits[0].text
    assert metadata["mutable_version"] == "v2"
    assert load_fingerprint(index_dir) == metadata["fingerprint"]


def test_chunker_splits_on_headings() -> None:
    from ingest.chunker import chunk_document

    text = "# Title\n\nIntro.\n\n## Section A\n\nAlpha.\n\n## Section B\n\nBeta."
    chunks = chunk_document(text, doc_stem="fastapi.routing", doc_id="fastapi/routing")

    assert [chunk.id for chunk in chunks] == [
        "fastapi.routing.01",
        "fastapi.routing.02",
        "fastapi.routing.03",
    ]
    assert "Section A" in chunks[1].text
    assert chunks[1].doc_id == "fastapi/routing"


def test_chunker_uses_sliding_window_without_headings() -> None:
    from ingest.chunker import chunk_document

    text = "x" * 900
    chunks = chunk_document(text, doc_stem="notes.long", doc_id="notes/long")

    assert len(chunks) >= 2
    assert chunks[0].id == "notes.long.01"
    assert all(chunk.doc_id == "notes/long" for chunk in chunks)
