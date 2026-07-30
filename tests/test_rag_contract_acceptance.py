"""ATDD coverage for the remaining RAG reliability contract."""

from __future__ import annotations

from pathlib import Path
import shutil

from rag_harness.reliability import (
    BaselineLifecycle,
    DriftKind,
    GateDecision,
    RetrievalStore,
    RunManifest,
    ThresholdProvenance,
    classify_drift_taxonomy,
)
from retrieval.adapters import LLMGenerator, ReplayGenerator
from rag_harness.cli import main


ROOT = Path(__file__).resolve().parents[1]


def test_at_rag_contract_exposes_named_provenance_and_gate_states() -> None:
    manifest = RunManifest.create(
        corpus_hash="corpus", golden_set_hash="golden", git_sha="abc",
        embedding_model="hash", embedding_model_version="1", index_configuration_hash="index",
        retrieval_configuration_hash="retrieval", generator_configuration_hash="generator",
        baseline_version="current", threshold_version="v1",
    )
    assert set(manifest.to_dict()).issuperset({
        "run_id", "git_sha", "corpus_hash", "golden_set_hash", "embedding_model",
        "embedding_model_version", "index_configuration_hash", "retrieval_configuration_hash",
        "generator_configuration_hash", "baseline_version", "threshold_version",
    })
    assert GateDecision.approve().decision == "approve"
    assert GateDecision.warn("watch").decision == "warn"
    assert GateDecision.block("stop").decision == "block"


def test_at_rag_adapters_and_metrics_contracts() -> None:
    assert issubclass(RetrievalStore, object)
    assert ReplayGenerator({"q": "recorded"}).generate("q", []) == "recorded"
    assert LLMGenerator().generate("q", []) == "INSUFFICIENT_CONTEXT"


def test_at_rag_threshold_baseline_and_drift_contracts() -> None:
    provenance = ThresholdProvenance(
        threshold_version="v1", baseline_dataset="golden", created_at="now", sample_size=10,
        estimation_method="bootstrap", metric_direction="higher_is_better", minimum_effect=0.05,
        owner="retrieval",
    )
    assert provenance.to_dict()["created_at"] == "now"
    assert BaselineLifecycle.from_dict({"current": "v1", "candidate": "v2", "minimum_sample_size": 10}).candidate == "v2"
    active = {"corpus_hash": "old", "document_ids": ["a"], "schema_version": "1", "embedding_model": "a", "index_configuration_hash": "a", "query_distribution_hash": "a", "retrieval_quality": 0.2, "generator_configuration_hash": "a"}
    expected = {**active, "corpus_hash": "new", "document_ids": ["b"], "schema_version": "2", "embedding_model": "b", "index_configuration_hash": "b", "query_distribution_hash": "b", "retrieval_quality": 0.9, "generator_configuration_hash": "b"}
    assert classify_drift_taxonomy(active, expected) == set(DriftKind)


def test_at_rag_cli_writes_and_reexecutes_standalone_artifact(tmp_path: Path) -> None:
    runs = tmp_path / "runs"
    assert main([
        "check", "--corpus", str(ROOT / "data" / "corpus"), "--golden", str(ROOT / "data" / "golden" / "set.jsonl"),
        "--baseline", str(ROOT / "eval" / "baselines" / "ci.json"), "--output", str(runs),
    ]) == 0
    manifest = next(runs.glob("*/manifest.json"))
    moved_run = tmp_path / "moved-run"
    shutil.move(str(manifest.parent), moved_run)
    assert main(["replay", "--manifest", str(moved_run / "manifest.json")]) == 0
