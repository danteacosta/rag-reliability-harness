"""Append-only candidate memory with provenance and human review gates."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows fallback
    fcntl = None


@dataclass(frozen=True)
class MemoryCandidate:
    user_id: str
    category: str
    content: str
    confidence: float
    source_refs: list[dict[str, str]] = field(default_factory=list)
    retention_days: int = 90


class CandidateMemoryStore:
    def __init__(
        self,
        path: Path | str,
        *,
        audit_path: Path | str | None = None,
        retention_days: int = 90,
        max_payload_bytes: int = 16_384,
    ) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._audit_path = Path(audit_path) if audit_path else self._path.with_suffix(".audit.jsonl")
        self._audit_path.parent.mkdir(parents=True, exist_ok=True)
        if retention_days <= 0:
            raise ValueError("retention_days must be positive")
        if max_payload_bytes <= 0:
            raise ValueError("max_payload_bytes must be positive")
        self._retention_days = retention_days
        self._max_payload_bytes = max_payload_bytes

    def add(self, candidate: MemoryCandidate) -> dict[str, Any]:
        if not candidate.source_refs:
            raise ValueError("source_refs are required for candidate memory")
        if not 0.0 <= candidate.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        if candidate.retention_days <= 0:
            raise ValueError("retention_days must be positive")
        _validate_source_refs(candidate.source_refs)
        retention_days = min(candidate.retention_days, self._retention_days)
        created_at = datetime.now(timezone.utc)
        record = {
            "candidate_id": str(uuid.uuid4()),
            "user_id": candidate.user_id,
            "category": candidate.category,
            "content": candidate.content,
            "confidence": candidate.confidence,
            "source_refs": candidate.source_refs,
            "status": "candidate",
            "created_at": created_at.isoformat(),
            "expires_at": (created_at + timedelta(days=retention_days)).isoformat(),
        }
        _validate_payload(record, self._max_payload_bytes)
        self._append(record)
        self._audit("add", user_id=candidate.user_id, candidate_id=record["candidate_id"])
        return record

    def review(self, candidate_id: str, *, status: str, reviewer: str | None = None) -> dict[str, Any]:
        if status not in {"accepted", "rejected"}:
            raise ValueError("status must be accepted or rejected")
        if status == "accepted" and not reviewer:
            raise ValueError("reviewer is required to accept a candidate")
        records = self._records()
        for record in reversed(records):
            if record.get("candidate_id") == candidate_id:
                updated = {**record, "status": status, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat()}
                self._append(updated)
                self._audit("review", user_id=str(record["user_id"]), candidate_id=candidate_id, status=status)
                return updated
        raise KeyError(candidate_id)

    def delete(self, candidate_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        if not actor.strip() or not reason.strip():
            raise ValueError("actor and reason are required")
        for record in reversed(self._records()):
            if record.get("candidate_id") == candidate_id:
                deleted = {
                    **record,
                    "status": "deleted",
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_by": actor,
                    "deletion_reason": reason,
                }
                self._append(deleted)
                self._audit("delete", user_id=str(record["user_id"]), candidate_id=candidate_id, actor=actor)
                return deleted
        raise KeyError(candidate_id)

    def retrieve(
        self,
        query: str,
        *,
        user_id: str | None = None,
        category: str | None = None,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Retrieve reviewed candidates by typed category and lexical relevance.

        This deliberately avoids embedding raw conversations. Only the latest
        reviewed record for each candidate is eligible for product retrieval.
        """
        if limit <= 0:
            return []
        terms = {term.casefold() for term in query.split() if term.strip()}
        latest: dict[str, dict[str, Any]] = {}
        for record in self._records():
            latest[record["candidate_id"]] = record
        scored: list[tuple[float, dict[str, Any]]] = []
        for record in latest.values():
            if record.get("status") != "accepted":
                continue
            if record.get("status") == "deleted" or _is_expired(record):
                continue
            if user_id is not None and record.get("user_id") != user_id:
                continue
            if category is not None and record.get("category") != category:
                continue
            content_terms = set(str(record.get("content", "")).casefold().split())
            overlap = len(terms & content_terms)
            if terms and overlap == 0:
                continue
            score = overlap / max(len(terms), 1) + float(record.get("confidence", 0.0)) * 0.01
            scored.append((score, record))
        scored.sort(key=lambda item: (-item[0], item[1]["candidate_id"]))
        self._audit("retrieve", user_id=user_id, query_hash=hashlib.sha256(query.encode("utf-8")).hexdigest())
        return [record for _, record in scored[:limit]]

    def audit_log(self) -> list[dict[str, Any]]:
        if not self._audit_path.is_file():
            return []
        return [json.loads(line) for line in self._audit_path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _records(self) -> list[dict[str, Any]]:
        if not self._path.is_file():
            return []
        return [json.loads(line) for line in self._path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _append(self, record: dict[str, Any]) -> None:
        self._append_to(self._path, record)

    def _audit(self, action: str, **payload: Any) -> None:
        self._append_to(self._audit_path, {"action": action, "at": datetime.now(timezone.utc).isoformat(), **payload})

    @staticmethod
    def _append_to(path: Path, record: dict[str, Any]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _validate_source_refs(source_refs: list[dict[str, str]]) -> None:
    for ref in source_refs:
        if not isinstance(ref, dict) or not str(ref.get("kind", "")).strip() or not str(ref.get("identifier", "")).strip():
            raise ValueError("source_refs must contain kind and identifier")


def _validate_payload(record: dict[str, Any], limit: int) -> None:
    if len(json.dumps(record, ensure_ascii=True).encode("utf-8")) > limit:
        raise ValueError("candidate payload exceeds configured payload limit")


def _is_expired(record: dict[str, Any]) -> bool:
    expires_at = record.get("expires_at")
    if not expires_at:
        return False
    return datetime.fromisoformat(str(expires_at)).astimezone(timezone.utc) <= datetime.now(timezone.utc)
