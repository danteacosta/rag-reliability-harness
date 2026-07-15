from __future__ import annotations

import argparse
from pathlib import Path

from eval.runner import (
    DEFAULT_CORPUS_ROOT,
    DEFAULT_GOLDEN,
    DEFAULT_INDEX_DIR,
    DEFAULT_MUTABLE_VERSION,
    DEFAULT_OUTPUT,
    print_summary,
    run_eval,
)
from retrieval.retriever import DEFAULT_K


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run RAG golden-set evaluation.")
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN)
    parser.add_argument("--index-dir", type=Path, default=DEFAULT_INDEX_DIR)
    parser.add_argument("--corpus-root", type=Path, default=DEFAULT_CORPUS_ROOT)
    parser.add_argument("--mutable-version", default=DEFAULT_MUTABLE_VERSION)
    parser.add_argument("--k", type=int, default=DEFAULT_K)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)

    metrics = run_eval(
        golden_path=args.golden,
        index_dir=args.index_dir,
        corpus_root=args.corpus_root,
        mutable_version=args.mutable_version,
        k=args.k,
        output_path=args.output,
    )
    print_summary(metrics)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
