from __future__ import annotations

import json
from pathlib import Path

from agent_reliability_protocol import GateDecision, RunManifest
from product.__main__ import main


def test_product_cli_writes_sarif_report_and_returns_gate_exit_code(tmp_path: Path) -> None:
    manifest = RunManifest(
        schema_version="2.0.5", experiment_id="rag-product", run_id="run-cli",
        created_at="2026-07-31T00:00:00+00:00", git_sha="abc", harness_name="rag",
        harness_version="0.2.0", dataset_id="demo", dataset_hash="dataset",
        configuration_hash="config", model_provider="local", model_name="hash",
        model_version="1", random_seed=1, replication_count=1, environment={},
        decision=GateDecision(decision="approve", checkpoint="gate.decided", threshold_version="ci-v1"),
    )
    manifest_path = tmp_path / "manifest.json"
    output_path = tmp_path / "report.sarif"
    manifest_path.write_text(json.dumps(manifest.to_dict()), encoding="utf-8")

    assert main(["--manifest", str(manifest_path), "--format", "sarif", "--output", str(output_path)]) == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["automationDetails"]["id"] == "run-cli"


def test_product_cli_returns_contract_error_code_for_invalid_manifest(tmp_path: Path) -> None:
    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_text("{\"schema_version\": \"not-semver\"}", encoding="utf-8")

    assert main(["--manifest", str(manifest_path)]) == 30
