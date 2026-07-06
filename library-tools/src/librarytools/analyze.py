"""Read-only sample intelligence pilot outputs.

Phase 1 indexes sources and writes inspectable manifests. It does not move,
delete, rewrite, or convert samples.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from . import config, probe, review

AUDIO_EXTS: frozenset[str] = config.SOURCE_EXTS
DOC_EXTS: frozenset[str] = frozenset({".pdf", ".txt", ".md", ".rtf", ".nfo", ".url"})


@dataclass(frozen=True)
class OtSet:
    set_name: str
    project_root: Path
    audio_pool_root: Path
    project_file_count: int
    strd_file_count: int
    audio_file_count: int
    doc_path: Path | None
    inferred_device: str = "octatrack"
    handling_policy: str = "preserve-set"


@dataclass(frozen=True)
class SourceRow:
    path: Path
    source_kind: str
    source_name: str
    processing_tag: str
    processing_reason: str


@dataclass(frozen=True)
class FeatureRow:
    path: Path
    source_kind: str
    source_name: str
    role: str
    sample_type: str
    bpm: str
    key: str
    tempo_fit: str
    duration: float | None
    proposed_name: str
    review_reason: str
    processing_tag: str
    processing_reason: str
    character_tags: str
    tag_reasons: str


@dataclass(frozen=True)
class CrateEntry:
    path: Path
    reason: str


def _is_ignored(path: Path) -> bool:
    return any(part.startswith("._") or part in {".DS_Store", "__MACOSX"} for part in path.parts)


def _is_staging(path: Path) -> bool:
    return path.parts[:1] in {
        ("_EXPORT",),
        ("_TO-DELETE",),
        ("_QUARANTINE",),
    }


def _rel(path: Path, root: Path) -> Path:
    return path.relative_to(root)


def _first_doc(path: Path, root: Path) -> Path | None:
    docs = sorted(
        p for p in path.rglob("*")
        if p.is_file() and not _is_ignored(_rel(p, root)) and p.suffix.lower() in DOC_EXTS
    )
    return _rel(docs[0], root) if docs else None


def _audio_count(path: Path, root: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(
        1 for p in path.rglob("*")
        if p.is_file() and not _is_ignored(_rel(p, root)) and p.suffix.lower() in AUDIO_EXTS
    )


def _candidate_dirs(root: Path) -> list[Path]:
    dirs: set[Path] = set()
    for base_name in ("PACKS", "_PACKS"):
        base = root / base_name
        if not base.is_dir():
            continue
        for project_file in base.rglob("project.work"):
            if project_file.is_file() and not _is_ignored(_rel(project_file, root)):
                dirs.add(project_file.parent)
    for project_file in root.glob("*/project.work"):
        if project_file.is_file() and not _is_ignored(_rel(project_file, root)):
            dirs.add(project_file.parent)
    return sorted(dirs)


def detect_ot_sets(root: Path) -> list[OtSet]:
    """Detect Octatrack Sets under the sample root without mutating anything."""
    sets: list[OtSet] = []
    for project_root in _candidate_dirs(root):
        audio_pool = project_root / "AUDIO"
        audio_file_count = _audio_count(audio_pool, root)
        project_files = sorted(
            p for p in project_root.rglob("*.work")
            if p.is_file() and not _is_ignored(_rel(p, root))
        )
        strd_files = sorted(
            p for p in project_root.rglob("*.strd")
            if p.is_file() and not _is_ignored(_rel(p, root))
        )
        sets.append(
            OtSet(
                set_name=project_root.name,
                project_root=_rel(project_root, root),
                audio_pool_root=_rel(audio_pool, root),
                project_file_count=len(project_files),
                strd_file_count=len(strd_files),
                audio_file_count=audio_file_count,
                doc_path=_first_doc(project_root, root),
            )
        )
    return sets


def parse_processing_suffix(path: Path) -> tuple[str, str]:
    """Map Caught-on-Tape style suffixes to inspectable processing tags."""
    suffixes = {
        "Orig": "original",
        "Tape": "tape",
        "TapeSat": "tape-saturated",
        "X": "processed",
        "X2": "processed-more",
    }
    stem = path.stem
    for suffix, tag in sorted(suffixes.items(), key=lambda item: len(item[0]), reverse=True):
        if stem.endswith(f"_{suffix}") or stem.endswith(f"-{suffix}") or stem.endswith(f" {suffix}"):
            return tag, f"filename_suffix:{suffix}"
    return "", ""


def _source_name(rel: Path) -> str:
    if len(rel.parts) >= 2 and rel.parts[0] in {"PACKS", "_PACKS"}:
        return rel.parts[1]
    if len(rel.parts) >= 2 and rel.parts[0] == "CURATED":
        return "CURATED"
    return rel.parts[0] if rel.parts else ""


def _ot_set_for(rel: Path, ot_sets: list[OtSet]) -> OtSet | None:
    rel_text = rel.as_posix()
    for ot_set in ot_sets:
        root_text = ot_set.project_root.as_posix()
        if rel_text == root_text or rel_text.startswith(f"{root_text}/"):
            return ot_set
    return None


def _source_kind(rel: Path, ot_sets: list[OtSet]) -> str | None:
    if _is_ignored(rel) or _is_staging(rel):
        return None
    ot_set = _ot_set_for(rel, ot_sets)
    suffix = rel.suffix.lower()
    if ot_set and suffix in {".work", ".strd"}:
        return "octatrack-set-project"
    if ot_set and rel.as_posix().startswith(f"{ot_set.audio_pool_root.as_posix()}/") and suffix in AUDIO_EXTS:
        return "octatrack-set-audio"
    if suffix in DOC_EXTS:
        return "document"
    if suffix not in AUDIO_EXTS:
        return None
    if rel.parts[:1] == ("CURATED",):
        return "curated-sample"
    if rel.parts[:1] in {("PACKS",), ("_PACKS",)}:
        return "vendor-pack-audio"
    return None


def build_source_registry(root: Path, ot_sets: list[OtSet]) -> list[SourceRow]:
    rows: list[SourceRow] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = _rel(path, root)
        kind = _source_kind(rel, ot_sets)
        if not kind:
            continue
        processing_tag, processing_reason = parse_processing_suffix(rel)
        rows.append(
            SourceRow(
                path=rel,
                source_kind=kind,
                source_name=_source_name(rel),
                processing_tag=processing_tag,
                processing_reason=processing_reason,
            )
        )
    return rows


def write_source_registry(path: Path, rows: list[SourceRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "source_kind",
            "source_name",
            "processing_tag",
            "processing_reason",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.source_kind,
                row.source_name,
                row.processing_tag,
                row.processing_reason,
            ])


def _is_sample_source(row: SourceRow) -> bool:
    return row.source_kind in {"curated-sample", "vendor-pack-audio", "octatrack-set-audio"}


def _has(text: str, *needles: str) -> bool:
    return any(needle in text for needle in needles)


def derive_character_tags(row: FeatureRow) -> tuple[str, str]:
    tags: list[str] = []
    reasons: list[str] = []
    text = row.path.as_posix().lower().replace("_", " ").replace("-", " ")

    def add(tag: str, reason: str) -> None:
        if tag not in tags:
            tags.append(tag)
            reasons.append(reason)

    if row.role == "KICKS":
        if _has(text, "sub"):
            add("subby", "path:sub")
        if row.duration is not None and row.duration <= 0.75:
            add("short", f"duration={row.duration:.2f}s")
        if _has(text, "rumble"):
            add("rumble-long", "path:rumble")
    if row.role == "HATS-CYM":
        if _has(text, "metallic", "metal"):
            add("metallic", "path:metallic")
        if _has(text, "tight", "closed") or (row.duration is not None and row.duration <= 0.35):
            add("tight", f"duration={row.duration:.2f}s" if row.duration is not None else "path:tight")
    if row.role == "PERC":
        if _has(text, "wood", "clave", "block"):
            add("wood", "path:wood-family")
        if _has(text, "tribal", "conga", "tom", "cowbell"):
            add("tribal", "path:tribal-family")
    if row.role == "DRUM-LOOPS":
        if _has(text, "sparse"):
            add("sparse", "path:sparse")
        if _has(text, "busy"):
            add("busy", "path:busy")
        if _has(text, "top") and row.bpm:
            add(f"top-{row.bpm}", f"path:top;bpm={row.bpm}")
    if row.role == "DRONE-ATMOS":
        if _has(text, "dub", "wash"):
            add("dub-wash", "path:dub/wash")
    if row.processing_tag:
        add(row.processing_tag, row.processing_reason)

    return ";".join(tags), ";".join(reasons)


def build_feature_rows(
    root: Path,
    sources: list[SourceRow],
    probe_durations: bool = False,
) -> list[FeatureRow]:
    rows: list[FeatureRow] = []
    for source in sources:
        if not _is_sample_source(source):
            continue
        full_path = root / source.path
        duration = probe.duration(full_path) if probe_durations else None
        item = review.build_item(full_path, root, probe_durations=False)
        row = FeatureRow(
            path=source.path,
            source_kind=source.source_kind,
            source_name=source.source_name,
            role=item.role,
            sample_type=item.sample_type,
            bpm=item.bpm,
            key=item.key,
            tempo_fit=item.tempo_fit,
            duration=duration,
            proposed_name=item.proposed_name,
            review_reason=item.reason,
            processing_tag=source.processing_tag,
            processing_reason=source.processing_reason,
            character_tags="",
            tag_reasons="",
        )
        tags, reasons = derive_character_tags(row)
        rows.append(replace(row, character_tags=tags, tag_reasons=reasons))
    return rows


def write_features(path: Path, rows: list[FeatureRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path",
            "source_kind",
            "source_name",
            "role",
            "sample_type",
            "bpm",
            "key",
            "tempo_fit",
            "duration",
            "proposed_name",
            "review_reason",
            "processing_tag",
            "processing_reason",
            "character_tags",
            "tag_reasons",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(),
                row.source_kind,
                row.source_name,
                row.role,
                row.sample_type,
                row.bpm,
                row.key,
                row.tempo_fit,
                f"{row.duration:.3f}" if row.duration is not None else "",
                row.proposed_name,
                row.review_reason,
                row.processing_tag,
                row.processing_reason,
                row.character_tags,
                row.tag_reasons,
            ])


def _crate_reason(row: FeatureRow) -> str:
    fields = [row.role, row.sample_type, row.character_tags]
    return ";".join(field for field in fields if field)


def _one_shot_candidate(row: FeatureRow) -> bool:
    if row.role not in {"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC"}:
        return False
    if row.sample_type != "one-shot":
        return False
    return row.duration is None or row.duration <= 3.0


def _entry(row: FeatureRow) -> CrateEntry:
    return CrateEntry(row.path, _crate_reason(row))


def build_crates(
    rows: list[FeatureRow],
    ot_sets: list[OtSet] | None = None,
) -> dict[str, list[CrateEntry]]:
    """Build small deterministic device-aware crate suggestions."""
    sorted_rows = sorted(rows, key=lambda row: row.path.as_posix())
    one_shots = [_entry(row) for row in sorted_rows if _one_shot_candidate(row)]
    crates: dict[str, list[CrateEntry]] = {
        "digitakt/punchy-techno-kit.txt": one_shots[:32],
        "tr8s/909-plus-weird-perc.txt": one_shots[:64],
        "ableton/dub-techno-favourites.txt": [_entry(row) for row in sorted_rows[:96]],
        "octatrack/dub-loop-bed-132.txt": [
            _entry(row)
            for row in sorted_rows
            if row.source_kind == "octatrack-set-audio"
            or row.role in {"DRUM-LOOPS", "DRONE-ATMOS", "SYNTH-STAB-CHORD", "FX-RISE-IMPACT"}
        ][:64],
    }
    for ot_set in sorted(ot_sets or [], key=lambda item: item.project_root.as_posix()):
        slug = review.normalise_token(ot_set.set_name)
        crates[f"octatrack/{slug}-set.txt"] = [
            CrateEntry(ot_set.project_root, "install-as-set;preserve-set")
        ]
    return crates


def write_crates(output_dir: Path, crates: dict[str, list[CrateEntry]]) -> None:
    crate_root = output_dir / "crates"
    for name, entries in sorted(crates.items()):
        path = crate_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as fh:
            fh.write(f"# generated by sample-analyze: {name}\n")
            for entry in entries:
                if entry.reason:
                    fh.write(f"# {entry.reason}\n")
                fh.write(f"{entry.path.as_posix()}\n")


def write_report(
    path: Path,
    ot_sets: list[OtSet],
    sources: list[SourceRow],
    features: list[FeatureRow],
    crates: dict[str, list[CrateEntry]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    source_counts: dict[str, int] = {}
    for row in sources:
        source_counts[row.source_kind] = source_counts.get(row.source_kind, 0) + 1
    role_counts: dict[str, int] = {}
    for row in features:
        role_counts[row.role] = role_counts.get(row.role, 0) + 1

    lines = [
        "# Sample Intelligence Pilot",
        "",
        f"OT Sets: {len(ot_sets)}",
        f"Source Rows: {len(sources)}",
        f"Feature Rows: {len(features)}",
        "",
        "## Source Kinds",
    ]
    if source_counts:
        lines.extend(f"- {kind}: {count}" for kind, count in sorted(source_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Roles"])
    if role_counts:
        lines.extend(f"- {role}: {count}" for role, count in sorted(role_counts.items()))
    else:
        lines.append("- none")
    lines.extend(["", "## Crates"])
    for name, entries in sorted(crates.items()):
        lines.append(f"- {name}: {len(entries)}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_ot_sets(path: Path, sets: list[OtSet]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "set_name",
            "project_root",
            "audio_pool_root",
            "project_file_count",
            "strd_file_count",
            "audio_file_count",
            "doc_path",
            "inferred_device",
            "handling_policy",
        ])
        for item in sets:
            writer.writerow([
                item.set_name,
                item.project_root.as_posix(),
                item.audio_pool_root.as_posix(),
                item.project_file_count,
                item.strd_file_count,
                item.audio_file_count,
                item.doc_path.as_posix() if item.doc_path else "",
                item.inferred_device,
                item.handling_policy,
            ])


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
    ap.add_argument("--no-probe", action="store_true", help="skip ffprobe duration features")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    sets = detect_ot_sets(args.root)
    sources = build_source_registry(args.root, sets)
    features = build_feature_rows(args.root, sources, probe_durations=not args.no_probe)
    crates = build_crates(features, ot_sets=sets)

    write_ot_sets(args.output_dir / "ot-sets-latest.tsv", sets)
    write_source_registry(args.output_dir / "source-registry-latest.tsv", sources)
    write_features(args.output_dir / "sample-features-latest.tsv", features)
    write_crates(args.output_dir, crates)
    write_report(args.output_dir / "reports" / "pilot.md", sets, sources, features, crates)

    print(f"[MANIFEST-ONLY] sample intelligence {args.root}")
    print(f"  ot sets: {len(sets)}")
    print(f"  source rows: {len(sources)}")
    print(f"  feature rows: {len(features)}")
    print(f"  crates: {len(crates)}")
    print(f"  output dir: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
