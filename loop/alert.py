"""Alert sink for closed-loop gate failures (file + optional webhook)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from loop.ownership import OwnerAssignment
from protocol_next import DecisionReason


def emit_alert(
    *,
    decision_reasons: Iterable[DecisionReason] = (),
    owner_assignments: Iterable[OwnerAssignment] = (),
    reasons: list[str] | None = None,
    owners: list[str] | None = None,
    metrics: dict[str, Any],
    alert_path: Path | str,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Write alert JSON; optionally POST to webhook (best-effort, never raises)."""
    structured_reasons = list(decision_reasons)
    structured_assignments = list(owner_assignments)
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": "gate_failed",
        # Legacy summaries are preserved for integrations that display strings.
        "reasons": list(reasons) if reasons is not None else [reason.message for reason in structured_reasons],
        "owners": list(owners) if owners is not None else [item.owner for item in structured_assignments],
        "decision_reasons": [reason.to_dict() for reason in structured_reasons],
        "owner_assignments": [item.to_dict() for item in structured_assignments],
        "metrics_summary": {
            k: metrics.get(k)
            for k in (
                "recall@5",
                "mrr",
                "groundedness",
                "refusal_accuracy",
                "drift_ok",
                "latency_p95_ms",
            )
            if k in metrics
        },
    }
    path = Path(alert_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if webhook_url:
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310 — caller-provided URL
                payload["webhook_status"] = getattr(resp, "status", None)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            payload["webhook_error"] = str(exc)
            path.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    return payload


def load_last_alert(alert_path: Path | str) -> dict[str, Any] | None:
    path = Path(alert_path)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
