"""Read an audio file's duration via ffprobe. Returns None on any failure."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def duration(path: Path) -> float | None:
    """Duration in seconds, or None if ffprobe is absent or the file won't probe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe or not path.exists():
        return None
    cmd = [
        ffprobe,
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, check=True
        ).stdout.strip()
        return float(out)
    except (subprocess.CalledProcessError, OSError, ValueError):
        return None
