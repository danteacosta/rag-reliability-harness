"""Stable, offline-first reliability contracts for this RAG harness.

The shared protocol package is intentionally domain neutral.  This module maps
the RAG run, gate, replay and baseline concepts onto explicit local contracts
without requiring a provider credential.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal, Mapping, Protocol, Sequence, runtime_checkable
from uuid import uuid4

from rag_harness.types import Chunk, RetrievalHit


Decision = Literal["approve", "warn", "block"]


@dataclass(frozen=True)
class GateReason:
    code: str
    surface: str
    metric: str | None = None
    observed: float | bool | None = None
    threshold: float | bool | None = None
    owner: str | None = None
    message: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = {key: value for key, value in asdict(self).items() if value is not None}
        payload["evidence"] = [item.to_dict() for item in self.evidence]
        return payload

    @property
    def evidence(self) -> tuple["GateEvidence", ...]:
        """Compatibility projection for callers of the old evidence shape."""
        return (GateEvidence(self.metric or self.code, self.observed, self.threshold),)


@dataclass(frozen=True)
class GateEvidence:
    subject: str
    observed: float | bool | None
    expected: float | bool | None

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "observed": self.observed, "expected": self.expected}


@dataclass(frozen=True)
class GateDecision:
    decision: Decision
    reasons: tuple[GateReason, ...] = ()
    evidence: tuple[GateReason, ...] = ()

    def __post_init__(self) -> None:
        if self.decision not in {"approve", "warn", "block"}:
            raise ValueError("decision must be approve, warn, or block")
        if self.decision == "block" and not self.reasons:
            raise ValueError("a block decision requires at least one reason")

    @classmethod
    def approve(cls) -> "GateDecision":
        return cls("approve")

    @classmethod
    def warn(cls, message: str, *, code: str = "gate.warning", surface: str = "gate") -> "GateDecision":
        reason = GateReason(code=code, surface=surface, message=message)
        return cls("warn", (reason,), (reason,))

    @classmethod
    def block(cls, message: str, *, code: str = "gate.blocked", surface: str = "gate") -> "GateDecision":
        reason = GateReason(code=code, surface=surface, message=message)
        return cls("block", (reason,), (reason,))

    @property
    def outcome(self) -> str:
        """Compatibility label for the pre-contract loop API."""
        return "pass" if self.decision == "approve" else "fail"

    @property
    def exit_code(self) -> int:
        return 0 if self.decision == "approve" else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "outcome": self.outcome,
            "reasons": [reason.to_dict() for reason in self.reasons],
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    git_sha: str
    corpus_hash: str
    golden_set_hash: str
    embedding_model: str
    embedding_model_version: str
    index_configuration_hash: str
    retrieval_configuration_hash: str
    generator_configuration_hash: str
    baseline_version: str
    threshold_version: str
    created_at: str
    decision: GateDecision = field(default_factory=GateDecision.approve)
    artifacts: Mapping[str, str] = field(default_factory=dict)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = "arp/v1"

    @classmethod
    def create(cls, **kwargs: Any) -> "RunManifest":
        return cls(run_id=kwargs.pop("run_id", str(uuid4())), created_at=kwargs.pop("created_at", datetime.now(timezone.utc).isoformat()), **kwargs)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["decision"] = self.decision.to_dict()
        payload["metadata"] = dict(self.metadata)
        payload["rag_schema_version"] = "rag-reliability/v1"
        # Compatibility projections retain the previous shared-envelope readers.
        payload["identifiers"] = {"git_commit": self.git_sha, "model": self.embedding_model, "index": "configured"}
        payload["hashes"] = {"corpus": self.corpus_hash, "golden": self.golden_set_hash, "index": self.index_configuration_hash, "config": self.retrieval_configuration_hash, "baseline": self.baseline_version, "thresholds": self.threshold_version}
        payload["started_at"] = self.created_at
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "RunManifest":
        decision_payload = dict(value["decision"])
        reasons = tuple(GateReason(**{key: item.get(key) for key in GateReason.__dataclass_fields__}) for item in decision_payload.get("reasons", []))
        return cls(
            **{key: value[key] for key in cls.__dataclass_fields__ if key in value and key not in {"decision"}},
            decision=GateDecision(str(decision_payload["decision"]), reasons, reasons),
        )


@dataclass(frozen=True)
class ThresholdProvenance:
    threshold_version: str
    baseline_dataset: str
    created_at: str
    sample_size: int
    estimation_method: str
    metric_direction: str
    minimum_effect: float
    owner: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class BaselineLifecycle:
    current: str
    candidate: str | None = None
    canary: str | None = None
    historical: tuple[str, ...] = ()
    minimum_sample_size: int = 1
    confidence_interval: float = 0.95
    threshold_sensitivity: float = 0.0

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> "BaselineLifecycle":
        return cls(
            current=str(value["current"]), candidate=value.get("candidate"), canary=value.get("canary"),
            historical=tuple(value.get("historical") or ()), minimum_sample_size=int(value.get("minimum_sample_size", 1)),
            confidence_interval=float(value.get("confidence_interval", 0.95)),
            threshold_sensitivity=float(value.get("threshold_sensitivity", 0.0)),
        )


class DriftKind(StrEnum):
    CORPUS_CONTENT = "corpus_content_drift"
    CORPUS_MEMBERSHIP = "corpus_membership_drift"
    SCHEMA = "schema_drift"
    EMBEDDING_MODEL = "embedding_model_drift"
    INDEX_CONFIGURATION = "index_configuration_drift"
    QUERY_DISTRIBUTION = "query_distribution_drift"
    RETRIEVAL_QUALITY = "retrieval_quality_drift"
    GENERATION_POLICY = "generation_policy_drift"


def classify_drift_taxonomy(active: Mapping[str, Any], expected: Mapping[str, Any]) -> set[DriftKind]:
    """Classify independently observable RAG drift surfaces."""
    fields = {
        DriftKind.CORPUS_CONTENT: "corpus_hash", DriftKind.CORPUS_MEMBERSHIP: "document_ids",
        DriftKind.SCHEMA: "schema_version", DriftKind.EMBEDDING_MODEL: "embedding_model",
        DriftKind.INDEX_CONFIGURATION: "index_configuration_hash", DriftKind.QUERY_DISTRIBUTION: "query_distribution_hash",
        DriftKind.RETRIEVAL_QUALITY: "retrieval_quality", DriftKind.GENERATION_POLICY: "generator_configuration_hash",
    }
    return {kind for kind, field_name in fields.items() if active.get(field_name) != expected.get(field_name)}


@runtime_checkable
class RetrievalStore(Protocol):
    def index(self, chunks: Sequence[Chunk], *, namespace: str = "default") -> None: ...
    def retrieve(self, query: str, *, k: int = 5, namespace: str = "default") -> list[RetrievalHit]: ...
    def delete_namespace(self, namespace: str) -> None: ...
    def health(self) -> Mapping[str, Any]: ...
