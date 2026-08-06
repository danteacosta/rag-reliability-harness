"""Append-only candidate memory with provenance and human review gates."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemoryCandidate:
    user_id: str
    category: str
    content: str
    confidence: float
    source_refs: list[dict[str, str]] = field(default_factory=list)


class CandidateMemoryStore:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def add(self, candidate: MemoryCandidate) -> dict[str, Any]:
        if not candidate.source_refs:
            raise ValueError("source_refs are required for candidate memory")
        if not 0.0 <= candidate.confidence <= 1.0:
            raise ValueError("confidence must be between 0 and 1")
        record = {
            "candidate_id": str(uuid.uuid4()),
            "user_id": candidate.user_id,
            "category": candidate.category,
            "content": candidate.content,
            "confidence": candidate.confidence,
            "source_refs": candidate.source_refs,
            "status": "candidate",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._append(record)
        return record

    def review(self, candidate_id: str, *, status: str, reviewer: str | None = None) -> dict[str, Any]:
        if status not in {"accepted", "rejected"}:
            raise ValueError("status must be accepted or rejected")
        if status == "accepted" and not reviewer:
            raise ValueError("reviewer is required to accept a candidate")
        records = [json.loads(line) for line in self._path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for record in reversed(records):
            if record.get("candidate_id") == candidate_id:
                updated = {**record, "status": status, "reviewer": reviewer, "reviewed_at": datetime.now(timezone.utc).isoformat()}
                self._append(updated)
                return updated
        raise KeyError(candidate_id)

    def _append(self, record: dict[str, Any]) -> None:
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
