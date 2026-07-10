"""Read-only source discovery for sample analysis."""

from __future__ import annotations

from pathlib import Path

from . import config, review
from .analyze_types import AUDIO_EXTS, DOC_EXTS, OtSet, SourceRow

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


def _first_doc(paths: list[Path], root: Path) -> Path | None:
    docs = sorted({
        p for path in paths if path.is_dir()
        for p in path.rglob("*")
        if p.is_file() and not _is_ignored(_rel(p, root)) and p.suffix.lower() in DOC_EXTS
    })
    return _rel(docs[0], root) if docs else None


def _audio_count(path: Path, root: Path) -> int:
    if not path.is_dir():
        return 0
    return sum(
        1 for p in path.rglob("*")
        if p.is_file() and not _is_ignored(_rel(p, root)) and p.suffix.lower() in AUDIO_EXTS
    )


def _candidate_sets(root: Path) -> list[tuple[Path, Path]]:
    sets: dict[Path, Path] = {}
    for project_file in root.rglob("project.work"):
        if not project_file.is_file():
            continue
        rel = _rel(project_file, root)
        if _is_ignored(rel) or _is_staging(rel):
            continue
        control_root = project_file.parent
        if (control_root / "AUDIO").is_dir():
            set_root = control_root
        elif (control_root.parent / "AUDIO").is_dir():
            set_root = control_root.parent
        else:
            set_root = control_root
        sets[set_root] = control_root
    return sorted(sets.items())


def detect_ot_sets(root: Path) -> list[OtSet]:
    """Detect Octatrack Sets under the sample root without mutating anything."""
    sets: list[OtSet] = []
    for set_root, control_root in _candidate_sets(root):
        audio_pool = set_root / "AUDIO"
        audio_file_count = _audio_count(audio_pool, root)
        project_files = sorted(
            p for p in set_root.rglob("*.work")
            if p.is_file() and not _is_ignored(_rel(p, root))
        )
        strd_files = sorted(
            p for p in set_root.rglob("*.strd")
            if p.is_file() and not _is_ignored(_rel(p, root))
        )
        sets.append(
            OtSet(
                set_name=control_root.name,
                project_root=_rel(set_root, root),
                audio_pool_root=_rel(audio_pool, root),
                project_file_count=len(project_files),
                strd_file_count=len(strd_files),
                audio_file_count=audio_file_count,
                doc_path=_first_doc([set_root, set_root.parent], root),
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
    if rel.parts and rel.parts[0] not in set(review.ROLE_FOLDERS) | set(config.DEDUPE_EXCLUDE) | {"CURATED", "MIDI"}:
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
