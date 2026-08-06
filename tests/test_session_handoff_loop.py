from pathlib import Path

from loop.run import run_closed_loop


ROOT = Path(__file__).resolve().parents[1]


def test_closed_loop_can_ingest_a_real_session_handoff(tmp_path: Path) -> None:
    result = run_closed_loop(
        corpus_root=ROOT / "data" / "corpus",
        index_dir=tmp_path / "index",
        golden_path=ROOT / "data" / "golden" / "set.jsonl",
        online_path=ROOT / "data" / "online" / "traffic_sample.jsonl",
        thresholds_path=ROOT / "eval" / "thresholds.yaml",
        baseline_path=ROOT / "eval" / "baselines" / "ci.json",
        runs_root=tmp_path / "runs",
        force_reingest=True,
        candidate_store_path=tmp_path / "candidates.jsonl",
        user_id="user-hash",
        session_handoff={
            "session_id_hash": "session-hash",
            "handoff": {"decision": "target role", "next_step": "send follow-up"},
        },
    )
    assert result["memory_candidates"]["count"] == 2
    assert "memory_candidates.ingested" in (tmp_path / "runs" / result["manifest"]["run_id"] / "events.jsonl").read_text()
