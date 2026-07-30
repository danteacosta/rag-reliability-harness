"""JSON export, redaction, and lightweight contract checks for protocol-next."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from protocol_next.contracts import GateDecision, RunManifest
from protocol_next.events import LifecycleEvent


ContractKind = Literal["decision", "event", "manifest"]
_SENSITIVE_KEY_PARTS = ("secret", "token", "password", "authorization", "cookie", "api_key")


def redact_contract(value: Any) -> Any:
    """Return a recursively redacted copy safe for portable fixture/export use."""
    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]" if _is_sensitive_key(str(key)) else redact_contract(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_contract(item) for item in value]
    if isinstance(value, tuple):
        return [redact_contract(item) for item in value]
    return value


def export_contract(value: Any, path: Path | str, *, redact: bool = True) -> None:
    """Serialize a protocol value as portable JSON, redacting secret-shaped fields."""
    payload = value.to_dict() if hasattr(value, "to_dict") else value
    if redact:
        payload = redact_contract(payload)
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def check_contract(kind: ContractKind, payload: Mapping[str, Any]) -> list[str]:
    """Return contract errors; accepts omitted optional v1 fields for compatibility."""
    try:
        _validate_json(payload)
        if kind == "decision":
            GateDecision.from_dict(payload)
        elif kind == "event":
            LifecycleEvent.from_dict(payload)
        elif kind == "manifest":
            RunManifest.from_dict(payload)
        else:
            return [f"unknown contract kind: {kind}"]
    except (KeyError, TypeError, ValueError) as exc:
        return [str(exc)]
    return []


def _validate_json(payload: Mapping[str, Any]) -> None:
    json.dumps(payload, ensure_ascii=True)


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_KEY_PARTS)
