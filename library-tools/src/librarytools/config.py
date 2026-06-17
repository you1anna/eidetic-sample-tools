"""Paths, scopes, buckets, and classification keywords.

Overridable via environment so the tool survives a different mount point:

    SAMPLES_ROOT   default: /Volumes/Extreme SSD/Production/SAMPLES
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

SAMPLES_ROOT: Path = Path(
    os.environ.get("SAMPLES_ROOT", "/Volumes/Extreme SSD/Production/SAMPLES")
)

# Top-level folders classify is allowed to read from (the messy bulk).
IN_SCOPE: tuple[str, ...] = ("_PACKS", "DRUM-KITS", "00_INBOX")

# Top-level folders dedupe never walks (staging / device exports).
DEDUPE_EXCLUDE: tuple[str, ...] = ("_EXPORT", "_TO-DELETE", "_QUARANTINE")

SOURCE_EXTS: frozenset[str] = frozenset(
    {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
)

BUCKETS: tuple[str, ...] = ("LOOPS", "ONE-SHOTS", "PADS-DRONES", "OTHER")

TO_DELETE_ROOT: Path = SAMPLES_ROOT / "_TO-DELETE"

# Generated .tsv manifests live next to the package, in the repo (gitignored).
MANIFEST_DIR: Path = Path(__file__).resolve().parents[2] / "manifests"  # parents[2] assumes src/librarytools/ layout

# Files shorter than this (seconds) classify as one-shots when no keyword matched.
DURATION_ONESHOT_MAX: float = 1.5

# Keyword sets, scanned against the lowercased relative path (folders + filename).
LOOP_KEYWORDS: tuple[str, ...] = ("loop", "lp", "groove", "bpm")
ONESHOT_KEYWORDS: tuple[str, ...] = (
    "oneshot", "one-shot", "one_shot", "one shot", "hit", "shot", "stab", "single",
)
PAD_KEYWORDS: tuple[str, ...] = (
    "pad", "drone", "atmos", "texture", "swell", "ambient",
)


def manifest_path(prefix: str) -> Path:
    """Timestamped manifest path like manifests/classify-20260617-142530.tsv."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return MANIFEST_DIR / f"{prefix}-{stamp}.tsv"
