"""Manifest-first near-duplicate sample review and approved staging.

This is intentionally more conservative than byte-identical `sample-dedupe`:
it writes review/audition artifacts first, then stages only rows that Robin has
marked `decision=remove` in the reviewed TSV.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config, moves

REVIEW_FIELDS = [
    "decision",
    "group_id",
    "family",
    "role",
    "sample_type",
    "keep_path",
    "candidate_path",
    "confidence",
    "score",
    "reason",
]

_REQUIRED_FLOATS = (
    "duration_s",
    "tail_ms",
    "sub_ratio",
    "low_ratio",
    "mid_ratio",
    "high_ratio",
    "centroid_hz",
    "flatness",
    "onset_density",
    "zcr",
)

_STOP_TOKENS = {
    "wav",
    "aif",
    "aiff",
    "flac",
    "mp3",
    "ogg",
    "one",
    "shot",
    "oneshot",
    "loop",
    "loops",
    "samples",
    "sample",
}

_SUFFIX_RANK = {".wav": 0, ".aif": 1, ".aiff": 1, ".flac": 2, ".mp3": 3, ".ogg": 4}


@dataclass(frozen=True)
class FeatureRow:
    path: Path
    role: str
    sample_type: str
    family: str
    duration_s: float
    tail_ms: float
    sub_ratio: float
    low_ratio: float
    mid_ratio: float
    high_ratio: float
    centroid_hz: float
    flatness: float
    onset_density: float
    zcr: float
    character_tags: str


@dataclass(frozen=True)
class NearDupeCandidate:
    path: Path
    confidence: str
    score: float
    reason: str


@dataclass(frozen=True)
class NearDupeGroup:
    group_id: str
    family: str
    role: str
    sample_type: str
    keep_path: Path
    candidates: tuple[NearDupeCandidate, ...]


def _float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def normalise_family(value: str) -> str:
    stem = Path(value).stem if value else ""
    tokens = [token for token in re.split(r"[^a-z0-9]+", stem.lower()) if token]
    useful = [token for token in tokens if token not in _STOP_TOKENS]
    return "-".join(useful or tokens)


def load_feature_rows(path: Path) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    with path.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh, delimiter="	"):
            if raw.get("audio_error"):
                continue
            values = {field: _float(raw.get(field)) for field in _REQUIRED_FLOATS}
            if any(value is None for value in values.values()):
                continue
            family = normalise_family(raw.get("proposed_name") or raw.get("path", ""))
            if not family:
                continue
            rows.append(
                FeatureRow(
                    path=Path(raw["path"]),
                    role=raw.get("role", ""),
                    sample_type=raw.get("sample_type", ""),
                    family=family,
                    duration_s=values["duration_s"],
                    tail_ms=values["tail_ms"],
                    sub_ratio=values["sub_ratio"],
                    low_ratio=values["low_ratio"],
                    mid_ratio=values["mid_ratio"],
                    high_ratio=values["high_ratio"],
                    centroid_hz=values["centroid_hz"],
                    flatness=values["flatness"],
                    onset_density=values["onset_density"],
                    zcr=values["zcr"],
                    character_tags=raw.get("character_tags", ""),
                )
            )
    return rows


def _canonical_key(row: FeatureRow) -> tuple[int, int, int, int, str]:
    curated_rank = 0 if row.path.parts and row.path.parts[0] == "CURATED" else 1
    suffix_rank = _SUFFIX_RANK.get(row.path.suffix.lower(), 9)
    return (curated_rank, suffix_rank, len(row.path.parts), len(row.path.as_posix()), row.path.as_posix())


def _ratio_distance(left: float, right: float, floor: float = 1.0) -> float:
    scale = max(abs(left), abs(right), floor)
    return abs(left - right) / scale


def _score(left: FeatureRow, right: FeatureRow) -> float:
    distances = [
        _ratio_distance(left.duration_s, right.duration_s, 0.25),
        _ratio_distance(left.tail_ms, right.tail_ms, 80.0),
        abs(left.sub_ratio - right.sub_ratio),
        abs(left.low_ratio - right.low_ratio),
        abs(left.mid_ratio - right.mid_ratio),
        abs(left.high_ratio - right.high_ratio),
        _ratio_distance(left.centroid_hz, right.centroid_hz, 200.0),
        abs(left.flatness - right.flatness),
        _ratio_distance(left.onset_density, right.onset_density, 1.0),
        abs(left.zcr - right.zcr),
    ]
    weighted = (
        distances[0] * 0.12
        + distances[1] * 0.12
        + distances[2] * 0.16
        + distances[3] * 0.10
        + distances[4] * 0.10
        + distances[5] * 0.10
        + distances[6] * 0.14
        + distances[7] * 0.06
        + distances[8] * 0.05
        + distances[9] * 0.05
    )
    return max(0.0, min(1.0, 1.0 - weighted))


def _candidate_reason(score: float) -> str:
    return f"stem-family;acoustic-score={score:.3f}"


def find_groups(rows: list[FeatureRow], *, min_score: float = 0.88) -> list[NearDupeGroup]:
    buckets: dict[tuple[str, str, str], list[FeatureRow]] = {}
    for row in rows:
        if not row.role or not row.sample_type:
            continue
        buckets.setdefault((row.role, row.sample_type, row.family), []).append(row)

    groups: list[NearDupeGroup] = []
    for (role, sample_type, family), bucket in sorted(buckets.items()):
        unique = sorted({row.path: row for row in bucket}.values(), key=_canonical_key)
        if len(unique) < 2:
            continue
        keep = min(unique, key=_canonical_key)
        candidates: list[NearDupeCandidate] = []
        for row in unique:
            if row.path == keep.path:
                continue
            score = _score(keep, row)
            if score < min_score:
                continue
            confidence = "high" if score >= 0.94 else "medium"
            candidates.append(NearDupeCandidate(row.path, confidence, score, _candidate_reason(score)))
        if candidates:
            group_id = f"{role}:{sample_type}:{family}"
            groups.append(NearDupeGroup(group_id, family, role, sample_type, keep.path, tuple(candidates)))
    return groups


def select_groups(
    groups: list[NearDupeGroup], *, family: str | None = None, limit_groups: int | None = None
) -> list[NearDupeGroup]:
    selected = sorted(groups, key=lambda group: (group.role, group.sample_type, group.family))
    if family:
        needle = normalise_family(family)
        selected = [group for group in selected if needle in group.family]
    if limit_groups is not None:
        selected = selected[: max(0, limit_groups)]
    return selected


def write_review(path: Path, groups: list[NearDupeGroup]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=REVIEW_FIELDS, delimiter="	")
        writer.writeheader()
        for group in groups:
            for candidate in group.candidates:
                writer.writerow(
                    {
                        "decision": "",
                        "group_id": group.group_id,
                        "family": group.family,
                        "role": group.role,
                        "sample_type": group.sample_type,
                        "keep_path": group.keep_path.as_posix(),
                        "candidate_path": candidate.path.as_posix(),
                        "confidence": candidate.confidence,
                        "score": f"{candidate.score:.3f}",
                        "reason": candidate.reason,
                    }
                )


def write_audition(path: Path, groups: list[NearDupeGroup], sample_root: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    m3u = path / "near-dupes.m3u"
    md = path / "near-dupes.md"
    lines = [
        "# Near-Dupe Pilot Audition",
        "",
        "Mark each candidate after listening: `keep` or `remove`. Only TSV rows marked `decision=remove` can be staged.",
        "",
    ]
    playlist: list[str] = []
    idx = 1
    for group in groups:
        for candidate in group.candidates:
            keep_abs = sample_root / group.keep_path
            candidate_abs = sample_root / candidate.path
            playlist.extend([keep_abs.as_posix(), candidate_abs.as_posix()])
            lines.extend(
                [
                    f"## {idx}. {group.family} ({group.role} / {group.sample_type})",
                    "",
                    "- [ ] decision: keep/remove",
                    f"- keep: `{keep_abs.as_posix()}`",
                    f"- candidate: `{candidate_abs.as_posix()}`",
                    f"- confidence: `{candidate.confidence}`",
                    f"- score: `{candidate.score:.3f}`",
                    f"- reason: `{candidate.reason}`",
                    "",
                ]
            )
            idx += 1
    m3u.write_text("\n".join(playlist) + ("\n" if playlist else ""), encoding="utf-8")
    md.write_text("\n".join(lines), encoding="utf-8")


def build_apply_plan(root: Path, reviewed_manifest: Path) -> list[moves.Move]:
    plan: list[moves.Move] = []
    with reviewed_manifest.open(encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh, delimiter="	"):
            if row.get("decision", "").strip().lower() != "remove":
                continue
            candidate = Path(row["candidate_path"])
            src = root / candidate
            dest = root / "_TO-DELETE" / "near-dupes" / candidate
            plan.append(moves.Move(src, dest, "near-dupe"))
    return plan


def _default_features_path() -> Path:
    return config.MANIFEST_DIR / "sample-intelligence-pilot" / "sample-features-latest.tsv"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-near-dupes",
        description="Write near-dupe review/audition manifests, then stage only reviewed rows marked decision=remove.",
    )
    ap.add_argument("--features", type=Path, default=_default_features_path(), help="sample-analyze feature TSV")
    ap.add_argument("--output-dir", type=Path, default=config.MANIFEST_DIR / "near-dupes-pilot", help="pilot output dir")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="sample library root")
    ap.add_argument("--family", help="only emit groups whose normalized family contains this text")
    ap.add_argument("--limit-groups", type=int, help="only emit the first N groups after filtering")
    ap.add_argument("--apply-manifest", type=Path, help="reviewed near-dupes TSV to stage from")
    ap.add_argument("--apply", action="store_true", help="perform approved moves from --apply-manifest (default: dry-run)")
    args = ap.parse_args(argv)

    if args.apply_manifest:
        plan = build_apply_plan(args.root, args.apply_manifest)
        manifest = config.manifest_path("near-dupes-apply")
        moves.write_plan(manifest, plan)
        staged_bytes = sum(move.src.stat().st_size for move in plan if move.src.exists())
        print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] near-dupes apply {args.apply_manifest}")
        print(f"  approved files to stage: {len(plan)}  (~{staged_bytes / 1e9:.2f} GB)")
        print(f"  plan written: {manifest}")
        if not args.apply:
            print("  (dry-run — mark TSV rows decision=remove, then re-run with --apply to stage)")
            return 0
        undo = config.manifest_path("undo-near-dupes")
        counts = moves.apply_plan(plan, undo)
        print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; missing: {counts['missing']}")
        print(f"  undo written: {undo}")
        return 0

    if not args.features.is_file():
        print(f"features TSV not found: {args.features}", file=sys.stderr)
        return 2
    rows = load_feature_rows(args.features)
    groups = select_groups(find_groups(rows), family=args.family, limit_groups=args.limit_groups)
    review_path = args.output_dir / "near-dupes-latest.tsv"
    write_review(review_path, groups)
    write_audition(args.output_dir / "audition", groups, args.root)
    candidate_count = sum(len(group.candidates) for group in groups)
    print(f"[MANIFEST-ONLY] near-dupes {args.features}")
    print(f"  groups: {len(groups)}")
    print(f"  candidates: {candidate_count}")
    print(f"  review TSV: {review_path}")
    print(f"  audition: {args.output_dir / 'audition'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
