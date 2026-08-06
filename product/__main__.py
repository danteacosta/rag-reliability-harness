from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from product.report import ProductGateReport
from product.codes import PRODUCT_EXIT_CONTRACT
from product.arp_adapter import read_arp_events, read_arp_manifest
from product.demo import write_demo
from product_memory.candidates import CandidateMemoryStore
from product_memory.ingress import ingest_session_handoff


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a shared ARP run as a product gate report.")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--rag", type=Path, help="Optional opaque RAG adapter payload JSON.")
    parser.add_argument("--format", choices=("json", "sarif"), default="json")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--demo-output", type=Path, help="Write deterministic approve/warn/block demo artifacts.")
    parser.add_argument("--ingest-handoff", type=Path, help="Ingest a provider session handoff into candidate memory.")
    parser.add_argument("--user-id", help="Hashed user identifier for --ingest-handoff.")
    parser.add_argument("--candidate-store", type=Path, help="Candidate memory JSONL path for --ingest-handoff.")
    args = parser.parse_args(argv)

    if args.ingest_handoff:
        if not args.user_id or not args.candidate_store:
            print("contract error: --ingest-handoff requires --user-id and --candidate-store", file=sys.stderr)
            return PRODUCT_EXIT_CONTRACT
        try:
            session = json.loads(args.ingest_handoff.read_text(encoding="utf-8"))
            records = ingest_session_handoff(
                CandidateMemoryStore(args.candidate_store), user_id=args.user_id, session=session,
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            print(f"contract error: {exc}", file=sys.stderr)
            return PRODUCT_EXIT_CONTRACT
        print(json.dumps({"schema_version": "candidate-memory-ingress/v1", "count": len(records)}, ensure_ascii=True))
        return 0

    if args.demo_output:
        if args.manifest:
            print("contract error: --demo-output cannot be combined with --manifest", file=sys.stderr)
            return PRODUCT_EXIT_CONTRACT
        try:
            write_demo(args.demo_output)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            print(f"contract error: {exc}", file=sys.stderr)
            return PRODUCT_EXIT_CONTRACT
        return 0

    if not args.manifest:
        print("contract error: --manifest or --demo-output is required", file=sys.stderr)
        return PRODUCT_EXIT_CONTRACT

    try:
        manifest = read_arp_manifest(args.manifest)
        events = read_arp_events(args.events, run_id=manifest.run_id) if args.events else []
        metrics = json.loads(args.metrics.read_text(encoding="utf-8")) if args.metrics else {}
        rag = json.loads(args.rag.read_text(encoding="utf-8")) if args.rag else {}
        report = ProductGateReport.from_run(manifest, events, metrics=metrics, rag=rag)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        print(f"contract error: {exc}", file=sys.stderr)
        return PRODUCT_EXIT_CONTRACT
    payload = report.to_sarif() if args.format == "sarif" else report.to_dict()
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return report.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
