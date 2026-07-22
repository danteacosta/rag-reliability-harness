"""Alert sink for closed-loop gate failures (file + optional webhook)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def emit_alert(
    *,
    reasons: list[str],
    owners: list[str],
    metrics: dict[str, Any],
    alert_path: Path | str,
    webhook_url: str | None = None,
) -> dict[str, Any]:
    """Write alert JSON; optionally POST to webhook (best-effort, never raises)."""
    payload: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "severity": "gate_failed",
        "reasons": list(reasons),
        "owners": list(owners),
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
