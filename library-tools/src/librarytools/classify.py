"""Sort the messy in-scope packs into sound-type buckets (reversible).

Decision precedence (cheapest signal first):
  loop keyword  ->  pad keyword  ->  one-shot keyword  ->  duration  ->  OTHER
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

from . import config, moves, probe

_BPM_RE = re.compile(r"\d{2,3}\s?bpm")


def _has(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords)


def classify_path(rel: Path, duration: float | None = None) -> tuple[str, str]:
    """Return (bucket, reason) for a file from its path relative to SAMPLES_ROOT.

    Keywords are matched against the whole lowercased relative path, so a parent
    folder named "Techno Loops" classifies its files even if the filename is bare.
    """
    text = str(rel).lower()
    if _has(text, config.LOOP_KEYWORDS) or _BPM_RE.search(text):
        return "LOOPS", "keyword:loop"
    if _has(text, config.PAD_KEYWORDS):
        return "PADS-DRONES", "keyword:pad"
    if _has(text, config.ONESHOT_KEYWORDS):
        return "ONE-SHOTS", "keyword:oneshot"
    if duration is not None:
        if duration < config.DURATION_ONESHOT_MAX:
            return "ONE-SHOTS", f"duration:{duration:.2f}<{config.DURATION_ONESHOT_MAX}"
        return "LOOPS", f"duration:{duration:.2f}>={config.DURATION_ONESHOT_MAX}"
    return "OTHER", "unmatched"


def dest_rel(rel: Path, bucket: str) -> Path:
    """Destination relative to SAMPLES_ROOT: <bucket>/<pack>/<subpath>."""
    parts = rel.parts
    if len(parts) >= 3:
        pack = parts[1]
        sub = Path(*parts[2:])
    else:  # file directly inside a scope folder, e.g. 00_INBOX/foo.wav
        pack = "_loose"
        sub = Path(parts[-1])
    return Path(bucket) / pack / sub


def _iter_sources(root: Path) -> "list[Path]":
    found: list[Path] = []
    for scope in config.IN_SCOPE:
        base = root / scope
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.name.startswith("._") or path.name.startswith("."):
                continue
            if path.suffix.lower() not in config.SOURCE_EXTS:
                continue
            found.append(path)
    return found


def build_plan(
    root: Path = config.SAMPLES_ROOT, probe_durations: bool = True
) -> list[moves.Move]:
    """Classify every in-scope audio file into a bucket move."""
    plan: list[moves.Move] = []
    for path in _iter_sources(root):
        rel = path.relative_to(root)
        bucket, reason = classify_path(rel)
        if bucket == "OTHER" and probe_durations:
            d = probe.duration(path)
            if d is not None:
                bucket, reason = classify_path(rel, d)
        dest = root / dest_rel(rel, bucket)
        plan.append(moves.Move(path, dest, f"{bucket}|{reason}"))
    return plan


def _print_counts(plan: list[moves.Move]) -> None:
    buckets = Counter(m.tag.split("|", 1)[0] for m in plan)
    reasons = Counter(m.tag.split("|", 1)[1].split(":", 1)[0] for m in plan)
    print(f"  files: {len(plan)}")
    for b in config.BUCKETS:
        print(f"    {b:<12} {buckets.get(b, 0)}")
    print("  resolved by:")
    for r, n in sorted(reasons.items()):
        print(f"    {r:<12} {n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-classify",
        description="Sort _PACKS/DRUM-KITS/00_INBOX into sound-type buckets (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument("--no-probe", action="store_true", help="skip ffprobe duration fallback")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root, probe_durations=not args.no_probe)
    manifest = config.manifest_path("classify")
    moves.write_plan(manifest, plan)
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] classify {args.root}")
    _print_counts(plan)
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move files)")
        return 0

    undo = config.manifest_path("undo-classify")
    counts = moves.apply_plan(plan, undo)
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; "
          f"missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
