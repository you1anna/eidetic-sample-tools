"""CLI for human-gated CURATED role cleanup."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, rolecleanup


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-role-cleanup")
    subparsers = parser.add_subparsers(dest="command", required=True)
    prepare = subparsers.add_parser(
        "prepare",
        help="write read-only audition batches",
    )
    prepare.add_argument("--audit", type=Path, required=True)
    prepare.add_argument("--root", type=Path, default=config.SAMPLES_ROOT)
    prepare.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.root = config.require_root(args.root, parser)

    if args.command == "prepare":
        if not args.audit.is_file():
            print(f"audit not found: {args.audit}", file=sys.stderr)
            return 2
        if not args.root.is_dir():
            print(f"root not found: {args.root}", file=sys.stderr)
            return 2
        try:
            routes = rolecleanup.write_prepare_artifacts(
                args.audit,
                args.root,
                args.output_dir,
            )
            candidate_count = len(
                rolecleanup.read_trust_mismatches(
                    args.output_dir / "role-audit-baseline.tsv"
                )
            )
        except (OSError, ValueError) as exc:
            print(str(exc), file=sys.stderr)
            return 3
        print(f"[MANIFEST-ONLY] role cleanup: {candidate_count} candidates")
        print(f"  routes: {len(routes)}")
        print(f"  output: {args.output_dir}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
