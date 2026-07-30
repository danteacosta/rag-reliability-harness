from __future__ import annotations

import json
from pathlib import Path

import agent_reliability_protocol
from protocol_next import (
    GateDecision,
    LifecycleEvent,
    RunManifest,
    check_contract,
    export_contract,
    redact_contract,
)


FIXTURES = Path(__file__).resolve().parents[1] / "protocol_next" / "fixtures" / "v1"


def test_portable_fixtures_round_trip_against_neutral_contracts() -> None:
    decision = json.loads((FIXTURES / "decision-fail.json").read_text(encoding="utf-8"))
    event = json.loads((FIXTURES / "lifecycle-event.json").read_text(encoding="utf-8"))
    manifest = json.loads((FIXTURES / "run-manifest.json").read_text(encoding="utf-8"))

    assert check_contract("decision", decision) == []
    assert check_contract("event", event) == []
    assert check_contract("manifest", manifest) == []
    assert GateDecision.from_dict(decision).to_dict() == decision
    assert LifecycleEvent.from_dict(event).to_dict() == event
    assert RunManifest.from_dict(manifest).to_dict() == manifest


def test_portable_json_schemas_are_parseable_and_versioned() -> None:
    schemas = Path(agent_reliability_protocol.__file__).parent / "schemas"
    for schema in schemas.glob("*.schema.json"):
        payload = json.loads(schema.read_text(encoding="utf-8"))
        assert payload["$schema"] == "https://json-schema.org/draft/2020-12/schema"
        assert "agent-reliability-protocol.dev/schemas/" in payload["$id"]


def test_contract_checker_accepts_v1_omitted_optional_fields() -> None:
    legacy_manifest = {
        "run_id": "run-123",
        "started_at": "2026-07-30T00:00:00+00:00",
        "decision": {"outcome": "pass"},
        "identifiers": {"build": "build-123"},
        "hashes": {"input": "abc"},
    }

    assert check_contract("manifest", legacy_manifest) == []
    assert RunManifest.from_dict(legacy_manifest).to_dict()["schema_version"] == "arp/v1"


def test_exporter_redacts_secrets_without_mutating_source(tmp_path: Path) -> None:
    source = {"token": "secret", "nested": {"authorization": "Bearer secret"}, "safe": "ok"}
    output = tmp_path / "contract.json"

    redacted = redact_contract(source)
    export_contract(source, output)

    assert source["token"] == "secret"
    assert redacted["token"] == "[REDACTED]"
    assert redacted["nested"]["authorization"] == "[REDACTED]"
    assert json.loads(output.read_text(encoding="utf-8"))["token"] == "[REDACTED]"
