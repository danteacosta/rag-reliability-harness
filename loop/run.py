"""Closed reliability loop: detect drift → re-ingest → eval → gate → alert."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import Any

from eval.runner import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN,
    DEFAULT_INDEX_DIR,
    DEFAULT_MUTABLE_VERSION,
    DEFAULT_OUTPUT,
    _document_to_hit,
    compute_expected_fingerprint,
    run_eval,
)
from gates.run import (
    DEFAULT_BASELINE,
    DEFAULT_THRESHOLDS,
    check_gate,
    load_baseline,
    load_thresholds,
)
from ingest.pipeline import ingest_corpus, load_fingerprint, load_index
from loop.alert import emit_alert
from loop.ownership import owners_for_failures
from retrieval.generate import generate_answer
from retrieval.retriever import DEFAULT_K, HarnessRetriever

DEFAULT_ONLINE = Path("data/online/traffic_sample.jsonl")
DEFAULT_ALERT = Path("loop/last_alert.json")
DEFAULT_STATUS = Path("loop/last_status.json")


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

    retriever = HarnessRetriever(store=store, k=k)
    latencies: list[float] = []
    refusals = 0
    for row in queries:
        t0 = time.perf_counter()
        docs = retriever.invoke(row["question"])
        hits = [_document_to_hit(doc) for doc in docs]
        answer = generate_answer(row["question"], hits)
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
    mutable_version: str = DEFAULT_MUTABLE_VERSION,
    webhook_url: str | None = None,
    force_reingest: bool = False,
) -> dict[str, Any]:
    """Run detect → reingest → eval (+ online sample) → gate → alert."""
    corpus_root = Path(corpus_root)
    index_dir = Path(index_dir)

    expected_fp = compute_expected_fingerprint(
        corpus_root, mutable_version=mutable_version
    )
    index_exists = (index_dir / "fingerprint.json").is_file()
    active_fp = load_fingerprint(index_dir) if index_exists else None
    drift_detected = (active_fp is None) or (active_fp != expected_fp)

    reingested = False
    if force_reingest or drift_detected:
        ingest_corpus(
            corpus_root=corpus_root,
            index_dir=index_dir,
            mutable_version=mutable_version,
        )
        reingested = True

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

    # Persist enriched metrics for gate + status.
    Path(metrics_path).write_text(
        json.dumps(metrics, indent=2, ensure_ascii=True) + "\n", encoding="utf-8"
    )

    thresholds = load_thresholds(thresholds_path)
    baseline = load_baseline(baseline_path)
    gate_ok, reasons = check_gate(metrics, thresholds, baseline)
    owners = owners_for_failures(reasons) if not gate_ok else []

    status: dict[str, Any] = {
        "healthy": gate_ok,
        "drift_detected": drift_detected,
        "reingested": reingested,
        "fingerprint_active": metrics.get("fingerprint_active"),
        "fingerprint_expected": metrics.get("fingerprint_expected"),
        "reasons": reasons,
        "owners": owners,
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

    if not gate_ok:
        emit_alert(
            reasons=reasons,
            owners=owners,
            metrics=metrics,
            alert_path=alert_path,
            webhook_url=webhook_url,
        )

    return {
        "drift_detected": drift_detected,
        "reingested": reingested,
        "gate_ok": gate_ok,
        "exit_code": 0 if gate_ok else 1,
        "reasons": reasons,
        "owners": owners,
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
        mutable_version=args.mutable_version,
        webhook_url=args.webhook_url,
        force_reingest=args.force_reingest,
    )
    print(json.dumps({k: result[k] for k in ("drift_detected", "reingested", "gate_ok", "exit_code", "owners", "reasons")}, indent=2))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
