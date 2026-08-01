"""`sample-tag` — recover origin, measure acoustics, and regenerate the search index.

Read-only against audio.  Everything it writes lands in the library database or a proposal
file, and every step is idempotent, so it is safe to re-run after editing the vocabulary.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import config, features as features_mod, origin as origin_mod, tagging
from .inventory import LibraryDatabase, scan_library


def _load_locations(database: LibraryDatabase) -> list:
    return database.current_locations()


def _resolve_origins(database: LibraryDatabase, locations: list) -> dict[str, origin_mod.Origin]:
    resolved = origin_mod.resolve_library([(loc.sample_id, loc.path) for loc in locations])
    for sample_id, found in resolved.items():
        database.record_origin(
            sample_id, found.origin, found.confidence, found.method, found.token,
        )
    return resolved


def _write_proposal(
    path: Path, counts: dict[tuple[str, str], tuple[int, list[str]]], total: int,
) -> None:
    lines = [
        "# Proposed vocabulary coverage — review, then edit vocabulary.toml.",
        "#",
        f"# {total} samples considered. A rule matching 0 samples has nothing to find;",
        "# a rule matching nearly everything is probably too loose to be useful.",
        "",
    ]
    for (group, name), (count, examples) in sorted(
        counts.items(), key=lambda item: (item[0][0], -item[1][0])
    ):
        share = f"{count / total:.1%}" if total else "0%"
        lines.append(f"[{group}] {name}: {count} samples ({share})")
        for example in examples:
            lines.append(f"    {example}")
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-tag",
        description="Recover origin, measure acoustics and regenerate search tags. "
        "Never moves, renames or converts audio.",
    )
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument(
        "--library-db",
        type=Path,
        default=config.MANIFEST_DIR / "sample-library.sqlite",
        help="library index to read and update",
    )
    ap.add_argument("--vocabulary", type=Path, help="rule file (default: vocabulary.toml)")
    ap.add_argument(
        "--legacy-cache",
        type=Path,
        default=config.MANIFEST_DIR / "sample-intelligence.sqlite",
        help="path-keyed feature cache to migrate measurements from",
    )
    ap.add_argument("--rescan", action="store_true", help="walk the library before tagging")
    ap.add_argument("--skip-features", action="store_true", help="do not measure acoustics")
    ap.add_argument(
        "--apply", action="store_true", help="write tags (default is a proposal only)",
    )
    ap.add_argument(
        "--proposal",
        type=Path,
        default=config.MANIFEST_DIR / "vocabulary-proposal.txt",
        help="where to write the coverage proposal",
    )
    args = ap.parse_args(argv)

    if args.rescan and not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    try:
        rules = tagging.load_vocabulary(args.vocabulary)
    except tagging.VocabularyError as exc:
        print(f"vocabulary error: {exc}", file=sys.stderr)
        return 2

    database = LibraryDatabase(args.library_db)
    if args.rescan:
        result = scan_library(args.root, database)
        print(f"  scanned: {result.file_count} files")

    locations = _load_locations(database)
    if not locations:
        print(
            "no indexed locations; run once with --rescan to build the index",
            file=sys.stderr,
        )
        return 2
    print(f"[READ-ONLY] {len(locations)} locations from {args.library_db}")

    resolved = _resolve_origins(database, locations)
    known = sum(1 for found in resolved.values() if found.origin != origin_mod.UNKNOWN)
    print(f"  origin: {known}/{len(resolved)} resolved ({known / len(resolved):.1%})")

    if not args.skip_features:
        sync = features_mod.sync_features(
            args.root,
            database,
            [(loc.sample_id, loc.path, loc.size, loc.mtime_ns) for loc in locations],
            legacy_cache=args.legacy_cache if args.legacy_cache.is_file() else None,
        )
        print(
            f"  features: {sync.migrated} migrated, {sync.extracted} measured, "
            f"{sync.skipped} already known, {sync.failed} failed"
        )

    payloads = database.features()
    samples = []
    seen: set[str] = set()
    for loc in locations:
        if loc.sample_id in seen:
            continue
        seen.add(loc.sample_id)
        found = resolved.get(loc.sample_id)
        raw = payloads.get(loc.sample_id)
        samples.append(
            tagging.build_sample(
                loc.sample_id,
                loc.path,
                origin=found.origin if found else "",
                features=json.loads(raw) if raw else {},
            )
        )

    counts = tagging.count_rules(samples, rules)
    _write_proposal(args.proposal, counts, len(samples))
    print(f"  proposal written: {args.proposal}")

    if not args.apply:
        empty = [f"{g}/{n}" for (g, n), (count, _) in counts.items() if count == 0]
        if empty:
            print(f"  rules matching nothing: {', '.join(sorted(empty))}")
        print("  (no tags written; re-run with --apply once the proposal looks right)")
        return 0

    database.clear_tags()
    written = 0
    for sample in samples:
        tags = tagging.tags_for(sample, rules)
        if tags:
            database.record_tags(sample.sample_id, tags)
            written += len(tags)
    print(f"  tags written: {written} across {len(samples)} samples")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
