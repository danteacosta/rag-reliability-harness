"""Inject three failure modes and measure before/after gate catch rates."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any, Callable, Literal

from gates.run import check_gate, check_gate_blind, load_baseline, load_thresholds
from ingest.pipeline import ingest_corpus, load_fingerprint, load_index
from rag_harness.types import RetrievalHit
from retrieval.generate import generate_answer
from retrieval.retriever import DEFAULT_K, HarnessRetriever

from eval.metrics import (
    aggregate_retrieval_metrics,
    drift_ok,
    groundedness,
    refusal_accuracy,
)
from eval.runner import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN,
    compute_expected_fingerprint,
    load_golden,
)

DEFAULT_REPORT = Path("eval/sim_report.json")

Sabotage = Literal["none", "reverse_ambiguous", "force_answer"]


def run_stale_scenario(
    work_dir: Path,
    *,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    golden_path: Path | str = DEFAULT_GOLDEN,
) -> dict[str, Any]:
    """Ingest mutable/v1 while expected fingerprint stays v2 → drift_ok=False."""
    corpus_root = Path(corpus_root)
    index_dir = Path(work_dir) / "index-stale"
    ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_dir,
        mutable_version="v1",
    )
    return _run_sabotaged_eval(
        index_dir=index_dir,
        corpus_root=corpus_root,
        golden_path=golden_path,
        expected_mutable_version="v2",
        sabotage="none",
    )


def run_ambiguous_scenario(
    work_dir: Path,
    *,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    golden_path: Path | str = DEFAULT_GOLDEN,
) -> dict[str, Any]:
    """Reverse retrieval order so MRR/ranking slip fails the gate."""
    corpus_root = Path(corpus_root)
    index_dir = Path(work_dir) / "index-ambiguous"
    ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_dir,
        mutable_version="v2",
    )
    return _run_sabotaged_eval(
        index_dir=index_dir,
        corpus_root=corpus_root,
        golden_path=golden_path,
        expected_mutable_version="v2",
        sabotage="reverse_ambiguous",
    )


def run_unsupported_scenario(
    work_dir: Path,
    *,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    golden_path: Path | str = DEFAULT_GOLDEN,
) -> dict[str, Any]:
    """Force answers on unsupported items → refusal_accuracy collapses."""
    corpus_root = Path(corpus_root)
    index_dir = Path(work_dir) / "index-unsupported"
    ingest_corpus(
        corpus_root=corpus_root,
        index_dir=index_dir,
        mutable_version="v2",
    )
    return _run_sabotaged_eval(
        index_dir=index_dir,
        corpus_root=corpus_root,
        golden_path=golden_path,
        expected_mutable_version="v2",
        sabotage="force_answer",
    )


def simulate_all(
    *,
    corpus_root: Path | str = DEFAULT_CORPUS_ROOT,
    golden_path: Path | str = DEFAULT_GOLDEN,
    output_path: Path | str = DEFAULT_REPORT,
    work_dir: Path | None = None,
) -> dict[str, Any]:
    """Run all three scenarios and write before/after catch-rate report."""
    thresholds = load_thresholds()
    baseline = load_baseline()

    scenario_runners: list[tuple[str, Callable[..., dict[str, Any]]]] = [
        ("stale-context", run_stale_scenario),
        ("ambiguous-ranking", run_ambiguous_scenario),
        ("unsupported-answer", run_unsupported_scenario),
    ]

    report: dict[str, Any] = {}

    def _build(root: Path) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for name, runner in scenario_runners:
            metrics = runner(root, corpus_root=corpus_root, golden_path=golden_path)
            before_ok, _ = check_gate_blind(metrics)
            after_ok, after_failures = check_gate(metrics, thresholds, baseline)
            # Blind path always passes ⇒ never catches; full gate should fail.
            before_caught = before_ok is False
            after_caught = after_ok is False
            out[name] = {
                "before_catch_rate": 1.0 if before_caught else 0.0,
                "after_catch_rate": 1.0 if after_caught else 0.0,
                "gate_failures": after_failures,
                "drift_ok": metrics.get("drift_ok"),
                "recall@5": metrics.get("recall@5"),
                "precision@5": metrics.get("precision@5"),
                "mrr": metrics.get("mrr"),
                "groundedness": metrics.get("groundedness"),
                "refusal_accuracy": metrics.get("refusal_accuracy"),
            }
        return out

    if work_dir is not None:
        report = _build(Path(work_dir))
    else:
        with tempfile.TemporaryDirectory(prefix="rag-sim-") as tmp:
            report = _build(Path(tmp))

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    return report


def _run_sabotaged_eval(
    *,
    index_dir: Path,
    corpus_root: Path,
    golden_path: Path | str,
    expected_mutable_version: str,
    sabotage: Sabotage,
    k: int = DEFAULT_K,
) -> dict[str, Any]:
    golden = load_golden(golden_path)
    store, _metadata = load_index(index_dir)
    retriever = HarnessRetriever(store=store, k=k)

    per_item: list[dict[str, Any]] = []
    groundedness_scores: list[float] = []

    for item in golden:
        docs = retriever.invoke(item.question)
        hits = [_hit_from_document(doc) for doc in docs]
        hits = _apply_ranking_sabotage(hits, item.failure_mode, item.relevant_chunk_ids, sabotage)

        force = sabotage == "force_answer"
        answer = generate_answer(item.question, hits, force_answer=force)
        contexts = [hit.text for hit in hits]
        g = groundedness(answer, contexts=contexts)
        groundedness_scores.append(g)

        per_item.append(
            {
                "id": item.id,
                "question": item.question,
                "relevant_chunk_ids": list(item.relevant_chunk_ids),
                "retrieved": [hit.chunk_id for hit in hits],
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

    fingerprint_active = load_fingerprint(index_dir)
    fingerprint_expected = compute_expected_fingerprint(
        corpus_root,
        mutable_version=expected_mutable_version,
    )
    is_drift_ok = drift_ok(
        active_fp=fingerprint_active,
        expected_fp=fingerprint_expected,
    )

    return {
        **retrieval,
        "groundedness": mean_groundedness,
        "refusal_accuracy": refusal,
        "fingerprint_active": fingerprint_active,
        "fingerprint_expected": fingerprint_expected,
        "drift_ok": is_drift_ok,
        "k": k,
        "n_items": len(per_item),
        "n_retrieval_items": sum(1 for i in per_item if i["relevant_chunk_ids"]),
        "n_refusal_items": sum(1 for i in per_item if not i["relevant_chunk_ids"]),
        "items": per_item,
    }


def _hit_from_document(doc: Any) -> RetrievalHit:
    metadata = dict(doc.metadata or {})
    chunk_id = str(metadata.pop("chunk_id", ""))
    score = float(metadata.pop("score", 0.0))
    return RetrievalHit(
        chunk_id=chunk_id,
        score=score,
        text=doc.page_content,
        metadata=metadata,
    )


def _apply_ranking_sabotage(
    hits: list[RetrievalHit],
    failure_mode: str,
    relevant_chunk_ids: list[str],
    sabotage: Sabotage,
) -> list[RetrievalHit]:
    """Hurt ranking metrics enough that floors/slip fail the gate.

    Reverse alone can leave recall@5 at 1.0. For ambiguous items we reverse
    and force relevant chunks to the end so MRR collapses below floor/slip.
    """
    if sabotage != "reverse_ambiguous":
        return hits
    if failure_mode != "ambiguous-ranking" or not hits:
        return hits

    reversed_hits = list(reversed(hits))
    relevant = set(relevant_chunk_ids)
    if not relevant:
        return reversed_hits

    non_relevant = [h for h in reversed_hits if h.chunk_id not in relevant]
    relevant_hits = [h for h in reversed_hits if h.chunk_id in relevant]
    # Put every relevant chunk last so first relevant rank is worst in the list.
    return non_relevant + relevant_hits


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Simulate three RAG failure modes and report gate catch rates.",
    )
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args(argv)

    report = simulate_all(
        corpus_root=args.corpus_root,
        golden_path=args.golden,
        output_path=args.output,
    )
    for name, row in report.items():
        print(
            f"{name}: before={row['before_catch_rate']:.1f} "
            f"after={row['after_catch_rate']:.1f} "
            f"failures={row.get('gate_failures', [])}"
        )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
