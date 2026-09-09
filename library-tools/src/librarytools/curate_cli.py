"""CLI for safe catalogue migration and human-gated curation."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, moves
from .curate import (
    CurationError, apply_migration, plan_catalogue_migration, prepare_packet,
    promote_favourites, read_labels, regenerate_packet_playlists, validate_labels,
    undo_promotions, write_consumer_views,
)
from .inventory import LibraryDatabase
from .curation_policy import CurationPolicyError, load_quotas, validate_crate_name
from .promotion_health import HealthCheckError, check_promotions
from .packet_classifier import PacketClassifierError, classify_packet
from .classification.review_server import load_review_packet, serve_review


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sample-curate")
    parser.add_argument("--root", type=Path, default=config.SAMPLES_ROOT)
    parser.add_argument(
        "--library-db", type=Path,
        default=config.MANIFEST_DIR / "sample-library.sqlite",
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
            paths = regenerate_packet_playlists(args.labels)
            categories = len(paths) - 2  # combined playlist and index are not categories
            print(f"category playlists: {categories} -> {args.labels.parent / 'playlists'}")
            return 0
        if args.command == "review-packet":
            root, session, candidates = load_review_packet(args.labels)
            serve_review(
                root,
                session,
                candidates,
                port=args.port,
                open_browser=args.open_browser,
            )
            return 0
        db = LibraryDatabase(args.library_db)
        if args.command == "classify-packet":
            classifications, score = classify_packet(
                args.root, db, args.labels, args.benchmark,
                restart_review=args.restart_review,
                carry_review=args.carry_review,
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
            paths = write_consumer_views(db, args.labels, args.output_dir, quotas=quotas, name=args.name)
            print(f"consumer views: {len(paths)} -> {args.output_dir}")
        elif args.command == "undo-promotion":
            count = undo_promotions(args.root, db, args.run_id)
            print(f"quarantined promoted copies: {count}")
        return 0
    except (CurationError, CurationPolicyError, PacketClassifierError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
