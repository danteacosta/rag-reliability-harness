"""Single command-line entry point for reproducible RAG reliability runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from loop.run import run_closed_loop
from protocol_next.replay import replay_manifest


def _check(args: argparse.Namespace) -> int:
    result = run_closed_loop(
        corpus_root=args.corpus, golden_path=args.golden, baseline_path=args.baseline,
        runs_root=args.output, force_reingest=True,
    )
    print(json.dumps(result, indent=2))
    return int(result["exit_code"])


def _replay(args: argparse.Namespace) -> int:
    report = replay_manifest(args.manifest, reexecute=True)
    print(json.dumps(report, indent=2))
    return 0 if report["outcome"] == "approve" else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-reliability")
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="run a secret-free reliability check")
    check.add_argument("--corpus", type=Path, required=True)
    check.add_argument("--golden", type=Path, required=True)
    check.add_argument("--baseline", type=Path, required=True)
    check.add_argument("--output", type=Path, required=True)
    check.set_defaults(handler=_check)
    replay = commands.add_parser("replay", help="validate and re-execute a run manifest")
    replay.add_argument("--manifest", type=Path, required=True)
    replay.set_defaults(handler=_replay)
    args = parser.parse_args(argv)
    return args.handler(args)
