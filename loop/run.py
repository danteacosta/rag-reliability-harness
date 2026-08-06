"""Closed reliability loop: detect drift → re-ingest → eval → gate → alert."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
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
    load_baseline,
    load_thresholds,
)
from ingest.pipeline import ingest_corpus, load_fingerprint, load_index
from loop.alert import emit_alert
from loop.ownership import owners_for_reasons
from observability.session_quality import lint_run_events
from product.arp_adapter import ArpV2EventLog, build_arp_manifest
from product.codes import product_exit_code
from product.gate import decide_product_gate
from product_memory import CandidateMemoryStore, ingest_session_handoff
from retrieval.retriever import DEFAULT_K, HarnessRetriever
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


def _snapshot_replay_inputs(
    run_dir: Path,
    *, corpus_root: Path, golden_path: Path | str, online_path: Path | str,
    thresholds_path: Path | str, baseline_path: Path | str,
) -> dict[str, str]:
    """Copy every deterministic input needed to replay a run without source paths."""
    inputs = run_dir / "inputs"
    corpus_copy = inputs / "corpus"
    shutil.copytree(corpus_root, corpus_copy)
    copies = {"corpus_root": str(corpus_copy.relative_to(run_dir))}
    for key, source in {
        "golden_path": golden_path, "online_path": online_path,
        "thresholds_path": thresholds_path, "baseline_path": baseline_path,
    }.items():
        target = inputs / f"{key}{Path(source).suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copies[key] = str(target.relative_to(run_dir))
    return copies


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
    provenance = metadata["threshold_provenance"]
    provenance.update({
        "version": provenance.get("threshold_version"), "created": provenance.get("created_at"),
        "sample": provenance.get("baseline_dataset"), "method": provenance.get("estimation_method"),
        "direction": provenance.get("metric_direction"), "min_effect": provenance.get("minimum_effect"),
    })
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
    runs_root: Path | str | None = None,
    mutable_version: str = DEFAULT_MUTABLE_VERSION,
    webhook_url: str | None = None,
    force_reingest: bool = False,
    candidate_store_path: Path | str | None = None,
    session_handoff: dict[str, Any] | None = None,
    user_id: str | None = None,
) -> dict[str, Any]:
    """Run detect → reingest → eval (+ online sample) → gate → alert."""
    started_at = datetime.now(timezone.utc).isoformat()
    run_id = str(uuid.uuid4())
    if runs_root is not None:
        run_dir = Path(runs_root) / run_id
        metrics_path, alert_path, status_path, events_path = (
            run_dir / "metrics.json", run_dir / "alert.json", run_dir / "status.json", run_dir / "events.jsonl",
        )
    event_log = ArpV2EventLog(
        events_path,
        experiment_id="rag-reliability",
        run_id=run_id,
        episode_id=run_id,
    )
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
    event_log.emit("corpus.fingerprint.computed", {"expected": expected_fp, "active": active_fp})
    event_log.emit("drift.detected", {"drift_detected": drift_detected, "classification": drift_classification})

    reingested = False
    if force_reingest or drift_detected:
        event_log.emit("ingest.started", {"mutable_version": mutable_version})
        ingest_corpus(
            corpus_root=corpus_root,
            index_dir=index_dir,
            mutable_version=mutable_version,
        )
        reingested = True
        event_log.emit("ingest.completed", {"operation": "reingest"})

    event_log.emit("evaluation.started", {})
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
    event_log.emit("retrieval.completed", {"operation": "evaluation"})
    event_log.emit("generation.completed", {"operation": "evaluation"})
    semantic_lint_findings = lint_run_events(
        run_id,
        [event.attributes for event in event_log.events],
    )
    semantic_lint_payload = {
        "finding_count": len(semantic_lint_findings),
        "findings": [finding.__dict__ for finding in semantic_lint_findings],
    }
    event_log.emit("semantic_lint.completed", semantic_lint_payload)

    memory_candidates: list[dict[str, Any]] = []
    if session_handoff is not None:
        if not candidate_store_path or not user_id:
            raise ValueError("session_handoff requires candidate_store_path and user_id")
        memory_candidates = ingest_session_handoff(
            CandidateMemoryStore(candidate_store_path), user_id=user_id, session=session_handoff,
        )
        event_log.emit("memory_candidates.ingested", {"count": len(memory_candidates)})

    # Persist enriched metrics for gate + status.
    Path(metrics_path).write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    thresholds = load_thresholds(thresholds_path)
    baseline = load_baseline(baseline_path)
    decision = decide_product_gate(metrics, thresholds, baseline)
    event_log.emit("gate.decided", {"decision": decision.decision, "outcome": decision.outcome})
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
    replay_inputs = _snapshot_replay_inputs(run_dir, corpus_root=corpus_root, golden_path=golden_path, online_path=online_path, thresholds_path=thresholds_path, baseline_path=baseline_path) if runs_root is not None else {
        "corpus_root": str(corpus_root), "golden_path": str(golden_path), "online_path": str(online_path), "thresholds_path": str(thresholds_path), "baseline_path": str(baseline_path),
    }
    configuration = {
        **configuration,
        **replay_inputs,
    }
    manifest_path = (Path(runs_root) / run_id / "manifest.json") if runs_root is not None else None
    metadata = {
        **metadata,
        "drift_classification": drift_classification,
        "drift_detected": drift_detected,
        "metrics_summary": {
            key: metrics.get(key)
            for key in ("recall@5", "precision@5", "mrr", "groundedness", "refusal_accuracy", "drift_ok")
        },
    }
    manifest = build_arp_manifest(
        run_id=run_id,
        started_at=started_at, decision=decision, identifiers=identifiers, hashes=hashes,
        metadata=metadata, configuration=configuration,
        artifacts={
            "metrics": str(Path(metrics_path).relative_to(run_dir)) if runs_root is not None else str(Path(metrics_path)),
            "status": str(Path(status_path).relative_to(run_dir)) if runs_root is not None else str(Path(status_path)),
            "alert": str(Path(alert_path).relative_to(run_dir)) if runs_root is not None else str(Path(alert_path)),
            "events": str(Path(events_path).relative_to(run_dir)) if runs_root is not None else str(Path(events_path)),
            **({"manifest": "manifest.json"} if manifest_path else {}),
        },
    )
    manifest_payload = manifest.to_dict()
    decision_payload = decision.to_dict()
    # Keep the legacy outcome label in loop/status responses while the
    # persisted manifest remains the neutral ARP v2 decision envelope.
    decision_payload["outcome"] = decision.outcome

    status: dict[str, Any] = {
        "healthy": decision.outcome == "pass",
        "decision": decision_payload,
        "manifest": manifest_payload,
        "drift_detected": drift_detected,
        "drift_classification": drift_classification,
        "reingested": reingested,
        "fingerprint_active": metrics.get("fingerprint_active"),
        "fingerprint_expected": metrics.get("fingerprint_expected"),
        "reasons": reasons,
        "owners": owners,
        "owner_assignments": [assignment.to_dict() for assignment in owner_assignments],
        "semantic_lint": semantic_lint_payload,
        "memory_candidates": {"count": len(memory_candidates)},
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
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(manifest_payload, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")

    if decision.decision != "approve":
        emit_alert(
            decision_reasons=decision.reasons,
            owner_assignments=owner_assignments,
            reasons=reasons,
            owners=owners,
            metrics=metrics,
            alert_path=alert_path,
            webhook_url=webhook_url,
        )
        event_log.emit("alert.emitted", {"owners": owners})

    event_log.emit("run.completed", {"decision": decision.decision, "outcome": decision.outcome})

    return {
        "drift_detected": drift_detected,
        "reingested": reingested,
        "drift_classification": drift_classification,
        "decision": decision_payload,
        "manifest": manifest_payload,
        # Compatibility fields retained for existing callers and CLI expectations.
        "gate_ok": decision.outcome == "pass",
        "exit_code": product_exit_code(decision),
        "reasons": reasons,
        "owners": owners,
        "owner_assignments": [assignment.to_dict() for assignment in owner_assignments],
        "semantic_lint": semantic_lint_payload,
        "memory_candidates": {"count": len(memory_candidates)},
        "status_path": str(status_file),
        "manifest_path": str(manifest_path) if manifest_path else None,
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
