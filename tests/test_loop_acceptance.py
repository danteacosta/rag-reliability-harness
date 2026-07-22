"""ATDD — closed reliability loop (detect → reingest → eval → gate → alert)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from eval.runner import run_eval
from gates.run import check_gate, load_baseline
from ingest.pipeline import ingest_corpus, load_fingerprint
from loop.alert import load_last_alert
from loop.ownership import owners_for_failures
from loop.run import run_closed_loop

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"
GOLDEN = ROOT / "data" / "golden" / "set.jsonl"
THRESHOLDS = ROOT / "eval" / "thresholds.yaml"
BASELINE = ROOT / "eval" / "baselines" / "ci.json"
ONLINE = ROOT / "data" / "online" / "traffic_sample.jsonl"


def test_at_loop1_corpus_drift_triggers_reingest_and_healthy_gate(tmp_path: Path) -> None:
    """AT1: stale index is detected, corpus re-ingested, gate passes offline."""
    index_dir = tmp_path / "index"
    alert_path = tmp_path / "alert.json"
    status_path = tmp_path / "status.json"

    # Build intentionally stale index (v1) while loop expects v2.
    ingest_corpus(corpus_root=CORPUS, index_dir=index_dir, mutable_version="v1")
    stale_fp = load_fingerprint(index_dir)

    result = run_closed_loop(
        corpus_root=CORPUS,
        index_dir=index_dir,
        golden_path=GOLDEN,
        online_path=ONLINE,
        thresholds_path=THRESHOLDS,
        baseline_path=BASELINE,
        alert_path=alert_path,
        status_path=status_path,
        mutable_version="v2",
    )

    assert result["drift_detected"] is True
    assert result["reingested"] is True
    assert result["gate_ok"] is True
    assert result["exit_code"] == 0
    assert load_fingerprint(index_dir) != stale_fp
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["healthy"] is True
    assert "latency_p95_ms" in status["metrics"]


def test_at_loop2_gate_failure_emits_alert_with_ownership(tmp_path: Path) -> None:
    """AT2: when gate fails, alert artifact includes owners and reasons."""
    index_dir = tmp_path / "index"
    alert_path = tmp_path / "alert.json"
    status_path = tmp_path / "status.json"
    bad_thresholds = tmp_path / "bad_thresholds.yaml"

    ingest_corpus(corpus_root=CORPUS, index_dir=index_dir, mutable_version="v2")
    data = yaml.safe_load(THRESHOLDS.read_text(encoding="utf-8"))
    data["floors"]["recall@5"] = 1.1  # impossible
    bad_thresholds.write_text(yaml.safe_dump(data), encoding="utf-8")

    result = run_closed_loop(
        corpus_root=CORPUS,
        index_dir=index_dir,
        golden_path=GOLDEN,
        online_path=ONLINE,
        thresholds_path=bad_thresholds,
        baseline_path=BASELINE,
        alert_path=alert_path,
        status_path=status_path,
        mutable_version="v2",
    )

    assert result["gate_ok"] is False
    assert result["exit_code"] == 1
    alert = load_last_alert(alert_path)
    assert alert is not None
    assert alert["reasons"]
    assert alert["owners"]
    assert "retrieval" in alert["owners"] or "generate" in alert["owners"] or "ingest" in alert["owners"]


def test_at_loop3_healthy_loop_writes_status_without_required_webhook(tmp_path: Path) -> None:
    """AT3: healthy loop exits 0; webhook env optional (no secrets required)."""
    index_dir = tmp_path / "index"
    status_path = tmp_path / "status.json"
    alert_path = tmp_path / "alert.json"

    result = run_closed_loop(
        corpus_root=CORPUS,
        index_dir=index_dir,
        golden_path=GOLDEN,
        online_path=ONLINE,
        thresholds_path=THRESHOLDS,
        baseline_path=BASELINE,
        alert_path=alert_path,
        status_path=status_path,
        mutable_version="v2",
        webhook_url=None,
    )
    assert result["exit_code"] == 0
    assert not alert_path.exists()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["healthy"] is True
    assert status["online_n"] >= 1


def test_at_loop4_ownership_maps_failure_classes() -> None:
    """AT4: failure reasons map to clear owners (caller-visible contract)."""
    owners = owners_for_failures(
        [
            "drift_ok required but metrics['drift_ok'] is not True",
            "floor mrr: 0.1 < 0.55",
            "floor refusal_accuracy: 0.0 < 0.9",
            "floor latency_p95_ms: 9999 < 1",
        ]
    )
    assert "ingest" in owners
    assert "retrieval" in owners
    assert "generate" in owners
    assert "infra" in owners


def test_at_loop5_eval_reports_latency_percentiles(tmp_path: Path) -> None:
    """AT5: eval metrics include latency p50/p95 for the closed-loop SLO story."""
    index_dir = tmp_path / "index"
    ingest_corpus(corpus_root=CORPUS, index_dir=index_dir, mutable_version="v2")
    metrics = run_eval(
        golden_path=GOLDEN,
        index_dir=index_dir,
        corpus_root=CORPUS,
        output_path=tmp_path / "last_run.json",
    )
    assert metrics["latency_p50_ms"] >= 0
    assert metrics["latency_p95_ms"] >= metrics["latency_p50_ms"]
