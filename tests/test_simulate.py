from __future__ import annotations

from pathlib import Path

from eval.simulate_regressions import (
    run_ambiguous_scenario,
    run_stale_scenario,
    run_unsupported_scenario,
    simulate_all,
)
from gates.run import check_gate, load_baseline, load_thresholds

CORPUS_ROOT = Path("data/corpus")


def test_stale_context_sim_caught(tmp_path: Path) -> None:
    metrics = run_stale_scenario(tmp_path, corpus_root=CORPUS_ROOT)
    assert metrics["drift_ok"] is False
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_ambiguous_ranking_sim_caught(tmp_path: Path) -> None:
    metrics = run_ambiguous_scenario(tmp_path, corpus_root=CORPUS_ROOT)
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_unsupported_always_answer_caught(tmp_path: Path) -> None:
    metrics = run_unsupported_scenario(tmp_path, corpus_root=CORPUS_ROOT)
    assert metrics["refusal_accuracy"] < 0.9
    ok, _ = check_gate(metrics, load_thresholds(), load_baseline())
    assert ok is False


def test_simulate_report_shape() -> None:
    report = simulate_all(corpus_root=CORPUS_ROOT)
    assert report["stale-context"]["before_catch_rate"] == 0.0
    assert report["stale-context"]["after_catch_rate"] == 1.0
    assert report["ambiguous-ranking"]["before_catch_rate"] == 0.0
    assert report["ambiguous-ranking"]["after_catch_rate"] == 1.0
    assert report["unsupported-answer"]["before_catch_rate"] == 0.0
    assert report["unsupported-answer"]["after_catch_rate"] == 1.0
