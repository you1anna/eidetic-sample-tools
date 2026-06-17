# Sample Library Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build two small, reversible CLI tools that sort the bulk vendor-pack sample mess by sound type (loops / one-shots / pads-drones / other) and de-dupe it.

**Architecture:** A new `library-tools/` package (`librarytools`) sits beside the existing `sample-tools` in the eidetic-music-tools repo, mirroring its conventions (stdlib-only, `src/` layout, env-overridable config, argparse CLIs, console-script entry points). A pure decision function classifies each file from cheap signals (path keywords first, an `ffprobe` duration fallback only for unmatched files). A shared safe-move helper performs every filesystem mutation move-only (never delete), default dry-run, writing an undo manifest for reversibility.

**Tech Stack:** Python 3.12, stdlib only (pathlib, argparse, hashlib, subprocess, dataclasses), `ffprobe` (from ffmpeg) for durations, pytest for tests. Venv lives on the Mac (`~/.venvs/library-tools`), never on the exFAT SSD.

## Global Constraints

- Python 3.12; `from __future__ import annotations` at the top of every module; type hints on all function signatures; prefer `pathlib` over `os.path`.
- Stdlib only for runtime deps (no third-party runtime packages); `ffprobe` invoked via `subprocess`. `pytest` is a dev-only dep.
- **Move, never delete.** Duplicates and any removed files go to `_TO-DELETE/dupes/` under `SAMPLES_ROOT`; nothing is `rm`-ed.
- **Dry-run is the default** for every mutating command; `--apply` is required to move files.
- **Every `--apply` writes an undo manifest** (`dest<TAB>src`, one moved file per line) enabling a reverse pass.
- **Never overwrite:** if a move destination already exists, skip and log — do not clobber.
- `SAMPLES_ROOT` default `/Volumes/Extreme SSD/Production/SAMPLES`, overridable via env var.
- In scope for classify: top-level folders `_PACKS`, `DRUM-KITS`, `00_INBOX` only. Curated role folders, `_EXPORT/`, `_TO-DELETE/`, `_QUARANTINE/` are never read as classify sources.
- Type buckets (exact names): `LOOPS`, `ONE-SHOTS`, `PADS-DRONES`, `OTHER`.
- BPM range 65–135 is a detection bound elsewhere, **not** a filter — no file is ever skipped for its tempo. FLAC originals are never deleted.
- Audio source extensions: `.wav .aif .aiff .flac .mp3 .ogg`. AppleDouble (`._*`) and dotfiles are ignored, not moved.
- Run all `pytest` and CLI commands from the repo root `/Volumes/Extreme SSD/eidetic-music-tools` using the Mac venv: `~/.venvs/library-tools/bin/pytest` and `~/.venvs/library-tools/bin/python -m librarytools.<mod>`.

---

## File Structure

- `library-tools/pyproject.toml` — package metadata, two console scripts.
- `library-tools/src/librarytools/__init__.py` — package marker.
- `library-tools/src/librarytools/config.py` — paths, scopes, buckets, keyword sets, thresholds.
- `library-tools/src/librarytools/probe.py` — `ffprobe` duration reader (one responsibility).
- `library-tools/src/librarytools/moves.py` — `Move` record + safe move + manifest/undo writers (shared by both tools).
- `library-tools/src/librarytools/classify.py` — pure decision fn + planner + CLI `main`.
- `library-tools/src/librarytools/dedupe.py` — candidate grouping + hashing + canonical pick + planner + CLI `main`.
- `library-tools/tests/test_classify.py`, `test_dedupe.py`, `test_moves.py` — unit tests.
- `library-tools/manifests/` — created at runtime, holds generated `.tsv` manifests (gitignored).
- `library-tools/README.md` — usage.
- Repo `docs/STORAGE-AND-WORKFLOW.md` — roadmap row updated.

---

### Task 1: Package scaffold + config

**Files:**
- Create: `library-tools/pyproject.toml`
- Create: `library-tools/src/librarytools/__init__.py`
- Create: `library-tools/src/librarytools/config.py`
- Create: `library-tools/tests/test_config.py`
- Create: `library-tools/.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: `config.SAMPLES_ROOT: Path`, `config.IN_SCOPE: tuple[str, ...]`, `config.DEDUPE_EXCLUDE: tuple[str, ...]`, `config.SOURCE_EXTS: frozenset[str]`, `config.BUCKETS: tuple[str, ...]`, `config.TO_DELETE_ROOT: Path`, `config.MANIFEST_DIR: Path`, `config.DURATION_ONESHOT_MAX: float`, `config.LOOP_KEYWORDS/ONESHOT_KEYWORDS/PAD_KEYWORDS: tuple[str, ...]`, `config.manifest_path(prefix: str) -> Path`.

- [ ] **Step 1: Create the package directories and marker**

```bash
mkdir -p "/Volumes/Extreme SSD/eidetic-music-tools/library-tools/src/librarytools" \
         "/Volumes/Extreme SSD/eidetic-music-tools/library-tools/tests"
```

Create `library-tools/src/librarytools/__init__.py`:

```python
"""Light, reversible tools to sort and de-dupe the SSD sample library."""

__version__ = "0.1.0"
```

- [ ] **Step 2: Write `pyproject.toml`**

Create `library-tools/pyproject.toml`:

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "librarytools"
version = "0.1.0"
description = "Sort the SSD sample library by sound type and de-dupe it (reversible)."
requires-python = ">=3.12"
dependencies = []  # stdlib + ffprobe via subprocess

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
sample-classify = "librarytools.classify:main"
sample-dedupe = "librarytools.dedupe:main"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 3: Write `.gitignore`**

Create `library-tools/.gitignore`:

```
manifests/
*.egg-info/
__pycache__/
.venv/
```

- [ ] **Step 4: Write the failing config test**

Create `library-tools/tests/test_config.py`:

```python
from __future__ import annotations

from librarytools import config


def test_buckets_are_the_four_expected():
    assert config.BUCKETS == ("LOOPS", "ONE-SHOTS", "PADS-DRONES", "OTHER")


def test_in_scope_is_the_messy_folders_only():
    assert config.IN_SCOPE == ("_PACKS", "DRUM-KITS", "00_INBOX")


def test_to_delete_root_under_samples_root():
    assert config.TO_DELETE_ROOT == config.SAMPLES_ROOT / "_TO-DELETE"


def test_manifest_path_has_prefix_and_tsv_suffix():
    p = config.manifest_path("classify")
    assert p.name.startswith("classify-")
    assert p.suffix == ".tsv"
    assert p.parent == config.MANIFEST_DIR
```

- [ ] **Step 5: Run the test to verify it fails**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && python3.12 -m pytest library-tools/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarytools'` (package not on path yet; the venv install in Step 7 fixes this).

- [ ] **Step 6: Write `config.py`**

Create `library-tools/src/librarytools/config.py`:

```python
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
MANIFEST_DIR: Path = Path(__file__).resolve().parents[2] / "manifests"

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
```

- [ ] **Step 7: Create the Mac venv, editable-install, and verify the test passes**

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -q -e "/Volumes/Extreme SSD/eidetic-music-tools/library-tools[dev]"
cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_config.py -v
```
Expected: 4 passed.

- [ ] **Step 8: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/pyproject.toml library-tools/.gitignore \
        library-tools/src/librarytools/__init__.py \
        library-tools/src/librarytools/config.py \
        library-tools/tests/test_config.py
git commit -m "feat(library-tools): package scaffold + config"
```

---

### Task 2: ffprobe duration reader

**Files:**
- Create: `library-tools/src/librarytools/probe.py`
- Create: `library-tools/tests/test_probe.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `probe.duration(path: Path) -> float | None` — seconds, or `None` if ffprobe is missing/fails/returns no duration.

- [ ] **Step 1: Write the failing test**

Create `library-tools/tests/test_probe.py`:

```python
from __future__ import annotations

from pathlib import Path

from librarytools import probe


def test_duration_none_for_nonexistent_file():
    assert probe.duration(Path("/no/such/file.wav")) is None
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_probe.py -v`
Expected: FAIL — `AttributeError: module 'librarytools.probe' has no attribute 'duration'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Write `probe.py`**

Create `library-tools/src/librarytools/probe.py`:

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_probe.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/src/librarytools/probe.py library-tools/tests/test_probe.py
git commit -m "feat(library-tools): ffprobe duration reader"
```

---

### Task 3: Safe-move helper + manifest/undo writers

**Files:**
- Create: `library-tools/src/librarytools/moves.py`
- Create: `library-tools/tests/test_moves.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `moves.Move` — frozen dataclass with `src: Path`, `dest: Path`, `tag: str` (a bucket name or a reason string).
  - `moves.safe_move(src: Path, dest: Path) -> str` — returns `"moved"`, `"exists"`, or `"missing"`; creates parent dirs; never overwrites.
  - `moves.write_plan(path: Path, plan: list[Move]) -> None` — writes a TSV `src<TAB>dest<TAB>tag` (creates parent dir).
  - `moves.apply_plan(plan: list[Move], undo_path: Path) -> dict[str, int]` — executes moves, writes undo TSV `dest<TAB>src` for each moved file, returns status counts.

- [ ] **Step 1: Write the failing tests**

Create `library-tools/tests/test_moves.py`:

```python
from __future__ import annotations

from pathlib import Path

from librarytools import moves


def test_safe_move_moves_into_new_dir(tmp_path: Path):
    src = tmp_path / "a" / "x.wav"
    src.parent.mkdir(parents=True)
    src.write_text("data")
    dest = tmp_path / "b" / "c" / "x.wav"
    assert moves.safe_move(src, dest) == "moved"
    assert dest.read_text() == "data"
    assert not src.exists()


def test_safe_move_skips_when_dest_exists(tmp_path: Path):
    src = tmp_path / "x.wav"
    src.write_text("new")
    dest = tmp_path / "out" / "x.wav"
    dest.parent.mkdir()
    dest.write_text("original")
    assert moves.safe_move(src, dest) == "exists"
    assert dest.read_text() == "original"  # not clobbered
    assert src.exists()                     # source left in place


def test_safe_move_missing_source(tmp_path: Path):
    assert moves.safe_move(tmp_path / "nope.wav", tmp_path / "out.wav") == "missing"


def test_apply_plan_writes_undo_for_moved_only(tmp_path: Path):
    src = tmp_path / "s" / "x.wav"
    src.parent.mkdir()
    src.write_text("d")
    dest = tmp_path / "d" / "x.wav"
    undo = tmp_path / "undo.tsv"
    counts = moves.apply_plan([moves.Move(src, dest, "LOOPS")], undo)
    assert counts == {"moved": 1, "exists": 0, "missing": 0}
    assert undo.read_text().strip() == f"{dest}\t{src}"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_moves.py -v`
Expected: FAIL — `module 'librarytools.moves' has no attribute 'safe_move'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Write `moves.py`**

Create `library-tools/src/librarytools/moves.py`:

```python
"""Filesystem mutations: move-only, never overwrite, always reversible."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Move:
    src: Path
    dest: Path
    tag: str  # bucket name (classify) or reason (dedupe)


def safe_move(src: Path, dest: Path) -> str:
    """Move src -> dest. Returns 'missing', 'exists', or 'moved'. Never overwrites."""
    if not src.exists():
        return "missing"
    if dest.exists():
        return "exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dest))
    return "moved"


def write_plan(path: Path, plan: list[Move]) -> None:
    """Write the planned moves as a TSV: src<TAB>dest<TAB>tag."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for m in plan:
            fh.write(f"{m.src}\t{m.dest}\t{m.tag}\n")


def apply_plan(plan: list[Move], undo_path: Path) -> dict[str, int]:
    """Execute moves; record reversible undo lines (dest<TAB>src) for moved files."""
    counts = {"moved": 0, "exists": 0, "missing": 0}
    undo_path.parent.mkdir(parents=True, exist_ok=True)
    with undo_path.open("w", encoding="utf-8") as undo:
        for m in plan:
            status = safe_move(m.src, m.dest)
            counts[status] += 1
            if status == "moved":
                undo.write(f"{m.dest}\t{m.src}\n")
    return counts
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_moves.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/src/librarytools/moves.py library-tools/tests/test_moves.py
git commit -m "feat(library-tools): safe-move helper + manifest/undo writers"
```

---

### Task 4: Classifier decision function (pure)

**Files:**
- Create: `library-tools/src/librarytools/classify.py`
- Create: `library-tools/tests/test_classify.py`

**Interfaces:**
- Consumes: `config.LOOP_KEYWORDS`, `config.ONESHOT_KEYWORDS`, `config.PAD_KEYWORDS`, `config.DURATION_ONESHOT_MAX`.
- Produces: `classify.classify_path(rel: Path, duration: float | None = None) -> tuple[str, str]` — returns `(bucket, reason)`. Precedence: loop keyword → pad keyword → one-shot keyword → duration (if given) → `("OTHER", "unmatched")`. `bucket` is always one of `config.BUCKETS`.

- [ ] **Step 1: Write the failing tests**

Create `library-tools/tests/test_classify.py`:

```python
from __future__ import annotations

from pathlib import Path

from librarytools.classify import classify_path


def test_loop_keyword_wins():
    b, r = classify_path(Path("_PACKS/Riemann/drum loop 132.wav"))
    assert b == "LOOPS"
    assert "loop" in r


def test_bpm_token_is_a_loop():
    b, _ = classify_path(Path("_PACKS/Pack/rumble_132bpm.wav"))
    assert b == "LOOPS"


def test_pad_keyword():
    b, _ = classify_path(Path("_PACKS/Pack/warm pad C.wav"))
    assert b == "PADS-DRONES"


def test_drone_keyword():
    b, _ = classify_path(Path("DRUM-KITS/Vendor/dark drone.wav"))
    assert b == "PADS-DRONES"


def test_oneshot_keyword():
    b, _ = classify_path(Path("DRUM-KITS/Vendor/kick hit 01.wav"))
    assert b == "ONE-SHOTS"


def test_loop_beats_pad_when_both_present():
    b, _ = classify_path(Path("_PACKS/Pack/pad loop.wav"))
    assert b == "LOOPS"


def test_short_duration_oneshot_when_no_keyword():
    b, r = classify_path(Path("_PACKS/Pack/zap.wav"), duration=0.4)
    assert b == "ONE-SHOTS"
    assert "duration" in r


def test_long_duration_loop_when_no_keyword():
    b, _ = classify_path(Path("_PACKS/Pack/zap.wav"), duration=4.0)
    assert b == "LOOPS"


def test_unmatched_no_duration_is_other():
    b, r = classify_path(Path("_PACKS/Pack/mystery.wav"))
    assert b == "OTHER"
    assert r == "unmatched"


def test_folder_keyword_counts():
    b, _ = classify_path(Path("_PACKS/Techno Loops/bd.wav"))
    assert b == "LOOPS"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_classify.py -v`
Expected: FAIL — `ImportError: cannot import name 'classify_path'` (or `ModuleNotFoundError`).

- [ ] **Step 3: Write the decision function in `classify.py`**

Create `library-tools/src/librarytools/classify.py` (CLI added in Task 5):

```python
"""Sort the messy in-scope packs into sound-type buckets (reversible).

Decision precedence (cheapest signal first):
  loop keyword  ->  pad keyword  ->  one-shot keyword  ->  duration  ->  OTHER
"""

from __future__ import annotations

import re
from pathlib import Path

from . import config

_BPM_RE = re.compile(r"\d{2,3}\s?bpm")


def _has(text: str, keywords: tuple[str, ...]) -> bool:
    return any(kw in text for kw in keywords)


def classify_path(rel: Path, duration: float | None = None) -> tuple[str, str]:
    """Return (bucket, reason) for a file from its path relative to SAMPLES_ROOT.

    Keywords are matched against the whole lowercased relative path, so a parent
    folder named "Techno Loops" classifies its files even if the filename is bare.
    """
    text = str(rel).lower()
    if _has(text, config.LOOP_KEYWORDS) or _BPM_RE.search(text):
        return "LOOPS", "keyword:loop"
    if _has(text, config.PAD_KEYWORDS):
        return "PADS-DRONES", "keyword:pad"
    if _has(text, config.ONESHOT_KEYWORDS):
        return "ONE-SHOTS", "keyword:oneshot"
    if duration is not None:
        if duration < config.DURATION_ONESHOT_MAX:
            return "ONE-SHOTS", f"duration:{duration:.2f}<{config.DURATION_ONESHOT_MAX}"
        return "LOOPS", f"duration:{duration:.2f}>={config.DURATION_ONESHOT_MAX}"
    return "OTHER", "unmatched"
```

Note: `"bpm"` is in `LOOP_KEYWORDS` (so a bare "bpm" matches) and `_BPM_RE` additionally catches `132bpm`/`132 bpm` forms — both routes yield LOOPS, which is intended.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_classify.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/src/librarytools/classify.py library-tools/tests/test_classify.py
git commit -m "feat(library-tools): pure classifier decision function"
```

---

### Task 5: Classify planner + CLI

**Files:**
- Modify: `library-tools/src/librarytools/classify.py`
- Modify: `library-tools/tests/test_classify.py`

**Interfaces:**
- Consumes: `classify.classify_path`, `probe.duration`, `moves.Move/write_plan/apply_plan`, `config.*`.
- Produces:
  - `classify.dest_rel(rel: Path, bucket: str) -> Path` — destination path **relative to `SAMPLES_ROOT`**: `<bucket>/<pack>/<subpath>`, where `<pack>` is the second path component (or `_loose` if the file sits directly in a scope folder).
  - `classify.build_plan(root: Path = config.SAMPLES_ROOT, probe_durations: bool = True) -> list[moves.Move]`.
  - `classify.main(argv: list[str] | None = None) -> int` — argparse CLI (`--apply`, `--root`, `--no-probe`).

- [ ] **Step 1: Write the failing tests for `dest_rel` and `build_plan`**

Append to `library-tools/tests/test_classify.py`:

```python
from librarytools import classify as classify_mod
from librarytools import config


def test_dest_rel_keeps_pack_and_subpath():
    rel = Path("_PACKS/Riemann Tribal/loops/bd 132.wav")
    dest = classify_mod.dest_rel(rel, "LOOPS")
    assert dest == Path("LOOPS/Riemann Tribal/loops/bd 132.wav")


def test_dest_rel_drum_kits_uses_vendor_as_pack():
    rel = Path("DRUM-KITS/Goldbaby/kick hit.wav")
    dest = classify_mod.dest_rel(rel, "ONE-SHOTS")
    assert dest == Path("ONE-SHOTS/Goldbaby/kick hit.wav")


def test_dest_rel_loose_file_uses_underscore_loose():
    rel = Path("00_INBOX/random loop.wav")
    dest = classify_mod.dest_rel(rel, "LOOPS")
    assert dest == Path("LOOPS/_loose/random loop.wav")


def test_build_plan_classifies_in_scope_audio(tmp_path: Path):
    root = tmp_path
    (root / "_PACKS" / "PackA").mkdir(parents=True)
    (root / "_PACKS" / "PackA" / "drum loop.wav").write_text("x")
    (root / "_PACKS" / "PackA" / "kick hit.wav").write_text("x")
    (root / "_PACKS" / "PackA" / "._sneaky.wav").write_text("x")  # AppleDouble: ignored
    (root / "_PACKS" / "PackA" / "notes.txt").write_text("x")      # non-audio: ignored
    (root / "KICKS").mkdir()                                       # out of scope
    (root / "KICKS" / "curated.wav").write_text("x")

    plan = classify_mod.build_plan(root=root, probe_durations=False)
    by_name = {m.src.name: m for m in plan}
    assert set(by_name) == {"drum loop.wav", "kick hit.wav"}
    assert by_name["drum loop.wav"].dest == root / "LOOPS" / "PackA" / "drum loop.wav"
    assert by_name["kick hit.wav"].dest == root / "ONE-SHOTS" / "PackA" / "kick hit.wav"
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_classify.py -v`
Expected: FAIL — `AttributeError: module 'librarytools.classify' has no attribute 'dest_rel'`.

- [ ] **Step 3: Add `dest_rel`, `build_plan`, counts, and `main` to `classify.py`**

Add these imports at the top of `library-tools/src/librarytools/classify.py` (merge with the existing `import` block):

```python
import argparse
import sys
from collections import Counter

from . import moves, probe
```

Append to `library-tools/src/librarytools/classify.py`:

```python
def dest_rel(rel: Path, bucket: str) -> Path:
    """Destination relative to SAMPLES_ROOT: <bucket>/<pack>/<subpath>."""
    parts = rel.parts
    if len(parts) >= 3:
        pack = parts[1]
        sub = Path(*parts[2:])
    else:  # file directly inside a scope folder, e.g. 00_INBOX/foo.wav
        pack = "_loose"
        sub = Path(parts[-1])
    return Path(bucket) / pack / sub


def _iter_sources(root: Path) -> "list[Path]":
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
    return found


def build_plan(
    root: Path = config.SAMPLES_ROOT, probe_durations: bool = True
) -> list[moves.Move]:
    """Classify every in-scope audio file into a bucket move."""
    plan: list[moves.Move] = []
    for path in _iter_sources(root):
        rel = path.relative_to(root)
        bucket, reason = classify_path(rel)
        if bucket == "OTHER" and probe_durations:
            d = probe.duration(path)
            if d is not None:
                bucket, reason = classify_path(rel, d)
        dest = root / dest_rel(rel, bucket)
        plan.append(moves.Move(path, dest, f"{bucket}|{reason}"))
    return plan


def _print_counts(plan: list[moves.Move]) -> None:
    buckets = Counter(m.tag.split("|", 1)[0] for m in plan)
    reasons = Counter(m.tag.split("|", 1)[1].split(":", 1)[0] for m in plan)
    print(f"  files: {len(plan)}")
    for b in config.BUCKETS:
        print(f"    {b:<12} {buckets.get(b, 0)}")
    print("  resolved by:")
    for r, n in sorted(reasons.items()):
        print(f"    {r:<12} {n}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-classify",
        description="Sort _PACKS/DRUM-KITS/00_INBOX into sound-type buckets (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    ap.add_argument("--no-probe", action="store_true", help="skip ffprobe duration fallback")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root, probe_durations=not args.no_probe)
    manifest = config.manifest_path("classify")
    moves.write_plan(manifest, plan)
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] classify {args.root}")
    _print_counts(plan)
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move files)")
        return 0

    undo = config.manifest_path("undo-classify")
    counts = moves.apply_plan(plan, undo)
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; "
          f"missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full classify test file to verify it passes**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_classify.py -v`
Expected: 14 passed.

- [ ] **Step 5: Smoke-test the CLI dry-run against the real library**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/sample-classify --no-probe`
Expected: prints a counts table (LOOPS/ONE-SHOTS/PADS-DRONES/OTHER), a `plan written:` path, and the dry-run notice. No files moved. (Use `--no-probe` here to keep it fast and token-cheap; a full run with probing comes during execution review.)

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/src/librarytools/classify.py library-tools/tests/test_classify.py
git commit -m "feat(library-tools): classify planner + CLI (dry-run default)"
```

---

### Task 6: De-dupe tool + CLI

**Files:**
- Create: `library-tools/src/librarytools/dedupe.py`
- Create: `library-tools/tests/test_dedupe.py`

**Interfaces:**
- Consumes: `moves.Move/write_plan/apply_plan`, `config.SAMPLES_ROOT/DEDUPE_EXCLUDE/SOURCE_EXTS/TO_DELETE_ROOT/manifest_path`.
- Produces:
  - `dedupe.find_candidates(root: Path) -> dict[tuple[int, str], list[Path]]` — groups by `(size, lowercased basename)`, only returning groups with >1 member.
  - `dedupe.sha256(path: Path) -> str`.
  - `dedupe.pick_canonical(paths: list[Path]) -> Path` — fewest path components, tie-broken by shortest string.
  - `dedupe.build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]` — duplicates (confirmed byte-identical) moved to `_TO-DELETE/dupes/<rel>`.
  - `dedupe.main(argv: list[str] | None = None) -> int`.

- [ ] **Step 1: Write the failing tests**

Create `library-tools/tests/test_dedupe.py`:

```python
from __future__ import annotations

from pathlib import Path

from librarytools import dedupe, config


def test_pick_canonical_prefers_shallowest():
    paths = [
        Path("a/b/c/x.wav"),
        Path("a/x.wav"),
        Path("a/b/x.wav"),
    ]
    assert dedupe.pick_canonical(paths) == Path("a/x.wav")


def test_pick_canonical_tiebreak_shortest_string():
    paths = [Path("aa/longer.wav"), Path("b/x.wav")]
    assert dedupe.pick_canonical(paths) == Path("b/x.wav")


def test_find_candidates_groups_same_size_and_name(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    c = tmp_path / "p3" / "other.wav"
    for p in (a, b, c):
        p.parent.mkdir(parents=True)
    a.write_text("same")
    b.write_text("same")           # same size + name as a
    c.write_text("different len")  # unique
    groups = dedupe.find_candidates(tmp_path)
    assert list(groups) == [(len("same"), "kick.wav")]
    assert set(groups[(len("same"), "kick.wav")]) == {a, b}


def test_build_plan_moves_confirmed_dupes_to_to_delete(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    for p in (a, b):
        p.parent.mkdir(parents=True)
    a.write_text("identical")
    b.write_text("identical")
    plan = dedupe.build_plan(root=tmp_path)
    assert len(plan) == 1                       # one of the two kept, one moved
    moved = plan[0]
    assert moved.dest.parts[-4:-1] == ("_TO-DELETE", "dupes", moved.src.parent.name)


def test_build_plan_ignores_false_positive_same_name_diff_bytes(tmp_path: Path):
    a = tmp_path / "p1" / "kick.wav"
    b = tmp_path / "p2" / "kick.wav"
    for p in (a, b):
        p.parent.mkdir(parents=True)
    a.write_text("AAAA")
    b.write_text("BBBB")  # same size + name, different bytes -> NOT a dupe
    assert dedupe.build_plan(root=tmp_path) == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_dedupe.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'librarytools.dedupe'`.

- [ ] **Step 3: Write `dedupe.py`**

Create `library-tools/src/librarytools/dedupe.py`:

```python
"""Find byte-identical duplicate samples and stage the extras in _TO-DELETE/dupes/.

Cheap first pass groups by (size, name); only those candidate groups are hashed.
Nothing is deleted — duplicates are moved to staging for a later human sign-off.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections import defaultdict
from pathlib import Path

from . import config, moves


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_candidates(root: Path) -> dict[tuple[int, str], list[Path]]:
    """Group files by (size, lowercased basename); return only multi-member groups."""
    groups: dict[tuple[int, str], list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.name.startswith("._") or path.name.startswith("."):
            continue
        if path.suffix.lower() not in config.SOURCE_EXTS:
            continue
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in config.DEDUPE_EXCLUDE:
            continue
        groups[(path.stat().st_size, path.name.lower())].append(path)
    return {k: v for k, v in groups.items() if len(v) > 1}


def pick_canonical(paths: list[Path]) -> Path:
    """Keep the shallowest path; tie-break by shortest string."""
    return min(paths, key=lambda p: (len(p.parts), len(str(p))))


def build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]:
    """Confirm dupes by hash; move every non-canonical copy to _TO-DELETE/dupes/."""
    plan: list[moves.Move] = []
    dupes_root = (root / "_TO-DELETE" / "dupes") if root != config.SAMPLES_ROOT \
        else config.TO_DELETE_ROOT / "dupes"
    for candidates in find_candidates(root).values():
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for p in candidates:
            by_hash[sha256(p)].append(p)
        for identical in by_hash.values():
            if len(identical) < 2:
                continue
            keep = pick_canonical(identical)
            for victim in identical:
                if victim == keep:
                    continue
                dest = dupes_root / victim.relative_to(root)
                plan.append(moves.Move(victim, dest, "dupe"))
    return plan


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-dedupe",
        description="Stage byte-identical duplicate samples in _TO-DELETE/dupes/ (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root)
    manifest = config.manifest_path("dedupe")
    moves.write_plan(manifest, plan)
    reclaimed = sum(m.src.stat().st_size for m in plan if m.src.exists())
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] dedupe {args.root}")
    print(f"  duplicate files to stage: {len(plan)}  (~{reclaimed / 1e9:.2f} GB)")
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move dupes to _TO-DELETE/dupes/)")
        return 0

    undo = config.manifest_path("undo-dedupe")
    counts = moves.apply_plan(plan, undo)
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; "
          f"missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/tests/test_dedupe.py -v`
Expected: 5 passed.

- [ ] **Step 5: Run the whole suite**

Run: `cd "/Volumes/Extreme SSD/eidetic-music-tools" && ~/.venvs/library-tools/bin/pytest library-tools/ -v`
Expected: all tests pass (config 4, probe 1, moves 4, classify 14, dedupe 5 = 28).

- [ ] **Step 6: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/src/librarytools/dedupe.py library-tools/tests/test_dedupe.py
git commit -m "feat(library-tools): de-dupe tool + CLI (stages to _TO-DELETE)"
```

---

### Task 7: Docs — library-tools README + roadmap update

**Files:**
- Create: `library-tools/README.md`
- Modify: `docs/STORAGE-AND-WORKFLOW.md` (the "Tooling roadmap" table)

**Interfaces:**
- Consumes: nothing (documentation).
- Produces: nothing (documentation).

- [ ] **Step 1: Write `library-tools/README.md`**

Create `library-tools/README.md`:

```markdown
# library-tools

Two light, **reversible** tools that tidy the bulk of the SSD sample library.
Both default to **dry-run** and **never delete** — they only move files, write a
plan manifest, and (on `--apply`) an undo manifest.

- `sample-classify` — sorts `_PACKS/`, `DRUM-KITS/`, `00_INBOX/` into sound-type
  buckets: `LOOPS/ ONE-SHOTS/ PADS-DRONES/ OTHER/`, keeping one level of pack
  grouping (`<bucket>/<pack>/...`). Curated role folders are left untouched.
- `sample-dedupe` — finds byte-identical duplicates and moves the extras to
  `_TO-DELETE/dupes/` for a later human sign-off.

## Install (venv on the Mac, never on the exFAT SSD)

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "/Volumes/Extreme SSD/eidetic-music-tools/library-tools[dev]"
```

## Use

```bash
lc() { ~/.venvs/library-tools/bin/sample-classify "$@"; }
ld() { ~/.venvs/library-tools/bin/sample-dedupe "$@"; }

lc                 # dry-run: counts table + plan manifest, nothing moved
lc --no-probe      # faster dry-run, keyword signals only (skip duration probe)
lc --apply         # move files into buckets, write undo manifest
ld                 # dry-run: how many dupes, ~GB reclaimable
ld --apply         # move dupes to _TO-DELETE/dupes/, write undo manifest
```

Run classify **before** dedupe so dedupe sees the final layout.

## Classification rules

Precedence (cheapest signal first), matched against the whole lowercased path:
loop keyword (`loop`, `lp`, `groove`, `bpm`, `NNNbpm`) → pad keyword
(`pad`, `drone`, `atmos`, `texture`, `swell`, `ambient`) → one-shot keyword
(`hit`, `shot`, `stab`, `oneshot`, `single`) → duration (< 1.5 s = one-shot,
else loop) → `OTHER`. Tune the keyword sets and threshold in `config.py`.

## Manifests & undo

Every run writes `manifests/<tool>-<timestamp>.tsv` (the plan). An `--apply` also
writes `manifests/undo-<tool>-<timestamp>.tsv` with `dest<TAB>src` lines — reverse
those moves to roll back. `manifests/` is gitignored.

## Safety

The SSD is exFAT with no backup. These tools move-only, never overwrite (a colliding
destination is skipped and logged), default to dry-run, and stage rather than delete.
```

- [ ] **Step 2: Update the roadmap table in `docs/STORAGE-AND-WORKFLOW.md`**

In `docs/STORAGE-AND-WORKFLOW.md`, find the `inbox-sort/` row in the Tooling roadmap table:

```
| `inbox-sort/` | planned | Fast intake of new downloads from `SAMPLES/00_INBOX/` into roles + naming. |
```

Replace it with:

```
| `library-tools/` | ✅ built | Sort `_PACKS`/`DRUM-KITS`/`00_INBOX` by sound type (loops/one-shots/pads-drones/other) + de-dupe to `_TO-DELETE/dupes/`. Reversible, dry-run default. |
| `inbox-sort/` | planned | Fast intake of new downloads from `SAMPLES/00_INBOX/` into roles + naming. |
```

- [ ] **Step 3: Commit**

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools"
git add library-tools/README.md docs/STORAGE-AND-WORKFLOW.md
git commit -m "docs(library-tools): README + roadmap update"
```

---

## Self-Review Notes

- **Spec coverage:** scope (_PACKS/DRUM-KITS/00_INBOX) → Task 1 config + Task 5 `_iter_sources`; four buckets → Task 1 + Task 4; `<bucket>/<pack>/...` layout → Task 5 `dest_rel`; keyword-then-duration classification → Task 4; dry-run default + undo manifests + move-never-delete + no-overwrite → Task 3 + CLIs in Tasks 5/6; dedupe size+name→hash→canonical→`_TO-DELETE/dupes/` → Task 6; classifier + dedupe unit tests → Tasks 4/6; counts-table token discipline → Task 5/6 `_print_counts`/summary; docs → Task 7. AppleDouble/`.asd` ignored (not moved) → `_iter_sources`/`find_candidates` skip dotfiles and non-source extensions; `.asd` is not in `SOURCE_EXTS` so it is never touched.
- **Placeholder scan:** none — every step has concrete code/commands.
- **Type consistency:** `Move(src, dest, tag)`, `classify_path(rel, duration)->(bucket,reason)`, `dest_rel(rel,bucket)->Path`, `build_plan(root, probe_durations)`, `find_candidates(root)->dict`, `pick_canonical(list)->Path` are used consistently across tasks and tests.
