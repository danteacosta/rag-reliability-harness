"""Map structured gate evidence to owning surfaces for the closed loop."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from protocol_next import DecisionReason, Evidence


@dataclass(frozen=True)
class OwnerAssignment:
    owner: str
    reason_codes: tuple[str, ...]
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict:
        return {
            "owner": self.owner,
            "reason_codes": list(self.reason_codes),
            "evidence": [item.to_dict() for item in self.evidence],
        }


def owners_for_reasons(reasons: Iterable[DecisionReason]) -> list[OwnerAssignment]:
    """Assign owners from reason evidence, never by parsing display messages."""
    grouped: dict[str, dict[str, list]] = {}
    for reason in reasons:
        explicit_owner = getattr(reason, "owner", None)
        for owner in ({explicit_owner} if explicit_owner else _owners_for_evidence(reason.evidence)):
            group = grouped.setdefault(owner, {"codes": [], "evidence": []})
            if reason.code not in group["codes"]:
                group["codes"].append(reason.code)
            group["evidence"].extend(reason.evidence)
    return [
        OwnerAssignment(owner, tuple(group["codes"]), tuple(group["evidence"]))
        for owner, group in sorted(grouped.items())
    ]


def _owners_for_evidence(evidence: Iterable[Evidence]) -> set[str]:
    owners: set[str] = set()
    for item in evidence:
        subject = item.subject.lower()
        if subject in {"drift_ok", "fingerprint_active", "fingerprint_expected"}:
            owners.add("ingest")
        if any(key in subject for key in ("recall", "precision", "mrr")):
            owners.add("retrieval")
        if any(key in subject for key in ("groundedness", "refusal")):
            owners.add("generate")
        if "latency" in subject:
            owners.add("infra")
    return owners


def owners_for_failures(reasons: list[str]) -> list[str]:
    """Return stable owner labels for caller-visible gate failures."""
    owners: set[str] = set()
    for reason in reasons:
        lower = reason.lower()
        if "drift" in lower or "fingerprint" in lower:
            owners.add("ingest")
        if any(k in lower for k in ("recall", "precision", "mrr")):
            owners.add("retrieval")
        if any(k in lower for k in ("groundedness", "refusal")):
            owners.add("generate")
        if "latency" in lower:
            owners.add("infra")
    return sorted(owners)
