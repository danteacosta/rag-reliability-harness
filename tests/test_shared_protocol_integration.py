from __future__ import annotations

from pathlib import Path

from agent_reliability_protocol import __version__, check_contract

from loop.run import run_closed_loop


ROOT = Path(__file__).resolve().parents[1]


def test_closed_loop_manifest_validates_with_shared_protocol(tmp_path: Path) -> None:
    assert __version__ == "2.0.6"
    result = run_closed_loop(
        corpus_root=ROOT / "data" / "corpus",
        index_dir=tmp_path / "index",
        golden_path=ROOT / "data" / "golden" / "set.jsonl",
        online_path=ROOT / "data" / "online" / "traffic_sample.jsonl",
        thresholds_path=ROOT / "eval" / "thresholds.yaml",
        baseline_path=ROOT / "eval" / "baselines" / "ci.json",
        metrics_path=tmp_path / "metrics.json",
        alert_path=tmp_path / "alert.json",
        status_path=tmp_path / "status.json",
        events_path=tmp_path / "events.jsonl",
    )

    assert check_contract("manifest", result["manifest"]) == []
