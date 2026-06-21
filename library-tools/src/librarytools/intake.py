"""Folder-level intake: route stray vendor packs into PACKS/ with clean names.

Whole packs stay whole — only the top folder is moved and renamed. Reuses
librarytools.moves for never-overwrite, undo-logged, dry-run-by-default moves.
"""

from __future__ import annotations

import re
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
