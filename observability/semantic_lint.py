"""Post-run semantic quality checks for product sessions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

_SECRET_PARTS = ("api_key", "secret", "token", "password")
LINT_RULESET_VERSION = "v1"


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    source: str
    rule_version: str = LINT_RULESET_VERSION


def lint_session(
    session: dict[str, Any],
    *,
    worker_status: str = "ready",
    ruleset_version: str = LINT_RULESET_VERSION,
    now: datetime | None = None,
    max_age_seconds: int = 86_400,
) -> list[Finding]:
    if ruleset_version != LINT_RULESET_VERSION:
        return [Finding("semantic_lint_unavailable", "error", "unknown semantic-lint ruleset", "worker")]
    findings: list[Finding] = []
    if worker_status not in {"ready", "stale", "unknown"} or worker_status != "ready":
        findings.append(Finding("semantic_lint_unavailable", "error", "semantic-lint worker is not ready", "worker"))
    if not session.get("source_refs"):
        findings.append(Finding("missing_source_refs", "error", "session has no source references", "session"))
    if _contains_secret_key(session):
        findings.append(Finding("secret_like_field", "error", "session contains a secret-like field", "session"))
    observed_at = session.get("observed_at") or session.get("created_at")
    if observed_at:
        try:
            observed = datetime.fromisoformat(str(observed_at)).astimezone(timezone.utc)
            current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
            if (current - observed).total_seconds() > max_age_seconds:
                findings.append(Finding("stale_session", "error", "session is older than the lint freshness window", "session"))
        except ValueError:
            findings.append(Finding("invalid_session_timestamp", "error", "session timestamp is invalid", "session"))
    return findings


def validate_session(session: dict[str, Any], *, strict: bool = False, **kwargs: Any) -> list[Finding]:
    findings = lint_session(session, **kwargs)
    if strict and findings:
        raise ValueError(", ".join(sorted({finding.code for finding in findings})))
    return findings


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(any(part in str(key).lower() for part in _SECRET_PARTS) or _contains_secret_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False
