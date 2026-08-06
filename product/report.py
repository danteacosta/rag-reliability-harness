"""JSON and SARIF reports assembled from shared ARP contracts."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from agent_reliability_protocol import GateDecision, LifecycleEvent, RunManifest

try:
    from agent_reliability_protocol import validate_thesis_envelope
except ImportError:  # ARP 2.0.5 exposes the primitives but not this convenience helper.
    def validate_thesis_envelope(manifest: RunManifest, events: Sequence[LifecycleEvent]) -> None:
        if any(event.run_id != manifest.run_id for event in events):
            raise ValueError("lifecycle event run_id does not match manifest")
        sequences = [getattr(event, "sequence_number", None) for event in events]
        if all(sequence is not None for sequence in sequences) and sequences != list(range(sequences[0], sequences[0] + len(sequences))):
            raise ValueError("lifecycle event sequence is not contiguous")

from product.codes import product_exit_code


@dataclass(frozen=True)
class ProductGateReport:
    """A consumer-facing report with an opaque RAG adapter payload.

    ``manifest``, ``decision`` and ``events`` are shared ARP contracts.  The
    ``rag`` mapping is deliberately namespaced and opaque so RAG-specific
    fields do not become a second product protocol.
    """

    manifest: RunManifest
    events: tuple[LifecycleEvent, ...] = ()
    metrics: Mapping[str, Any] = field(default_factory=dict)
    rag: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_run(
        cls,
        manifest: RunManifest,
        events: Sequence[LifecycleEvent],
        *,
        metrics: Mapping[str, Any],
        rag: Mapping[str, Any] | None = None,
    ) -> "ProductGateReport":
        foreign = [event.run_id for event in events if event.run_id != manifest.run_id]
        if foreign:
            raise ValueError(
                f"all lifecycle events must use manifest run_id {manifest.run_id!r}; got {foreign[0]!r}"
            )
        if events:
            validate_thesis_envelope(manifest, events)
        return cls(
            manifest=manifest,
            events=tuple(events),
            metrics=dict(metrics),
            rag=dict(rag or {}),
        )

    @property
    def decision(self) -> GateDecision:
        decision = self.manifest.decision
        if decision is None:
            raise ValueError("manifest must carry a gate decision")
        return decision

    @property
    def exit_code(self) -> int:
        """Return the stable product-process code (0/10/20)."""
        return product_exit_code(self.decision)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "rag-product-report/v1",
            "run_id": self.manifest.run_id,
            "decision": self.decision.to_dict(),
            "manifest": self.manifest.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "metrics": dict(self.metrics),
            "rag": dict(self.rag),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=True) + "\n"

    def to_sarif(self) -> dict[str, Any]:
        """Return a SARIF 2.1.0 document suitable for CI check-runs."""
        results = []
        level = _sarif_level(self.decision)
        if level is not None:
            reason_codes = [reason.code for reason in self.decision.reasons]
            evidence_bases = [
                f"{reason.code}:{_evidence_subject(item)}"
                for reason in self.decision.reasons
                for item in reason.evidence
            ]
            evidence_counts = Counter(evidence_bases)
            for reason_index, reason in enumerate(self.decision.reasons):
                evidence = [
                    _evidence_dict(
                        item,
                        evidence_id=(
                            f"{reason.code}:{_evidence_subject(item)}"
                            if evidence_counts[
                                f"{reason.code}:{_evidence_subject(item)}"
                            ] == 1
                            else f"{reason.code}:{reason_index}:{evidence_index}:{_evidence_subject(item)}"
                        ),
                    )
                    for evidence_index, item in enumerate(reason.evidence)
                ]
                results.append(
                    {
                        "ruleId": (
                            reason.code
                            if reason_codes.count(reason.code) == 1
                            else f"{reason.code}:{reason_index}"
                        ),
                        "level": level,
                        "message": {"text": reason.message},
                        "properties": {
                            "runId": self.manifest.run_id,
                            "evidence": evidence,
                        },
                    }
                )
        else:
            results.append(
                {
                    "ruleId": "gate.approved",
                    "level": "note",
                    "message": {"text": "RAG reliability gate approved"},
                    "properties": {"runId": self.manifest.run_id},
                }
            )
        return {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "RAG Reliability Product Gate",
                            "informationUri": "https://github.com/danteacosta/rag-reliability-harness",
                            "version": self.manifest.harness_version,
                        }
                    },
                    "automationDetails": {"id": self.manifest.run_id},
                    "properties": {"metrics": dict(self.metrics), "rag": dict(self.rag)},
                    "results": results,
                }
            ],
        }


def _sarif_level(decision: GateDecision) -> str | None:
    value = decision.decision
    if value == "approve":
        return None
    if value in {"warn", "request_clarification"}:
        return "warning"
    return "error"


def _evidence_subject(evidence: Any) -> str:
    payload = evidence.to_dict()
    return str(payload.get("subject") or payload.get("metric_name") or payload.get("evidence_id") or "evidence")


def _evidence_dict(evidence: Any, *, evidence_id: str) -> dict[str, Any]:
    payload = evidence.to_dict()
    # EvidenceReference uses metric_name/observed_value; normalize only in the
    # SARIF adapter while retaining the source contract unchanged in JSON.
    if "metric_name" in payload:
        payload.setdefault("subject", payload["metric_name"])
    if "observed_value" in payload:
        payload.setdefault("observed", payload["observed_value"])
    payload.setdefault("evidence_id", evidence_id)
    return payload
