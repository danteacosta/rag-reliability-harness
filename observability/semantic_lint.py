"""Post-run semantic quality checks for product sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_SECRET_PARTS = ("api_key", "secret", "token", "password")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    source: str


def lint_session(session: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []
    if not session.get("source_refs"):
        findings.append(Finding("missing_source_refs", "error", "session has no source references", "session"))
    if _contains_secret_key(session):
        findings.append(Finding("secret_like_field", "error", "session contains a secret-like field", "session"))
    return findings


def validate_session(session: dict[str, Any], *, strict: bool = False) -> list[Finding]:
    findings = lint_session(session)
    if strict and findings:
        raise ValueError(", ".join(sorted({finding.code for finding in findings})))
    return findings


def _contains_secret_key(value: Any) -> bool:
    if isinstance(value, dict):
        return any(any(part in str(key).lower() for part in _SECRET_PARTS) or _contains_secret_key(item) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_secret_key(item) for item in value)
    return False
