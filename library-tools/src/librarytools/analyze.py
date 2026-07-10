"""Read-only sample intelligence pilot outputs.

Phase 1 indexes sources and writes inspectable manifests. It does not move,
delete, rewrite, or convert samples.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import classifier, config
from .inventory import LibraryDatabase, scan_library
from .profiles import ProfileError, resolve_profile
from .analyze_features import build_feature_rows, derive_character_tags
from .analyze_outputs import (
    write_clusters,
    write_crates,
    write_curated_role_conflicts,
    write_features,
    write_kick_audit,
    write_ot_sets,
    write_report,
    write_source_registry,
    add_inventory_identity,
)
from .analyze_rules import (
    build_crates,
    cluster_within_role,
    curated_role_conflict,
    curated_role_conflicts,
    kick_audit,
    kick_gate,
)
from .analyze_sources import build_source_registry, detect_ot_sets, parse_processing_suffix
from .analyze_types import (
    ClusterRow,
    CrateEntry,
    CuratedRoleConflict,
    FeatureRow,
    KickGateRow,
    OtSet,
    SourceRow,
)

__all__ = [
    "ClusterRow",
    "CrateEntry",
    "CuratedRoleConflict",
    "FeatureRow",
    "KickGateRow",
    "OtSet",
    "SourceRow",
    "build_crates",
    "build_feature_rows",
    "build_source_registry",
    "cluster_within_role",
    "curated_role_conflict",
    "curated_role_conflicts",
    "derive_character_tags",
    "detect_ot_sets",
    "kick_audit",
    "kick_gate",
    "main",
    "parse_processing_suffix",
    "write_clusters",
    "write_crates",
    "write_curated_role_conflicts",
    "write_features",
    "write_kick_audit",
    "write_ot_sets",
    "write_report",
    "write_source_registry",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-analyze",
        description="Write read-only sample intelligence pilot manifests.",
    )
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="sample library root")
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=config.MANIFEST_DIR / "sample-intelligence-pilot",
        help="directory for generated sample intelligence artifacts",
    )
    ap.add_argument("--pilot", action="store_true", help="run the phase-1 pilot output set")
    ap.add_argument(
        "--classifier",
        action="store_true",
        help=(
            "vote every CURATED file with the drum-role classifier and write "
            "role-audit-latest.tsv (needs local weights at config.DRUM_MODEL_PATH). "
            "Runs on its own unless --pilot is also given."
        ),
    )
    ap.add_argument(
        "--feature-cache",
        type=Path,
        default=config.MANIFEST_DIR / "sample-intelligence.sqlite",
        help="SQLite cache for acoustic sample features",
    )
    ap.add_argument(
        "--no-probe",
        action="store_true",
        help="skip ffprobe duration and acoustic audio feature extraction",
    )
    ap.add_argument("--profile", help="portable studio profile name")
    ap.add_argument(
        "--library-db",
        type=Path,
        help="write stable SHA-256 inventory to this new SQLite database",
    )
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    try:
        resolve_profile(args.profile)
    except ProfileError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    inventory_db: LibraryDatabase | None = None
    inventory_scan = None
    inventory_drift: tuple[int, int] | None = None
    if args.library_db:
        inventory_db = LibraryDatabase(args.library_db)
        inventory_scan = scan_library(args.root, inventory_db)
        previous_manifest = args.output_dir / "sample-features-latest.tsv"
        previous_paths: set[str] = set()
        if previous_manifest.is_file():
            with previous_manifest.open(encoding="utf-8", newline="") as fh:
                reader = csv.DictReader(fh, delimiter="\t")
                if reader.fieldnames and "path" in reader.fieldnames:
                    previous_paths = {row["path"] for row in reader}
        current_paths = {item.path.as_posix() for item in inventory_db.current_locations()}
        if previous_paths:
            inventory_drift = (
                len(previous_paths - current_paths), len(current_paths - previous_paths)
            )

    if args.classifier:
        if not classifier.available():
            print(
                "classifier unavailable: install the 'classifier' extra (torch+librosa) and "
                f"place weights at {config.DRUM_MODEL_PATH}",
                file=sys.stderr,
            )
            if not args.pilot:
                return 3
        else:
            audit = classifier.build_role_audit(args.root)
            out_path = args.output_dir / "role-audit-latest.tsv"
            classifier.write_role_audit(out_path, audit)
            print(f"[MANIFEST-ONLY] drum-role audit: {len(audit)} rows -> {out_path}")
            for line in classifier.summarise_role_audit(audit):
                print(f"  {line}")
        if not args.pilot:
            return 0

    sets = detect_ot_sets(args.root)
    sources = build_source_registry(args.root, sets)
    features = build_feature_rows(
        args.root,
        sources,
        probe_durations=not args.no_probe,
        audio_features=not args.no_probe,
        cache_path=args.feature_cache,
    )
    curated_conflicts = curated_role_conflicts(features)
    kick_audit_rows = kick_audit(features)
    clusters = cluster_within_role(features)
    crates = build_crates(features, ot_sets=sets, clusters=clusters)

    write_ot_sets(args.output_dir / "ot-sets-latest.tsv", sets)
    write_source_registry(args.output_dir / "source-registry-latest.tsv", sources)
    write_features(args.output_dir / "sample-features-latest.tsv", features)
    write_curated_role_conflicts(args.output_dir / "curated-role-conflicts-latest.tsv", curated_conflicts)
    write_kick_audit(args.output_dir / "kick-audit-latest.tsv", kick_audit_rows)
    write_clusters(args.output_dir / "clusters-latest.tsv", clusters)
    write_crates(args.output_dir, crates)
    write_report(
        args.output_dir / "reports" / "pilot.md",
        sets,
        sources,
        features,
        crates,
        clusters,
        curated_conflicts,
        kick_audit_rows=kick_audit_rows,
    )

    if inventory_db is not None and inventory_scan is not None:
        for manifest in (
            args.output_dir / "source-registry-latest.tsv",
            args.output_dir / "sample-features-latest.tsv",
            args.output_dir / "curated-role-conflicts-latest.tsv",
            args.output_dir / "kick-audit-latest.tsv",
            args.output_dir / "clusters-latest.tsv",
        ):
            add_inventory_identity(manifest, inventory_db, inventory_scan.scan_id)

    print(f"[MANIFEST-ONLY] sample intelligence {args.root}")
    print(f"  ot sets: {len(sets)}")
    print(f"  source rows: {len(sources)}")
    print(f"  feature rows: {len(features)}")
    print(f"  curated role conflicts: {len(curated_conflicts)}")
    print(f"  KICKS audit rows: {len(kick_audit_rows)}")
    print(f"  clusters: {len(clusters)}")
    print(f"  crates: {len(crates)}")
    print(f"  output dir: {args.output_dir}")
    if inventory_scan is not None:
        print(f"  inventory scan: {inventory_scan.scan_id} ({inventory_scan.file_count} audio files)")
    if inventory_drift is not None:
        print(
            f"  inventory path drift — previous-only: {inventory_drift[0]}; "
            f"current-only: {inventory_drift[1]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
