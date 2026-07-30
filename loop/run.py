"""Closed reliability loop: detect drift → re-ingest → eval → gate → alert."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from eval.runner import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN,
    DEFAULT_INDEX_DIR,
    DEFAULT_MUTABLE_VERSION,
    DEFAULT_OUTPUT,
    compute_expected_fingerprint,
    run_eval,
)
from gates.run import (
    DEFAULT_BASELINE,
    DEFAULT_THRESHOLDS,
    decide_gate,
    load_baseline,
    load_thresholds,
)
from ingest.pipeline import ingest_corpus, load_fingerprint, load_index
from loop.alert import emit_alert
from loop.ownership import owners_for_reasons
from retrieval.retriever import DEFAULT_K, HarnessRetriever
from protocol_next import EventLog, GateDecision, RunManifest
from retrieval.adapters import ExtractiveGeneratorAdapter, HarnessRetrievalAdapter

DEFAULT_ONLINE = Path("data/online/traffic_sample.jsonl")
DEFAULT_ALERT = Path("loop/last_alert.json")
DEFAULT_STATUS = Path("loop/last_status.json")
DEFAULT_EVENTS = Path("loop/last_events.jsonl")


def _load_online_queries(path: Path | str) -> list[dict[str, str]]:
    p = Path(path)
    if not p.is_file():
        return []
    rows: list[dict[str, str]] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def _replay_online_traffic(
    store: Any,
    queries: list[dict[str, str]],
    *,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    if not queries:
        return {"online_n": 0, "online_latency_p95_ms": 0.0, "online_refusal_rate": 0.0}

    retriever = HarnessRetrievalAdapter(HarnessRetriever(store=store, k=k))
    generator = ExtractiveGeneratorAdapter()
    latencies: list[float] = []
    refusals = 0
    for row in queries:
        t0 = time.perf_counter()
        hits = retriever.retrieve(row["question"])
        answer = generator.generate(row["question"], hits)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if answer == "INSUFFICIENT_CONTEXT":
            refusals += 1

    latencies_sorted = sorted(latencies)
    p95 = _percentile(latencies_sorted, 95)
    return {
        "online_n": len(queries),
        "online_latency_p95_ms": p95,
        "online_refusal_rate": refusals / len(queries),
    }


def _percentile(sorted_values: list[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return float(sorted_values[0])
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lo = int(rank)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = rank - lo
    return float(sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac)


def _file_hash(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _git_commit() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return completed.stdout.strip() or None


def _manifest_context(
    *,
    corpus_hash: str,
    golden_path: Path | str,
    thresholds_path: Path | str,
    baseline_path: Path | str,
    index_hash: str | None,
    mutable_version: str,
    thresholds: dict[str, Any],
) -> tuple[dict[str, str], dict[str, str], dict[str, Any], dict[str, Any]]:
    config = {"mutable_version": mutable_version, "retrieval_k": DEFAULT_K}
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    git_commit = _git_commit()
    identifiers = {
        "git_commit": git_commit or "unavailable",
        "model": "HashEmbedder",
        "index": "InMemoryVectorStore",
    }
    hashes = {
        "corpus": corpus_hash,
        "golden": _file_hash(golden_path),
        "config": config_hash,
        "index": index_hash or "unavailable",
        "baseline": _file_hash(baseline_path),
        "thresholds": _file_hash(thresholds_path),
    }
    metadata = {
        "model": {"dimension": 256, "ngram_range": [3, 5]},
        "index": {"mutable_version": mutable_version},
        "threshold_provenance": {
            "path": str(Path(thresholds_path)),
            "hash": hashes["thresholds"],
            **dict(thresholds.get("provenance") or {}),
        },
    }
    return identifiers, hashes, metadata, config


def classify_drift(active_fingerprint: str | None, expected_fingerprint: str) -> str:
    """Classify deterministic corpus/index divergence for routing and alerting."""
    if active_fingerprint is None:
        return "index_missing"
    if active_fingerprint != expected_fingerprint:
        return "corpus_index_mismatch"
    return "none"


def run_closed_loop(
    *,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    golden_path: Path | str = DEFAULT_GOLDEN,
    online_path: Path | str = DEFAULT_ONLINE,
    thresholds_path: Path | str = DEFAULT_THRESHOLDS,
    baseline_path: Path | str = DEFAULT_BASELINE,
    metrics_path: Path | str = DEFAULT_OUTPUT,
    alert_path: Path | str = DEFAULT_ALERT,
    status_path: Path | str = DEFAULT_STATUS,
    events_path: Path | str = DEFAULT_EVENTS,
    mutable_version: str = DEFAULT_MUTABLE_VERSION,
    webhook_url: str | None = None,
    force_reingest: bool = False,
) -> dict[str, Any]:
    """Run detect → reingest → eval (+ online sample) → gate → alert."""
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    event_log = EventLog(events_path, run_id=run_id)
    event_log.emit("run.started", {"component": "closed_loop"})
    corpus_root = Path(corpus_root)
    index_dir = Path(index_dir)

    expected_fp = compute_expected_fingerprint(
        corpus_root, mutable_version=mutable_version
    )
    index_exists = (index_dir / "fingerprint.json").is_file()
    active_fp = load_fingerprint(index_dir) if index_exists else None
    drift_classification = classify_drift(active_fp, expected_fp)
    drift_detected = drift_classification != "none"
    event_log.emit("input.changed", {"drift_detected": drift_detected, "classification": drift_classification})

    reingested = False
    if force_reingest or drift_detected:
        ingest_corpus(
            corpus_root=corpus_root,
            index_dir=index_dir,
            mutable_version=mutable_version,
        )
        reingested = True
        event_log.emit("work.completed", {"operation": "reingest"})

    metrics = run_eval(
        golden_path=golden_path,
        index_dir=index_dir,
        corpus_root=corpus_root,
        mutable_version=mutable_version,
        output_path=metrics_path,
    )

    store, _ = load_index(index_dir)
    online_stats = _replay_online_traffic(store, _load_online_queries(online_path))
    metrics.update(online_stats)
    event_log.emit("work.completed", {"operation": "evaluation"})

    # Persist enriched metrics for gate + status.
    Path(metrics_path).write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    thresholds = load_thresholds(thresholds_path)
    baseline = load_baseline(baseline_path)
    decision: GateDecision = decide_gate(metrics, thresholds, baseline)
    event_log.emit("gate.decided", {"outcome": decision.outcome})
    reasons = [reason.message for reason in decision.reasons]
    owner_assignments = owners_for_reasons(decision.reasons)
    owners = [assignment.owner for assignment in owner_assignments]
    identifiers, hashes, metadata, configuration = _manifest_context(
        corpus_hash=expected_fp,
        golden_path=golden_path,
        thresholds_path=thresholds_path,
        baseline_path=baseline_path,
        index_hash=metrics.get("fingerprint_active"),
        mutable_version=mutable_version,
        thresholds=thresholds,
    )
    manifest = RunManifest(
        run_id=run_id,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc).isoformat(),
        decision=decision,
        identifiers=identifiers,
        hashes=hashes,
        metadata=metadata,
        configuration=configuration,
        artifacts={
            "metrics": str(Path(metrics_path)),
            "status": str(Path(status_path)),
            "alert": str(Path(alert_path)),
            "events": str(Path(events_path)),
        },
    )
    manifest_payload = manifest.to_dict()

    status: dict[str, Any] = {
        "healthy": decision.is_passed,
        "decision": decision.to_dict(),
        "manifest": manifest_payload,
        "drift_detected": drift_detected,
        "drift_classification": drift_classification,
        "reingested": reingested,
        "fingerprint_active": metrics.get("fingerprint_active"),
        "fingerprint_expected": metrics.get("fingerprint_expected"),
        "reasons": reasons,
        "owners": owners,
        "owner_assignments": [assignment.to_dict() for assignment in owner_assignments],
        "online_n": metrics.get("online_n", 0),
        "metrics": {
            k: metrics.get(k)
            for k in (
                "recall@5",
                "precision@5",
                "mrr",
                "groundedness",
                "refusal_accuracy",
                "drift_ok",
                "latency_p50_ms",
                "latency_p95_ms",
                "online_latency_p95_ms",
                "online_refusal_rate",
            )
        },
    }
    status_file = Path(status_path)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text(json.dumps(status, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if not decision.is_passed:
        emit_alert(
            decision_reasons=decision.reasons,
            owner_assignments=owner_assignments,
            reasons=reasons,
            owners=owners,
            metrics=metrics,
            alert_path=alert_path,
            webhook_url=webhook_url,
        )

    event_log.emit("run.completed", {"outcome": decision.outcome})

    return {
        "drift_detected": drift_detected,
        "reingested": reingested,
        "drift_classification": drift_classification,
        "decision": decision.to_dict(),
        "manifest": manifest_payload,
        # Compatibility fields retained for existing callers and CLI expectations.
        "gate_ok": decision.is_passed,
        "exit_code": decision.exit_code,
        "reasons": reasons,
        "owners": owners,
        "owner_assignments": [assignment.to_dict() for assignment in owner_assignments],
        "status_path": str(status_file),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Closed RAG reliability loop")
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--online", type=Path, default=DEFAULT_ONLINE)
    parser.add_argument("--thresholds", type=Path, default=DEFAULT_THRESHOLDS)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--metrics-out", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--alert-out", type=Path, default=DEFAULT_ALERT)
    parser.add_argument("--status-out", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--events-out", type=Path, default=DEFAULT_EVENTS)
    parser.add_argument("--mutable-version", default=DEFAULT_MUTABLE_VERSION)
    parser.add_argument("--force-reingest", action="store_true")
    parser.add_argument(
        "--webhook-url",
        default=os.environ.get("ALERT_WEBHOOK_URL") or None,
        help="Optional; also read from ALERT_WEBHOOK_URL",
    )
    args = parser.parse_args(argv)

    result = run_closed_loop(
        corpus_root=args.corpus_root,
        index_dir=args.index_dir,
        golden_path=args.golden,
        online_path=args.online,
        thresholds_path=args.thresholds,
        baseline_path=args.baseline,
        metrics_path=args.metrics_out,
        alert_path=args.alert_out,
        status_path=args.status_out,
        events_path=args.events_out,
        mutable_version=args.mutable_version,
        webhook_url=args.webhook_url,
        force_reingest=args.force_reingest,
    )
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
