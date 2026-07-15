"""Flagrare-style acceptance tests (AT1–AT5).

Public behavior only: ingest → eval → gate, plus failure-mode simulations.
No API keys required.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eval.runner import run_eval
from eval.simulate_regressions import (
    run_ambiguous_scenario,
    run_stale_scenario,
    run_unsupported_scenario,
    simulate_all,
)
from gates.run import check_gate, load_baseline, load_thresholds
from ingest.pipeline import ingest_corpus

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "data" / "corpus"
GOLDEN = ROOT / "data" / "golden" / "set.jsonl"


@pytest.fixture(scope="module")
def happy_index(tmp_path_factory: pytest.TempPathFactory) -> Path:
    index_dir = tmp_path_factory.mktemp("happy_index")
    ingest_corpus(
        corpus_root=CORPUS,
        index_dir=index_dir,
        mutable_version="v2",
    )
    return index_dir


def test_at1_happy_path_gate_passes_offline(happy_index: Path, tmp_path: Path) -> None:
    """AT1: ingest v2 → eval → gate passes with drift_ok, no cloud APIs."""
    out = tmp_path / "last_run.json"
    metrics = run_eval(
        golden_path=GOLDEN,
        index_dir=happy_index,
        corpus_root=CORPUS,
        output_path=out,
    )
    assert metrics["drift_ok"] is True
    assert metrics["refusal_accuracy"] >= 0.9
    assert metrics["recall@5"] >= 0.7
    ok, reasons = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is True, reasons
    assert out.is_file()


def test_at2_stale_context_fails_gate(tmp_path: Path) -> None:
    """AT2: v1 index vs v2 expectation → gate fails."""
    metrics = run_stale_scenario(tmp_path)
    assert metrics["drift_ok"] is False
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_at3_ambiguous_ranking_fails_gate(tmp_path: Path) -> None:
    """AT3: sabotaged ranking → gate fails."""
    metrics = run_ambiguous_scenario(tmp_path)
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_at4_unsupported_always_answer_fails_gate(tmp_path: Path) -> None:
    """AT4: force_answer path → refusal regression fails gate."""
    metrics = run_unsupported_scenario(tmp_path)
    assert metrics["refusal_accuracy"] < 0.9
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_at5_failure_modes_before_after_and_no_secrets() -> None:
    """AT5: simulate report is 0%→100% catch; CI workflow has no required secrets."""
    report = simulate_all()
    for mode in ("stale-context", "ambiguous-ranking", "unsupported-answer"):
        assert report[mode]["before_catch_rate"] == 0.0
        assert report[mode]["after_catch_rate"] == 1.0

    workflow = (ROOT / ".github" / "workflows" / "eval.yml").read_text(encoding="utf-8")
    assert "secrets." not in workflow
    assert "OPENAI" not in workflow
    assert "ANTHROPIC" not in workflow
