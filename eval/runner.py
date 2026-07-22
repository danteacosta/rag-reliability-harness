from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from ingest.fingerprint import content_hash, corpus_fingerprint
from ingest.pipeline import load_fingerprint, load_index
from rag_harness.types import GoldenItem, RetrievalHit
from retrieval.generate import generate_answer
from retrieval.retriever import DEFAULT_K, HarnessRetriever

from eval.metrics import (
    aggregate_retrieval_metrics,
    drift_ok,
    groundedness,
    refusal_accuracy,
)

DEFAULT_GOLDEN = Path("data/golden/set.jsonl")
DEFAULT_INDEX_DIR = Path(".index")
DEFAULT_CORPUS_ROOT = Path("data/corpus")
DEFAULT_OUTPUT = Path("eval/last_run.json")
DEFAULT_MUTABLE_VERSION = "v2"


def load_golden(path: Path | str = DEFAULT_GOLDEN) -> list[GoldenItem]:
    items: list[GoldenItem] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            items.append(GoldenItem.from_dict(json.loads(line)))
    return items


def compute_expected_fingerprint(
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    *,
    mutable_version: str = DEFAULT_MUTABLE_VERSION,
) -> str:
    corpus_root = Path(corpus_root)
    roots = [
        corpus_root / "fastapi",
        corpus_root / "mutable" / mutable_version,
    ]
    doc_pairs: list[tuple[str, str]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for doc_path in sorted(root.rglob("*.md")):
            text = doc_path.read_text(encoding="utf-8")
            doc_id = doc_path.relative_to(corpus_root).with_suffix("").as_posix()
            doc_pairs.append((doc_id, content_hash(text)))
    return corpus_fingerprint(doc_pairs)


def run_eval(
    *,
    golden_path: Path | str = DEFAULT_GOLDEN,
    index_dir: Path | str = DEFAULT_INDEX_DIR,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    mutable_version: str = DEFAULT_MUTABLE_VERSION,
    k: int = DEFAULT_K,
    output_path: Path | str = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    store, _metadata = load_index(index_dir)
    retriever = HarnessRetriever(store=store, k=k)

    per_item: list[dict[str, Any]] = []
    groundedness_scores: list[float] = []
    latencies_ms: list[float] = []

    for item in golden:
        t0 = time.perf_counter()
        docs = retriever.invoke(item.question)
        hits = [_document_to_hit(doc) for doc in docs]
        retrieved_ids = [hit.chunk_id for hit in hits]
        answer = generate_answer(item.question, hits)
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
        contexts = [hit.text for hit in hits]
        g = groundedness(answer, contexts=contexts)
        groundedness_scores.append(g)

        per_item.append(
            {
                "id": item.id,
                "question": item.question,
                "relevant_chunk_ids": list(item.relevant_chunk_ids),
                "retrieved": retrieved_ids,
                "answer": answer,
                "groundedness": g,
                "failure_mode": item.failure_mode,
            }
        )

    retrieval = aggregate_retrieval_metrics(per_item, k=k)
    refusal = refusal_accuracy(per_item)
    mean_groundedness = (
        sum(groundedness_scores) / len(groundedness_scores) if groundedness_scores else 0.0
    )
    lat_sorted = sorted(latencies_ms)
    latency_p50 = _percentile(lat_sorted, 50)
    latency_p95 = _percentile(lat_sorted, 95)

    fingerprint_active = load_fingerprint(index_dir)
    fingerprint_expected = compute_expected_fingerprint(
        corpus_root,
        mutable_version=mutable_version,
    )
    is_drift_ok = drift_ok(
        active_fp=fingerprint_active,
        expected_fp=fingerprint_expected,
    )

    metrics: dict[str, Any] = {
        **retrieval,
        "groundedness": mean_groundedness,
        "refusal_accuracy": refusal,
        "latency_p50_ms": latency_p50,
        "latency_p95_ms": latency_p95,
        "fingerprint_active": fingerprint_active,
        "fingerprint_expected": fingerprint_expected,
        "drift_ok": is_drift_ok,
        "k": k,
        "n_items": len(per_item),
        "n_retrieval_items": sum(1 for i in per_item if i["relevant_chunk_ids"]),
        "n_refusal_items": sum(1 for i in per_item if not i["relevant_chunk_ids"]),
        "items": per_item,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(metrics, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return metrics


def print_summary(metrics: dict[str, Any]) -> None:
    k = metrics.get("k", DEFAULT_K)
    lines = [
        f"recall@{k}: {metrics.get(f'recall@{k}', 0.0):.4f}",
        f"precision@{k}: {metrics.get(f'precision@{k}', 0.0):.4f}",
        f"mrr: {metrics.get('mrr', 0.0):.4f}",
        f"groundedness: {metrics.get('groundedness', 0.0):.4f}",
        f"refusal_accuracy: {metrics.get('refusal_accuracy', 0.0):.4f}",
        f"latency_p50_ms: {metrics.get('latency_p50_ms', 0.0):.2f}",
        f"latency_p95_ms: {metrics.get('latency_p95_ms', 0.0):.2f}",
        f"drift_ok: {metrics.get('drift_ok')}",
        f"fingerprint_active: {metrics.get('fingerprint_active')}",
        f"fingerprint_expected: {metrics.get('fingerprint_expected')}",
        f"n_items: {metrics.get('n_items')}",
    ]
    print("\n".join(lines))


def _document_to_hit(doc: Any) -> RetrievalHit:
    metadata = dict(doc.metadata or {})
    chunk_id = str(metadata.pop("chunk_id", ""))
    score = float(metadata.pop("score", 0.0))
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        text=doc.page_content,
        metadata=metadata,
    )


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
