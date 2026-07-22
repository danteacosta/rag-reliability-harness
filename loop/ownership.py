"""Map gate failure reasons to owning surfaces for the closed loop."""

from __future__ import annotations


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
