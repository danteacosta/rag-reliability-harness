from product.arp_adapter import ArpV2EventLog


def test_event_log_adds_run_provenance_and_supports_lint_checkpoint(tmp_path):
    log = ArpV2EventLog(tmp_path / "events.jsonl", experiment_id="exp", run_id="run")
    event = log.emit("run.started")
    lint = log.emit("semantic_lint.completed", {"finding_count": 0})
    assert event.attributes["source_refs"][0]["identifier"] == "run"
    assert lint.checkpoint == "tool.completed"
