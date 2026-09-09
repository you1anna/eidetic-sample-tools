"""Move confidently-classified samples into their role folders (reversible).

Bridges the two halves that already exist:
  - librarytools.review  -> the role + hardware-friendly name for each file
  - librarytools.moves    -> move-only, never-overwrite, undo-logged mutations

Each in-scope file lands flat at ``<ROLE>/<proposed_name>``. Low-confidence
``_REVIEW`` files are left untouched unless ``--include-review`` is given, which
gathers them into ``_REVIEW/`` for manual triage. Dry-run by default.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path

from . import config, moves, review

# Top-level folders that are already destinations or staging — never sorted FROM.
NON_SOURCE_DIRS: frozenset[str] = (
    frozenset(review.ROLE_FOLDERS)        # KICKS, HATS-CYM, ..., _REVIEW
    | frozenset(config.DEDUPE_EXCLUDE)    # _EXPORT, _TO-DELETE, _QUARANTINE, PACKS
    | {"MIDI", "CURATED"}                 # CURATED is the role destination zone, not a source
)


def iter_sources(root: Path) -> list[Path]:
    """Audio files under every top-level folder that isn't a destination/staging dir."""
    found: list[Path] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir() or entry.name in NON_SOURCE_DIRS:
            continue
        for path in entry.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("."):  # hidden + AppleDouble (._foo)
                continue
            if path.suffix.lower() not in config.SOURCE_EXTS:
                continue
            found.append(path)
    return sorted(found)


def _unique_dest(dest: Path, claimed: set[Path]) -> Path:
    """Return dest, or a `-N`-suffixed variant if it exists on disk or is claimed.

    Resolves flat-name collisions (different files normalising to the same name)
    so every source moves instead of being skipped. Byte-identical dupes are
    handled separately by sample-dedupe, so suffixing here never loses content.
    """
    if dest not in claimed and not dest.exists():
        return dest
    n = 2
    while True:
        candidate = dest.with_name(f"{dest.stem}-{n}{dest.suffix}")
        if candidate not in claimed and not candidate.exists():
            return candidate
        n += 1


def build_plan(
    root: Path = config.SAMPLES_ROOT, include_review: bool = False
) -> list[moves.Move]:
    """Classify every in-scope file and plan a flat move into its role folder."""
    root = config.require_root(root)
    plan: list[moves.Move] = []
    claimed: set[Path] = set()
    for path in iter_sources(root):
        rel = path.relative_to(root)
        result = review.classify_role(rel)
        if result.role == "_REVIEW" and not include_review:
            continue
        name = review.proposed_name(rel, result.role)
        # Real roles live under CURATED/; _REVIEW stays a top-level staging dir.
        zone = root if result.role == "_REVIEW" else root / "CURATED"
        dest = _unique_dest(zone / result.role / name, claimed)
        claimed.add(dest)
        plan.append(moves.Move(path, dest, f"{result.role}|{result.reason}"))
    return plan


def _print_counts(plan: list[moves.Move]) -> None:
    roles = Counter(m.tag.split("|", 1)[0] for m in plan)
    print(f"  files: {len(plan)}")
    for role in review.ROLE_FOLDERS:
        if roles.get(role, 0):
            print(f"    {role:<17} {roles[role]}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-sort",
        description="Move confidently-classified samples into role folders (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument(
        "--include-review",
        action="store_true",
        help="also gather low-confidence files into _REVIEW/ for manual triage",
    )
    args = ap.parse_args(argv)
    args.root = config.require_root(args.root, ap)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root, include_review=args.include_review)
    manifest = config.manifest_path("sort", root=args.root)
    moves.write_plan(manifest, plan)
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] sort {args.root}")
    _print_counts(plan)
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move files)")
        return 0

    undo = config.manifest_path("undo-sort", root=args.root)
    counts = moves.apply_plan(plan, undo, root=args.root)
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; "
          f"missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
