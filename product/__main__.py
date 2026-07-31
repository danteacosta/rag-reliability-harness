from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent_reliability_protocol import GateDecision, LifecycleEvent, RunManifest

from product.report import ProductGateReport


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a shared ARP run as a product gate report.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--events", type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--rag", type=Path, help="Optional opaque RAG adapter payload JSON.")
    parser.add_argument("--format", choices=("json", "sarif"), default="json")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    manifest_payload = json.loads(args.manifest.read_text(encoding="utf-8"))
    # ARP v2.0.5's compatibility ``from_dict`` keeps the decision mapping
    # opaque; normalize it at this adapter boundary before rendering.
    if isinstance(manifest_payload.get("decision"), dict):
        manifest_payload["decision"] = GateDecision.from_dict(manifest_payload["decision"])
    manifest = RunManifest.from_dict(manifest_payload)
    events = []
    if args.events:
        for line in args.events.read_text(encoding="utf-8").splitlines():
            if line.strip():
                events.append(LifecycleEvent.from_dict(json.loads(line)))
    metrics = json.loads(args.metrics.read_text(encoding="utf-8")) if args.metrics else {}
    rag = json.loads(args.rag.read_text(encoding="utf-8")) if args.rag else {}
    report = ProductGateReport.from_run(manifest, events, metrics=metrics, rag=rag)
    payload = report.to_sarif() if args.format == "sarif" else report.to_dict()
    rendered = json.dumps(payload, indent=2, ensure_ascii=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return report.decision.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
