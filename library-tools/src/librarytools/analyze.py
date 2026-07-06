"""Read-only sample intelligence pilot outputs.

Phase 1 indexes sources and writes inspectable manifests. It does not move,
delete, rewrite, or convert samples.
"""

from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config

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
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    sets = detect_ot_sets(args.root)
    write_ot_sets(args.output_dir / "ot-sets-latest.tsv", sets)
    print(f"[MANIFEST-ONLY] sample intelligence {args.root}")
    print(f"  ot sets: {len(sets)}")
    print(f"  output dir: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
