"""Ingest corpus documents into a searchable vector index."""

from ingest.pipeline import ingest_corpus, load_fingerprint, load_index

__all__ = ["ingest_corpus", "load_fingerprint", "load_index"]
