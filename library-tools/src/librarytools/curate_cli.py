"""CLI for safe catalogue migration and human-gated curation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, moves
from .curate import (
    CurationError, apply_migration, plan_catalogue_migration, prepare_packet,
    promote_favourites, read_labels, validate_labels,
    undo_promotions, write_consumer_views,
)
from .inventory import LibraryDatabase


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-curate")
    parser.add_argument("--root", type=Path, default=config.SAMPLES_ROOT)
    parser.add_argument(
        "--library-db", type=Path,
        default=config.MANIFEST_DIR / "sample-library.sqlite",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    migrate = sub.add_parser("migrate-catalogue")
    migrate.add_argument("--ableton-root", type=Path, required=True)
    migrate.add_argument("--manifest", type=Path, required=True)
    migrate.add_argument("--undo", type=Path, required=True)
    migrate.add_argument("--apply", action="store_true")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--output-dir", type=Path, required=True)
    validate = sub.add_parser("validate")
    validate.add_argument("--labels", type=Path, required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--labels", type=Path, required=True)
    promote.add_argument("--run-id", required=True)
    views = sub.add_parser("views")
    views.add_argument("--labels", type=Path, required=True)
    views.add_argument("--output-dir", type=Path, required=True)
    undo_promotion = sub.add_parser("undo-promotion")
    undo_promotion.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    try:
        db = LibraryDatabase(args.library_db)
        if args.command == "migrate-catalogue":
            plan = plan_catalogue_migration(args.root, args.ableton_root, db)
            moves.write_plan(args.manifest, plan)
            print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] migration: {len(plan)} moves")
            if args.apply:
                print(apply_migration(args.root, plan, args.undo))
        elif args.command == "prepare":
            count = prepare_packet(args.root, db, args.output_dir)
            print(f"[MANIFEST-ONLY] audition candidates: {count} -> {args.output_dir}")
        elif args.command == "validate":
            rows = read_labels(args.labels)
            validate_labels(rows)
            print(f"labels valid: {len(rows)}")
        elif args.command == "promote":
            paths = promote_favourites(args.root, db, args.labels, run_id=args.run_id)
            print(f"promoted: {len(paths)}")
        elif args.command == "views":
            paths = write_consumer_views(db, args.labels, args.output_dir)
            print(f"consumer views: {len(paths)} -> {args.output_dir}")
        elif args.command == "undo-promotion":
            count = undo_promotions(args.root, db, args.run_id)
            print(f"quarantined promoted copies: {count}")
        return 0
    except (CurationError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
