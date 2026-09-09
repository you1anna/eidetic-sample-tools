"""CLI for safe catalogue migration and human-gated curation."""

from __future__ import annotations

import argparse
import json
import sys
import sqlite3
from pathlib import Path

from . import config, moves
from .curate import (
    CurationError, apply_migration, plan_catalogue_migration, prepare_packet,
    promote_favourites, read_labels, regenerate_packet_playlists, validate_labels,
    undo_promotions, write_consumer_views,
)
from .inventory import LibraryDatabase
from .artifacts import packet_root
from .locking import library_lock
from .state import resolve_library_db
from .curation_policy import CurationPolicyError, load_quotas, validate_crate_name
from .promotion_health import HealthCheckError, check_promotions
from .packet_classifier import PacketClassifierError, classify_packet
from .classification.review_server import load_review_packet, serve_review
from .classification.workers import DEFAULT_BATCH_SIZE, DEFAULT_THREADS, DEFAULT_TIMEOUT


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-curate")
    parser.add_argument("--root", type=Path, default=None)
    parser.add_argument(
        "--library-db", type=Path,
        default=None,
    )
    sub = parser.add_subparsers(dest="command", required=True)
    check = sub.add_parser("check", help="read-only verification of recorded promotions")
    check.add_argument("--run-id", help="check one recorded promotion run")
    check.add_argument("--json", action="store_true", dest="json_output")
    migrate = sub.add_parser("migrate-catalogue")
    migrate.add_argument("--ableton-root", type=Path, required=True)
    migrate.add_argument("--manifest", type=Path, required=True)
    migrate.add_argument("--undo", type=Path, required=True)
    migrate.add_argument("--apply", action="store_true")
    prepare = sub.add_parser("prepare")
    prepare.add_argument("--output-dir", type=Path, required=True)
    prepare.add_argument("--quotas", type=Path, help="TOML [quotas] collection targets")
    playlists = sub.add_parser("playlists")
    playlists.add_argument("--labels", type=Path, required=True)
    classify = sub.add_parser("classify-packet")
    classify.add_argument("--labels", type=Path, required=True)
    classify.add_argument("--benchmark", type=Path, required=True)
    classify.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE, help='audio files per committed batch (1–8; default 2)')
    classify.add_argument('--threads', type=int, default=DEFAULT_THREADS, help='CPU threads per model worker (default 2)')
    classify.add_argument('--worker-timeout', type=float, default=DEFAULT_TIMEOUT, help='seconds per model worker, including load (default 300); completed batches survive a timeout')
    review_state = classify.add_mutually_exclusive_group()
    review_state.add_argument("--restart-review", action="store_true")
    review_state.add_argument("--carry-review", action="store_true")
    packet_review = sub.add_parser("review-packet")
    packet_review.add_argument("--labels", type=Path, required=True)
    packet_review.add_argument("--port", type=int, default=0)
    packet_review.add_argument("--open", action="store_true", dest="open_browser")
    validate = sub.add_parser("validate")
    validate.add_argument("--labels", type=Path, required=True)
    promote = sub.add_parser("promote")
    promote.add_argument("--labels", type=Path, required=True)
    promote.add_argument("--run-id", required=True)
    views = sub.add_parser("views")
    views.add_argument("--labels", type=Path, required=True)
    views.add_argument("--output-dir", type=Path, required=True)
    views.add_argument("--quotas", type=Path, help="TOML [quotas] collection targets")
    views.add_argument("--name", default="foundation-v1", help="crate filename prefix")
    undo_promotion = sub.add_parser("undo-promotion")
    undo_promotion.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)
    args.root = config.require_root(args.root or config.SAMPLES_ROOT, parser)
    packet_root_override = args.root
    try:
        args.library_db = resolve_library_db(args.root, args.library_db)
    except (ValueError, OSError) as exc:
        if args.command == 'check' and args.json_output:
            print(json.dumps({'error': str(exc)}))
        else:
            print(str(exc), file=sys.stderr)
        return 2
    if args.command == "check":
        try:
            report = check_promotions(args.root, args.library_db, args.run_id)
        except HealthCheckError as exc:
            if args.json_output:
                print(json.dumps({"error": str(exc)}))
            else:
                print(str(exc), file=sys.stderr)
            return 2
        print(json.dumps(report.to_dict(), indent=2) if args.json_output else report.text())
        return report.exit_code
    try:
        quotas = load_quotas(args.quotas) if args.command in {"prepare", "views"} else None
        if args.command == "views":
            validate_crate_name(args.name)
        if args.command == "playlists":
            paths = regenerate_packet_playlists(args.labels, **({"root": packet_root_override} if packet_root_override is not None else {}))
            categories = len(paths) - 2  # combined playlist and index are not categories
            print(f"category playlists: {categories} -> {args.labels.parent / 'playlists'}")
            return 0
        if args.command == "review-packet":
            metadata = json.loads((args.labels.parent / "packet-meta.json").read_text(encoding="utf-8"))
            session_root = packet_root(metadata, packet_root_override)
            with library_lock(session_root, purpose="review listening packet"):
                root, session, candidates = load_review_packet(args.labels, root=session_root)
                serve_review(root, session, candidates, port=args.port, open_browser=args.open_browser)
            return 0
        if not args.library_db.is_file():
            raise ValueError('no library index; initialise or migrate existing history first')
        db = LibraryDatabase(args.library_db)
        db.bind_root(args.root, create=False)
        if args.command == "classify-packet":
            with library_lock(args.root, purpose="classify listening packet"):
                classifications, score = classify_packet(
                    args.root, db, args.labels, args.benchmark,
                    restart_review=args.restart_review,
                    carry_review=args.carry_review,
                    batch_size=args.batch_size, threads=args.threads, worker_timeout=args.worker_timeout,
                )
            print(f"classified: {len(classifications)} -> {args.labels.parent / 'classification.tsv'}")
            metadata_path = args.labels.parent / "packet-meta.json"
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            review = metadata.get("review")
            if metadata.get("schema_version", 0) >= 3 and (
                not isinstance(review, dict)
                or not review.get("ready")
                or not review.get("passed")
            ):
                unresolved = review.get("unresolved", "unknown") if isinstance(review, dict) else "unknown"
                suffix = "" if unresolved == 1 else "s"
                print(f"review awaiting {unresolved} ear check{suffix}: sample-curate review-packet")
                return 3
            if not score.ready:
                print(f"benchmark awaiting ear labels: {args.benchmark}")
                return 3
            print(
                f"benchmark: form {score.form_correct}/{score.total}; "
                f"content {score.content_correct}/{score.total}; "
                f"group {score.group_correct}/{score.total}; "
                f"content+group {score.content_group_correct}/{score.total}"
            )
            if not score.passed:
                print("benchmark gate failed; playlists were not regenerated", file=sys.stderr)
                return 3
            print("quality gate passed; run `sample-curate playlists --labels ...` to publish")
        elif args.command == "migrate-catalogue":
            plan = plan_catalogue_migration(args.root, args.ableton_root, db)
            moves.write_plan(args.manifest, plan)
            print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] migration: {len(plan)} moves")
            if args.apply:
                print(apply_migration(args.root, plan, args.undo))
        elif args.command == "prepare":
            count = prepare_packet(args.root, db, args.output_dir, quotas=quotas)
            print(f"[MANIFEST-ONLY] audition candidates: {count} -> {args.output_dir}")
        elif args.command == "validate":
            rows = read_labels(args.labels)
            validate_labels(rows)
            print(f"labels valid: {len(rows)}")
        elif args.command == "promote":
            paths = promote_favourites(args.root, db, args.labels, run_id=args.run_id)
            print(f"promoted: {len(paths)}")
        elif args.command == "views":
            with library_lock(args.root, purpose="write consumer views"):
                paths = write_consumer_views(db, args.labels, args.output_dir, quotas=quotas, name=args.name)
            print(f"consumer views: {len(paths)} -> {args.output_dir}")
        elif args.command == "undo-promotion":
            count = undo_promotions(args.root, db, args.run_id)
            print(f"quarantined promoted copies: {count}")
        return 0
    except (CurationError, CurationPolicyError, PacketClassifierError, ValueError, sqlite3.Error, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
