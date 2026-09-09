"""Paths, scopes, buckets, and classification keywords.

Overridable via environment so the tool survives a different mount point:

    SAMPLES_ROOT   required unless --root is supplied
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

SAMPLES_ROOT = Path(os.environ['SAMPLES_ROOT']).expanduser() if os.environ.get('SAMPLES_ROOT', '').strip() else None


def require_root(root: Path | None, parser=None) -> Path:
    if root is None:
        message = 'No sample library selected; pass --root PATH or set SAMPLES_ROOT.'
        if parser is not None:
            parser.error(message)
        raise ValueError(message)
    return Path(root).expanduser()

# Two-zone model: CURATED/ = role folders (renamed by convention);
# PACKS/ = whole vendor packs kept intact.
CURATED_ROOT = SAMPLES_ROOT / "CURATED" if SAMPLES_ROOT else None
PACKS_ROOT = SAMPLES_ROOT / "PACKS" if SAMPLES_ROOT else None

# Top-level folders classify is allowed to read from (the messy bulk).
IN_SCOPE: tuple[str, ...] = ("_PACKS", "DRUM-KITS", "00_INBOX")

# Top-level folders dedupe never walks (staging / device exports / whole packs).
# PACKS is excluded so vendor packs stay pristine and whole — a curated copy of a
# pack file is a deliberate promotion, not a duplicate to remove.
DEDUPE_EXCLUDE: tuple[str, ...] = ("_EXPORT", "_TO-DELETE", "_QUARANTINE", "PACKS")

SOURCE_EXTS: frozenset[str] = frozenset(
    {".wav", ".aif", ".aiff", ".flac", ".mp3", ".ogg"}
)

BUCKETS: tuple[str, ...] = ("LOOPS", "ONE-SHOTS", "PADS-DRONES", "OTHER")

TO_DELETE_ROOT = SAMPLES_ROOT / "_TO-DELETE" if SAMPLES_ROOT else None

# Historical state is discovered explicitly; it must never silently compete with
# portable state on the sample drive.
LEGACY_MANIFEST_DIR: Path = Path(__file__).resolve().parents[2] / "manifests"
MANIFEST_DIR = SAMPLES_ROOT / '.eidetic' / 'runs' if SAMPLES_ROOT else None

# Optional drum-role classifier weights. USER-SUPPLIED and gitignored: the upstream
# weights carry no license, so they are never committed or redistributed — the package
# only ships the integration and loads the file if present. Override with DRUM_MODEL_PATH.
DRUM_MODEL_PATH: Path = Path(
    os.environ.get("DRUM_MODEL_PATH", str(LEGACY_MANIFEST_DIR.parent / "models" / "drum-cnn-lstm.model"))
)

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


def manifest_path(prefix: str, root: Path | None = None) -> Path:
    """Timestamped manifest path under the selected library's .eidetic/runs/."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    directory = require_root(root if root is not None else SAMPLES_ROOT) / '.eidetic' / 'runs'
    return directory / f"{prefix}-{stamp}.tsv"
