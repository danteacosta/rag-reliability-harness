"""Portable run protocol; domain metrics remain in the producing application."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal, Mapping


DecisionOutcome = Literal["pass", "fail"]
REQUIRED_PROVENANCE = frozenset(
    {"git", "corpus", "golden", "config", "model", "index", "baseline", "thresholds"}
)


@dataclass(frozen=True)
class Evidence:
    """A machine-readable observation that supports a decision reason."""

    kind: str
    subject: str
    observed: Any = None
    expected: Any = None
    comparator: str | None = None
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return _without_none(asdict(self))


@dataclass(frozen=True)
class DecisionReason:
    """A stable reason code with human explanation and supporting evidence."""

    code: str
    message: str
    evidence: tuple[Evidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "evidence": [item.to_dict() for item in self.evidence],
        }


@dataclass(frozen=True)
class GateDecision:
    """The gate result, independent from process and CLI conventions."""

    outcome: DecisionOutcome
    reasons: tuple[DecisionReason, ...] = ()

    @classmethod
    def passed(cls) -> "GateDecision":
        return cls(outcome="pass")

    @classmethod
    def failed(cls, *reasons: DecisionReason) -> "GateDecision":
        if not reasons:
            raise ValueError("a failed decision requires at least one reason")
        return cls(outcome="fail", reasons=tuple(reasons))

    @property
    def is_passed(self) -> bool:
        return self.outcome == "pass"

    @property
    def exit_code(self) -> int:
        return 0 if self.is_passed else 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome,
            "reasons": [reason.to_dict() for reason in self.reasons],
        }


@dataclass(frozen=True)
class RunManifest:
    """Complete, JSON-serializable identity and provenance for one evaluated run."""

    run_id: str
    started_at: str
    decision: GateDecision
    provenance: Mapping[str, Mapping[str, Any]]
    schema_version: str = "protocol_next/v1"
    completed_at: str | None = None
    artifacts: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        missing = REQUIRED_PROVENANCE.difference(self.provenance)
        if missing:
            raise ValueError(
                "missing required provenance: " + ", ".join(sorted(missing))
            )

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "started_at": self.started_at,
            "decision": self.decision.to_dict(),
            "provenance": {name: dict(value) for name, value in self.provenance.items()},
            "artifacts": dict(self.artifacts),
        }
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at
        return payload


def _without_none(values: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in values.items() if value is not None}
