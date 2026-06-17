"""Find byte-identical duplicate samples and stage the extras in _TO-DELETE/dupes/.

Cheap first pass groups by (size, name); only those candidate groups are hashed.
Nothing is deleted — duplicates are moved to staging for a later human sign-off.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

from . import config, moves


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_candidates(root: Path) -> dict[tuple[int, str], list[Path]]:
    """Group files by (size, lowercased basename); return only multi-member groups."""
    groups: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("._") or path.name.startswith("."):
            continue
        if path.suffix.lower() not in config.SOURCE_EXTS:
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in config.DEDUPE_EXCLUDE:
            continue
        groups[(path.stat().st_size, path.name.lower())].append(path)
    return {k: v for k, v in groups.items() if len(v) > 1}


def pick_canonical(paths: list[Path]) -> Path:
    """Keep the shallowest path; tie-break by shortest string."""
    return min(paths, key=lambda p: (len(p.parts), len(str(p))))


def build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]:
    """Confirm dupes by hash; move every non-canonical copy to _TO-DELETE/dupes/."""
    plan: list[moves.Move] = []
    dupes_root = root / "_TO-DELETE" / "dupes"
    for candidates in find_candidates(root).values():
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for p in candidates:
            by_hash[sha256(p)].append(p)
        for identical in by_hash.values():
            if len(identical) < 2:
                continue
            keep = pick_canonical(identical)
            for victim in identical:
                if victim == keep:
                    continue
                dest = dupes_root / victim.relative_to(root)
                plan.append(moves.Move(victim, dest, "dupe"))
    return plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-dedupe",
        description="Stage byte-identical duplicate samples in _TO-DELETE/dupes/ (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root)
    manifest = config.manifest_path("dedupe")
    moves.write_plan(manifest, plan)
    reclaimed = sum(m.src.stat().st_size for m in plan if m.src.exists())
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] dedupe {args.root}")
    print(f"  duplicate files to stage: {len(plan)}  (~{reclaimed / 1e9:.2f} GB)")
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move dupes to _TO-DELETE/dupes/)")
        return 0

    undo = config.manifest_path("undo-dedupe")
    counts = moves.apply_plan(plan, undo)
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; "
          f"missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
