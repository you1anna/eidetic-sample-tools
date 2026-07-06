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


def _is_ignored(path: Path) -> bool:
    return any(part.startswith("._") or part in {".DS_Store", "__MACOSX"} for part in path.parts)


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
