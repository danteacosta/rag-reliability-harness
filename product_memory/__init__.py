"""Explicit, reviewable product-memory candidates."""

from .candidates import CandidateMemoryStore, MemoryCandidate
from .ingress import ingest_session_handoff

__all__ = ["CandidateMemoryStore", "MemoryCandidate", "ingest_session_handoff"]
