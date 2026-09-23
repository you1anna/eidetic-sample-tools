"""Manifest-only sample library review with smarter role and name suggestions."""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import config, probe
from .lexical import words_text

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

REVIEW_SKIP_TOP: frozenset[str] = (
    (frozenset(ROLE_FOLDERS) - {"_REVIEW"})
    | {"CURATED", "MIDI", "_EXPORT", "_TO-DELETE", "_QUARANTINE"}
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


def _parts_text(rel: Path) -> str:
    return " / ".join(part.lower().replace("_", " ").replace(".", " ") for part in rel.parts)


def word_pattern(needles: tuple[str, ...]) -> re.Pattern[str]:
    """Match needles as whole words in :func:`words_text` output, never inside other words.

    A ``*`` marks where a needle may continue inside a longer word: ``kick*`` also finds
    'kicks' and 'kickdrum', ``*loop`` finds 'toploop' and ``*vocal*`` finds 'leadvocals'.
    Without one, 'rim' never matches 'grime', 'hat' never matches 'what' and 'sub' never
    matches 'subtle'.
    """
    return re.compile(_needle_regex(needles))


def _needle_regex(needles: tuple[str, ...]) -> str:
    alternatives = []
    for needle in needles:
        head = r"\S*?" if needle.startswith("*") else ""
        tail = r"\S*" if needle.endswith("*") else r"(?!\S)"
        alternatives.append(head + re.escape(needle.strip("*")) + tail)
    # One word-start check per position keeps a long needle list cheap to search.
    return r"(?<!\S)(?:" + "|".join(alternatives) + ")"


_DRUM_LOOP_WORDS = word_pattern(("drum loop*", "top loop*", "beat loop*", "beats"))
_LOOP_WORDS = word_pattern(("*loop", "*loops", "groove", "grooves"))

# Checked in this order within one path part. Distinctive stems may sit inside longer
# words; short or ambiguous ones must stand alone.
_ROLE_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("KICKS", ("*bassdrum*", "bass drum*", "bdrum*", "*kick*", "bd")),
    ("CLAP-SNARE", ("*clap*", "*snare*", "rim", "rims", "rimshot*", "sd")),
    ("HATS-CYM", (
        "*hihat*", "hi hat*", "hat", "hats", "openhat*", "closedhat*", "closedhh", "openhh",
        "*cymbal*", "cym", "cyms", "ride", "rides", "crash", "crashes", "*shaker*",
    )),
    ("PERC", ("perc*", "*conga*", "*bongo*", "tom", "toms", "agogo*", "cabasa*", "cabassa*")),
    ("BASS", ("bass*", "subbass*", "sub", "subs", "reese*")),
    ("SYNTH-STAB-CHORD", (
        "synth*", "stab", "stabs", "chord*", "pluck*", "arp", "arps", "arpeggi*",
        "lead", "leads", "sh 101", "guitar*", "keys", "piano*",
    )),
    ("DRONE-ATMOS", ("drone*", "pad", "pads", "atmos*", "ambien*", "texture*", "field*")),
    ("FX-RISE-IMPACT", (
        "fx", "sfx", "impact*", "riser*", "rise", "uplifter*", "downlifter*", "sweep*",
        "swell*", "noise*",
    )),
    ("VOCALS", ("*vocal*", "vox", "voice*", "acapella*", "accapella*")),
)

# Short, ambiguous instrument codes matched ONLY as whole tokens, so 'chord'
# never hits 'ch' and 'ohio' never hits 'oh'. Drum-machine model names excluded.
ROLE_ABBREV_TOKEN: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("HATS-CYM", ("hh", "hho", "hhc", "ohh", "chh")),
    ("CLAP-SNARE", ("rs",)),
)

# Unambiguous instrument stems matched as a token PREFIX, so fused names like
# 'cowhigh' and plurals like 'Congas' still classify.
ROLE_ABBREV_PREFIX: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("PERC", (
        "cow", "clave", "cabasa", "conga", "block", "tamb", "agogo",
        "quijada", "timbale", "timb", "tabla", "triangle", "guiro",
        "maraca", "whistle",
    )),
)

# Words for a 303-style line: they hint at a role but must not outrank an instrument word
# anywhere in the path, so a vocal in an 'Acid House' pack is still a vocal. Style words
# such as 'tribal' say nothing about the sound type and are left to tags.
_ROLE_HINT_WORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("SYNTH-STAB-CHORD", ("acid",)),
    ("BASS", ("303",)),
)

_PART_RULES = tuple(
    [(role, word_pattern(needles), "path") for role, needles in _ROLE_WORDS]
    + [(role, word_pattern(codes), "token") for role, codes in ROLE_ABBREV_TOKEN]
    + [(role, word_pattern(tuple(f"{stem}*" for stem in stems)), "token")
       for role, stems in ROLE_ABBREV_PREFIX]
)
_HINT_RULES = tuple((role, word_pattern(needles)) for role, needles in _ROLE_HINT_WORDS)


_part_words = lru_cache(maxsize=65536)(words_text)


def _part_texts(rel: Path) -> list[str]:
    """Words of each path part, filename first, so the most specific evidence is read first."""
    return [_part_words(part) for part in reversed(rel.parts)]


@lru_cache(maxsize=65536)
def _part_role(text: str) -> tuple[str, str] | None:
    """Role evidence from one part's words; folder names repeat, so results are cached."""
    for role, pattern, kind in _PART_RULES:
        match = pattern.search(text)
        if match:
            return role, f"{kind}:{match.group(0)}"
    return None


def has_loop_words(rel: Path) -> bool:
    """Loop or groove named anywhere in the path, as a whole word ('Loopmasters' is not)."""
    return any(_LOOP_WORDS.search(text) for text in _part_texts(rel))


def classify_role(rel: Path, duration: float | None = None) -> RoleResult:
    """Classify an in-scope sample path into the library's role taxonomy.

    The filename is read first, then each folder outwards to the pack name, so the most
    specific evidence wins: 'Kicks & Bass/Bass/bass_01.wav' is bass, not a kick.
    """
    texts = _part_texts(rel)

    for text in texts:
        drum_loop = _DRUM_LOOP_WORDS.search(text)
        if drum_loop:
            return RoleResult("DRUM-LOOPS", "high", f"path:{drum_loop.group(0)}")

    for text in texts:
        found = _part_role(text)
        if found:
            return RoleResult(found[0], "high", found[1])

    for text in texts:
        for role, pattern in _HINT_RULES:
            hint = pattern.search(text)
            if hint:
                return RoleResult(role, "high", f"path:{hint.group(0)}")

    if any(_LOOP_WORDS.search(text) for text in texts) or _BPM_RE.search(str(rel)):
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
    if has_loop_words(rel):
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
    if has_loop_words(rel) or _extract_bpm(rel):
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
    for base in sorted(root.iterdir()):
        if not base.is_dir() or base.name in REVIEW_SKIP_TOP or base.name.startswith("."):
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
    root = config.require_root(root)
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
    args.root = config.require_root(args.root, ap)

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
