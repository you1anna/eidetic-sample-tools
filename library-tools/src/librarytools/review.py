"""Manifest-only sample library review with smarter role and name suggestions."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from . import config, probe

DIGITAKT_NAME_WARN = 24

ROLE_FOLDERS: tuple[str, ...] = (
    "KICKS",
    "CLAP-SNARE",
    "HATS-CYM",
    "PERC",
    "DRUM-LOOPS",
    "BASS",
    "SYNTH-STAB-CHORD",
    "DRONE-ATMOS",
    "FX-RISE-IMPACT",
    "VOCALS",
    "_REVIEW",
)

_BPM_RE = re.compile(r"(?<!\d)(\d{2,3})\s*bpm(?!\d)", re.IGNORECASE)
_BRACKET_BPM_RE = re.compile(r"\[(\d{2,3})\]")
_BARE_BPM_RE = re.compile(r"(?<![a-z0-9])([6-9]\d|1\d\d|200)(?![a-z0-9])", re.IGNORECASE)
_KEY_RE = re.compile(r"(?<![a-z])([a-g](?:#|b)?)(?:\s*(maj|min|major|minor|m))?(?![a-z])", re.IGNORECASE)
_TOKEN_SPLIT_RE = re.compile(r"[^a-z0-9#b]+")
_BAD_CHARS_RE = re.compile(r"[^a-z0-9._-]+")
_DASHES_RE = re.compile(r"-{2,}")
_USCORES_RE = re.compile(r"_{2,}")


@dataclass(frozen=True)
class RoleResult:
    role: str
    confidence: str
    reason: str


@dataclass(frozen=True)
class ReviewItem:
    source: Path
    main_category: str
    role: str
    sample_type: str
    bpm: str
    key: str
    tempo_fit: str
    proposed_path: Path
    proposed_name: str
    confidence: str
    reason: str
    warnings: str


def _contains(text: str, needles: tuple[str, ...]) -> str | None:
    for needle in needles:
        if needle in text:
            return needle
    return None


def _parts_text(rel: Path) -> str:
    return " / ".join(part.lower().replace("_", " ").replace(".", " ") for part in rel.parts)


def classify_role(rel: Path, duration: float | None = None) -> RoleResult:
    """Classify an in-scope sample path into the library's role taxonomy."""
    text = _parts_text(rel)

    drum_loop = _contains(text, ("drum loop", "drum loops", "top loop", "top loops", "beat loop", "beats"))
    if drum_loop:
        return RoleResult("DRUM-LOOPS", "high", f"path:{drum_loop}")

    role_rules: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("KICKS", ("bassdrum", "bass drum", "bdrum", "kick", "kicks", "bd ", " bd", "sa909 bd")),
        ("CLAP-SNARE", ("clap", "claps", "snare", "snares", "rim", "sd ", " sd", "sa909 sd")),
        ("HATS-CYM", ("hihat", "hi hat", "hi-hat", "closedhh", "openhh", "hat", "hats", "cymbal", "cym", "ride", "crash", "shaker")),
        ("PERC", ("perc", "percussion", "conga", "bongo", "tom", "agogo", "tribal")),
        ("BASS", ("bass", "sub", "reese", "303")),
        ("SYNTH-STAB-CHORD", ("synth", "stab", "chord", "pluck", "arp", "lead", "sh101", "acid", "guitar", "keys", "piano")),
        ("DRONE-ATMOS", ("drone", "drones", "pad", "pads", "atmos", "ambience", "ambient", "texture", "textures", "field")),
        ("FX-RISE-IMPACT", ("fx", "sfx", "impact", "riser", "rise", "uplifter", "downlifter", "sweep", "swell", "noise")),
        ("VOCALS", ("vocal", "vocals", "vox", "voice", "voices", "acapella", "accapella")),
    )
    for role, needles in role_rules:
        matched = _contains(text, needles)
        if matched:
            return RoleResult(role, "high", f"path:{matched}")

    loop = _contains(text, ("loop", "loops", "groove", "grooves"))
    if loop or _BPM_RE.search(str(rel)):
        return RoleResult("DRUM-LOOPS", "medium", "path:loop")

    if duration is not None:
        if duration < config.DURATION_ONESHOT_MAX:
            return RoleResult("_REVIEW", "low", f"duration:{duration:.2f}<oneshot")
        return RoleResult("DRUM-LOOPS", "medium", f"duration:{duration:.2f}>=oneshot")

    return RoleResult("_REVIEW", "low", "unmatched")


def normalise_token(value: str) -> str:
    """Return a lowercase hardware-friendly token."""
    s = value.strip().lower().replace("'", "")
    s = s.replace("&", "and")
    s = _BAD_CHARS_RE.sub("-", s)
    s = _DASHES_RE.sub("-", s)
    s = _USCORES_RE.sub("_", s)
    return s.strip("-_") or "sample"


def _source_token(rel: Path) -> str:
    parts = rel.parts
    if len(parts) >= 2:
        return normalise_token(parts[1])
    return "loose"


def _extract_bpm(rel: Path) -> str | None:
    text = str(rel)
    match = _BPM_RE.search(text) or _BRACKET_BPM_RE.search(text)
    if match:
        return match.group(1)
    if _contains(_parts_text(rel), ("loop", "loops", "groove", "grooves")):
        bare = _BARE_BPM_RE.search(text)
        if bare:
            return bare.group(1)
    return None


def _extract_key(stem: str) -> str | None:
    for match in _KEY_RE.finditer(stem):
        token = match.group(1)
        quality = match.group(2)
        if len(token) == 1 and not quality:
            continue
        suffix = "m" if quality and quality.lower() in {"m", "min", "minor"} else ""
        return f"{token.replace('#', 's').lower()}{suffix}"
    return None


def sample_type(rel: Path, main_category: str, duration: float | None = None) -> str:
    """Return loop/one-shot/texture/unknown without changing the main category."""
    text = _parts_text(rel)
    if _contains(text, ("loop", "loops", "groove", "grooves")) or _extract_bpm(rel):
        return "loop"
    if main_category == "DRONE-ATMOS":
        return "texture"
    if duration is not None and duration < config.DURATION_ONESHOT_MAX:
        return "one-shot"
    if main_category in {"KICKS", "CLAP-SNARE", "HATS-CYM", "PERC", "FX-RISE-IMPACT", "VOCALS"}:
        return "one-shot"
    return "unknown"


def tempo_fit(bpm: str) -> str:
    """Tag tempo suitability for techno without rejecting lower-BPM material."""
    if not bpm:
        return "unknown"
    value = int(bpm)
    if 130 <= value <= 150:
        return "techno-core"
    if 124 <= value <= 129:
        return "techno-adjacent"
    if value < 124:
        return "house-lower"
    return "too-fast"


def _description(stem: str) -> str:
    cleaned = _BARE_BPM_RE.sub("", _BRACKET_BPM_RE.sub("", _BPM_RE.sub("", stem)))
    cleaned = re.sub(
        r"\bin\s+[a-g](?:#|b)?\s*(?:maj|min|major|minor|m)?\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(
        r"\b[a-g](?:#|b)?\s*(?:maj|min|major|minor|m)\b",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    words = [
        token
        for token in _TOKEN_SPLIT_RE.split(cleaned.lower())
        if token and token not in {"bpm", "wav", "aif", "aiff", "flac", "mp3", "ogg"}
    ]
    return normalise_token("-".join(words))


def _drop_role_prefix(desc: str, prefix: str) -> str:
    for token in prefix.split("-"):
        if desc == token:
            return "sample"
        if desc.startswith(f"{token}-"):
            return desc[len(token) + 1 :]
    return desc


def proposed_name(rel: Path, role: str) -> str:
    """Suggest a conservative hardware-friendly filename, preserving extension."""
    source = _source_token(rel)
    stem = rel.stem
    desc = _description(stem)
    ext = rel.suffix.lower()
    if role == "DRUM-LOOPS" or "loop" in _parts_text(rel):
        fields = [field for field in (_extract_bpm(rel), _extract_key(stem), desc, source) if field]
        return f"{normalise_token('_'.join(fields))}{ext}"
    prefix = {
        "KICKS": "kick",
        "CLAP-SNARE": "clap-snare",
        "HATS-CYM": "hat-cym",
        "PERC": "perc",
        "BASS": "bass",
        "SYNTH-STAB-CHORD": "synth-stab",
        "DRONE-ATMOS": "drone-atmos",
        "FX-RISE-IMPACT": "fx",
        "VOCALS": "vocal",
    }.get(role, "review")
    desc = _drop_role_prefix(desc, prefix)
    return f"{normalise_token(f'{prefix}-{desc}_{source}')}{ext}"


def _iter_sources(root: Path) -> list[Path]:
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
    return sorted(found)


def build_item(path: Path, root: Path, probe_durations: bool = False) -> ReviewItem:
    rel = path.relative_to(root)
    duration = None
    result = classify_role(rel)
    if result.role == "_REVIEW" and probe_durations:
        duration = probe.duration(path)
        result = classify_role(rel, duration)
    main_category = result.role
    bpm = _extract_bpm(rel) or ""
    key = _extract_key(rel.stem) or ""
    kind = sample_type(rel, main_category, duration)
    fit = tempo_fit(bpm)
    name = proposed_name(rel, result.role)
    warnings = []
    if len(name) > DIGITAKT_NAME_WARN:
        warnings.append(f"digitakt-name>{DIGITAKT_NAME_WARN}")
    dest = Path(result.role) / _source_token(rel) / name
    return ReviewItem(
        source=rel,
        main_category=main_category,
        role=result.role,
        sample_type=kind,
        bpm=bpm,
        key=key,
        tempo_fit=fit,
        proposed_path=dest,
        proposed_name=name,
        confidence=result.confidence,
        reason=result.reason,
        warnings=";".join(warnings),
    )


def build_review(root: Path = config.SAMPLES_ROOT, probe_durations: bool = False) -> list[ReviewItem]:
    """Build a manifest-only review of in-scope files. Does not move or rename."""
    return [build_item(path, root, probe_durations=probe_durations) for path in _iter_sources(root)]


def write_manifest(path: Path, items: list[ReviewItem]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "source",
            "main_category",
            "role",
            "sample_type",
            "bpm",
            "key",
            "tempo_fit",
            "proposed_path",
            "proposed_name",
            "confidence",
            "reason",
            "warnings",
        ])
        for item in items:
            writer.writerow([
                item.source.as_posix(),
                item.main_category,
                item.role,
                item.sample_type,
                item.bpm,
                item.key,
                item.tempo_fit,
                item.proposed_path.as_posix(),
                item.proposed_name,
                item.confidence,
                item.reason,
                item.warnings,
            ])


def write_split_indexes(root: Path, items: list[ReviewItem]) -> None:
    """Write grouped manifest indexes for later curation tooling. Does not move files."""
    high_root = root / "high-confidence"
    tempo_root = root / "tempo"
    for role in ROLE_FOLDERS:
        if role == "_REVIEW":
            continue
        selected = [item for item in items if item.main_category == role and item.confidence == "high"]
        if selected:
            write_manifest(high_root / f"{role}.tsv", selected)
    for fit in ("techno-core", "techno-adjacent", "house-lower", "too-fast", "unknown"):
        selected = [item for item in items if item.tempo_fit == fit]
        if selected:
            write_manifest(tempo_root / f"{fit}.tsv", selected)
    review_needed = [item for item in items if item.main_category == "_REVIEW" or item.confidence == "low"]
    write_manifest(root / "review-needed.tsv", review_needed)


def print_summary(items: list[ReviewItem]) -> None:
    roles = Counter(item.role for item in items)
    types = Counter(item.sample_type for item in items)
    tempos = Counter(item.tempo_fit for item in items)
    confidence = Counter(item.confidence for item in items)
    warnings = Counter(w for item in items for w in item.warnings.split(";") if w)
    print(f"  files: {len(items)}")
    for role in ROLE_FOLDERS:
        if roles.get(role, 0):
            print(f"    {role:<17} {roles[role]}")
    print("  confidence:")
    for name, count in sorted(confidence.items()):
        print(f"    {name:<17} {count}")
    print("  sample type:")
    for name, count in sorted(types.items()):
        print(f"    {name:<17} {count}")
    print("  tempo fit:")
    for name, count in sorted(tempos.items()):
        print(f"    {name:<17} {count}")
    if warnings:
        print("  warnings:")
        for name, count in sorted(warnings.items()):
            print(f"    {name:<17} {count}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-review",
        description="Write a manifest-only review of proposed role folders and hardware-friendly names.",
    )
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument("--output", type=Path, help="explicit TSV manifest path to write")
    ap.add_argument("--index-dir", type=Path, help="write split TSV indexes under this directory")
    ap.add_argument("--summary", action="store_true", help="print compact counts")
    ap.add_argument("--no-probe", action="store_true", help="skip ffprobe duration fallback")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    items = build_review(root=args.root, probe_durations=not args.no_probe)
    print(f"[MANIFEST-ONLY] review {args.root}")
    if args.summary or not args.output:
        print_summary(items)
    if args.output:
        write_manifest(args.output, items)
        print(f"  manifest written: {args.output}")
    if args.index_dir:
        write_split_indexes(args.index_dir, items)
        print(f"  index written: {args.index_dir}")
    if not args.output and not args.index_dir:
        print("  (no manifest written; pass --output PATH to write TSV)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
