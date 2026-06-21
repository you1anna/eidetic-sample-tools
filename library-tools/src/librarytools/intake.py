"""Folder-level intake: route stray vendor packs into PACKS/ with clean names.

Whole packs stay whole — only the top folder is moved and renamed. Reuses
librarytools.moves for never-overwrite, undo-logged, dry-run-by-default moves.
"""

from __future__ import annotations

import re

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
