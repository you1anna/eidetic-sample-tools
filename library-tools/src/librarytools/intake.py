"""Folder-level intake: route stray vendor packs into PACKS/ with clean names.

Whole packs stay whole — only the top folder is moved and renamed. Reuses
librarytools.moves for never-overwrite, undo-logged, dry-run-by-default moves.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from . import config, moves, review

# Scene-release groups, format markers, and noise tokens dropped from pack names.
_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "multiformat", "multi", "wav", "flac", "aiff", "aif", "scd", "mp3",
        "samples", "sample", "decibel", "pack",
    }
)
# Release-ID shapes like "dcb-5289" (catalogue numbers) — stripped before tokenizing.
_RELEASE_ID = re.compile(r"[a-z]{2,4}-\d{3,6}")
# A bare numeric token left after tokenizing is also noise.
_BARE_NUM = re.compile(r"\d{3,6}")


def normalize_pack_name(raw: str) -> str:
    """Lowercase, drop scene/format/release noise, hyphenate, collapse, trim."""
    lowered = _RELEASE_ID.sub(" ", raw.lower())
    # Split on any run of separators (., space, _, -).
    tokens = [t for t in re.split(r"[.\s_-]+", lowered) if t]
    kept = [t for t in tokens if t not in _NOISE_TOKENS and not _BARE_NUM.fullmatch(t)]
    slug = "-".join(kept)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug


# Top-level names that are structure, not stray packs.
KNOWN_TOP: frozenset[str] = (
    frozenset(review.ROLE_FOLDERS)        # legacy top-level role folders + _REVIEW
    | frozenset(config.DEDUPE_EXCLUDE)    # _EXPORT, _TO-DELETE, _QUARANTINE
    | {"MIDI", "00_INBOX", "_PACKS", "CURATED", "PACKS"}
)


def is_pack_folder(path: Path) -> bool:
    """True if path is a directory containing at least one audio file (recursive)."""
    if not path.is_dir():
        return False
    for p in path.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in config.SOURCE_EXTS:
            return True
    return False


def _unique_dest(dest: Path, claimed: set[Path]) -> Path:
    """dest, or a -N variant if it exists on disk or is already claimed this run."""
    if dest not in claimed and not dest.exists():
        return dest
    n = 2
    while True:
        cand = dest.with_name(f"{dest.name}-{n}")
        if cand not in claimed and not cand.exists():
            return cand
        n += 1


def build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]:
    """Plan a move for every stray top-level pack folder into PACKS/<slug>."""
    plan: list[moves.Move] = []
    claimed: set[Path] = set()
    packs_root = root / "PACKS"
    for entry in sorted(root.iterdir()):
        if entry.name in KNOWN_TOP or entry.name.startswith("."):
            continue
        if not is_pack_folder(entry):
            continue
        slug = normalize_pack_name(entry.name) or "pack"
        dest = _unique_dest(packs_root / slug, claimed)
        claimed.add(dest)
        plan.append(moves.Move(entry, dest, f"pack|{entry.name}"))
    return plan


def record_manifest(plan: list[moves.Move], packs_root: Path) -> None:
    """Append slug<TAB>original<TAB>date for each planned pack (for traceability)."""
    if not plan:
        return
    packs_root.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    with (packs_root / "_manifest.tsv").open("a", encoding="utf-8") as fh:
        for m in plan:
            original = m.tag.split("|", 1)[1]
            fh.write(f"{m.dest.name}\t{original}\t{today}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-intake",
        description="Route stray vendor packs into PACKS/ with clean names (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root)
    manifest = config.manifest_path("intake")
    moves.write_plan(manifest, plan)
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] intake {args.root}")
    print(f"  stray packs: {len(plan)}")
    for m in plan:
        print(f"    {m.tag.split('|', 1)[1]}  ->  PACKS/{m.dest.name}")
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move packs)")
        return 0

    undo = config.manifest_path("undo-intake")
    counts = moves.apply_plan(plan, undo)
    record_manifest(plan, args.root / "PACKS")
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
