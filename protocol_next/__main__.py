from __future__ import annotations

import argparse
import json
from pathlib import Path

from protocol_next.replay import replay_manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check or replay a protocol-next manifest.")
    subcommands = parser.add_subparsers(dest="command", required=True)
    for command in ("check", "replay"):
        child = subcommands.add_parser(command)
        child.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    result = replay_manifest(args.manifest)
    print(json.dumps(result, indent=2))
    return 0 if result["outcome"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
