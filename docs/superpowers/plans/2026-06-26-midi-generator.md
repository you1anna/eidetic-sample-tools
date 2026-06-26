# MIDI Generator (`midi-tools`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A new `midi-tools` package (`miditools`, console script `midi-gen`) that generates techno
MIDI — Euclidean percussion and hypnotic basslines in a chosen scale — as `.mid` files that drop
into Ableton's browser or load onto the Octatrack/Digitakt. Pure, testable rhythm/pitch functions
behind a thin `mido` writer and CLI.

**Architecture:** Mirror the `librarytools` layout — `src/miditools/{euclid,music,generate,write,cli}.py`
with pure functions at the core (`euclid`, `music`, `generate`) and thin IO at the edge (`write`,
`cli`). No DAW state, no realtime, no network. Output dir env-overridable, defaulting to
`$SAMPLES_ROOT/CURATED/MIDI/`.

**Tech Stack:** Python 3.12, `mido` (only third-party dep — robust SMF round-tripping), pytest.
Per-machine venv under `~/.venvs/midi-tools`. (Zero-dep alternative: a ~50-line stdlib SMF writer in
`write.py` — swap point noted in Task 4 if Robin prefers no deps.)

## Global Constraints

- Python 3.12; type hints on every signature; `pathlib` over `os.path`.
- **Writes new files only**; never overwrites — `write_midi` adds a `-N` suffix on collision.
- Rhythm is generated independently of pitch; deterministic given `--seed`.
- Run `pytest`/installs from the **Mac venv**, never on the exFAT SSD.
- Output root: `MIDI_OUT_ROOT` env, default `$SAMPLES_ROOT/CURATED/MIDI`.

---

### Task 1: Euclidean rhythm — `euclid.py`

**Files:** Create `midi-tools/src/miditools/euclid.py`, `midi-tools/tests/test_euclid.py`.
**Interface:** `euclidean(steps: int, pulses: int, rotate: int = 0) -> list[bool]` (exactly `pulses` onsets).

- [ ] **Step 1: Failing test**
```python
# midi-tools/tests/test_euclid.py
from miditools.euclid import euclidean

def test_pulse_count_matches():
    for steps in range(1, 33):
        for pulses in range(0, steps + 1):
            assert sum(euclidean(steps, pulses)) == pulses

def test_known_tresillo():
    assert euclidean(8, 3) == [True, False, False, True, False, False, True, False]

def test_rotate_shifts_right():
    base = euclidean(8, 3)
    assert euclidean(8, 3, rotate=1) == [base[-1]] + base[:-1]

def test_edges():
    assert euclidean(0, 4) == []
    assert euclidean(4, 0) == [False, False, False, False]
    assert euclidean(4, 4) == [True, True, True, True]
    assert sum(euclidean(4, 9)) == 4  # pulses clamp to steps
```
- [ ] **Step 2: Run → fail** (`pytest tests/test_euclid.py -v` → ModuleNotFoundError)
- [ ] **Step 3: Implement**
```python
# midi-tools/src/miditools/euclid.py
from __future__ import annotations

def euclidean(steps: int, pulses: int, rotate: int = 0) -> list[bool]:
    """Even distribution of `pulses` onsets across `steps` (Bresenham/Bjorklund)."""
    if steps <= 0:
        return []
    pulses = max(0, min(pulses, steps))
    pattern = [(i * pulses) // steps != ((i - 1) * pulses) // steps for i in range(steps)]
    if rotate:
        r = rotate % steps
        pattern = pattern[-r:] + pattern[:-r]
    return pattern
```
- [ ] **Step 4: Run → pass**
- [ ] **Step 5: Commit** — `feat(midi): euclidean rhythm generator`

---

### Task 2: Scales + note parsing — `music.py`

**Files:** Create `midi-tools/src/miditools/music.py`, `tests/test_music.py`.
**Interface:** `note_to_midi(name) -> int`; `note_number(root, scale, degree) -> int`; `SCALES` table.

- [ ] **Step 1: Failing test**
```python
# midi-tools/tests/test_music.py
from miditools.music import note_to_midi, note_number

def test_note_to_midi():
    assert note_to_midi("A1") == 33      # (1+1)*12 + 9
    assert note_to_midi("C-1") == 0
    assert note_to_midi("C#3") == note_to_midi("Db3")

def test_degree_in_scale_and_octave_wrap():
    root = note_to_midi("A1")
    assert note_number(root, "phrygian", 0) == root
    assert note_number(root, "phrygian", 1) == root + 1   # phrygian b2
    assert note_number(root, "minor", 7) == root + 12      # wraps an octave
```
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement**
```python
# midi-tools/src/miditools/music.py
from __future__ import annotations
import re

SCALES: dict[str, tuple[int, ...]] = {
    "minor": (0, 2, 3, 5, 7, 8, 10),
    "phrygian": (0, 1, 3, 5, 7, 8, 10),
    "minor_pentatonic": (0, 3, 5, 7, 10),
}
_BASE = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}

def note_to_midi(name: str) -> int:
    """Parse 'A1', 'C#3', 'Eb2' -> MIDI number (C-1 = 0, A4 = 69)."""
    m = re.fullmatch(r"([A-Ga-g])([#b]?)(-?\d+)", name.strip())
    if not m:
        raise ValueError(f"bad note name: {name!r}")
    semitone = _BASE[m.group(1).lower()] + (1 if m.group(2) == "#" else -1 if m.group(2) == "b" else 0)
    return (int(m.group(3)) + 1) * 12 + semitone

def note_number(root: int, scale: str, degree: int) -> int:
    """MIDI note for `degree` of `scale` above `root` (wraps octaves for out-of-range degrees)."""
    iv = SCALES[scale]
    octave, idx = divmod(degree, len(iv))
    return root + 12 * octave + iv[idx]
```
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(midi): scales + note-name parsing`

---

### Task 3: Event + pattern generators — `generate.py`

**Files:** Create `midi-tools/src/miditools/generate.py`, `tests/test_generate.py`.
**Interface:** `Event(note,start,dur,vel)`; `hats(...)`, `bassline(...)`, `kick(...)` → `list[Event]`.

- [ ] **Step 1: Failing test**
```python
# midi-tools/tests/test_generate.py
from miditools import generate
from miditools.music import note_to_midi, SCALES

def test_hats_one_event_per_pulse_with_accents():
    ev = generate.hats(16, 7, step_ticks=120, note=42)
    assert len(ev) == 7
    assert all(e.note == 42 for e in ev)
    # first step of any beat (multiple of 4) is accented
    assert any(e.vel > 100 for e in ev)

def test_bassline_notes_in_scale_and_deterministic():
    root = note_to_midi("A1")
    a = generate.bassline(16, 5, step_ticks=120, root=root, scale="phrygian", seed=1)
    b = generate.bassline(16, 5, step_ticks=120, root=root, scale="phrygian", seed=1)
    assert a == b                                  # deterministic per seed
    pcs = {(e.note - root) % 12 for e in a}
    assert pcs <= set(SCALES["phrygian"]) | {(p) % 12 for p in (-1,)}  # in scale (incl. degree -1)

def test_kick_four_on_floor():
    ev = generate.kick(16, step_ticks=120, every=4)
    assert [e.start for e in ev] == [0, 480, 960, 1440]
```
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement**
```python
# midi-tools/src/miditools/generate.py
from __future__ import annotations
import random
from dataclasses import dataclass
from .euclid import euclidean
from .music import note_number

@dataclass(frozen=True)
class Event:
    note: int    # MIDI note
    start: int   # ticks from start
    dur: int     # ticks
    vel: int     # 1..127

def hats(steps: int, pulses: int, *, step_ticks: int, note: int = 42, rotate: int = 0,
         accent: int = 110, ghost: int = 70) -> list[Event]:
    """One hat per Euclidean pulse; accent the first step of each beat (every 4 steps)."""
    out: list[Event] = []
    for i, on in enumerate(euclidean(steps, pulses, rotate)):
        if on:
            out.append(Event(note, i * step_ticks, step_ticks // 2, accent if i % 4 == 0 else ghost))
    return out

def bassline(steps: int, pulses: int, *, step_ticks: int, root: int, scale: str = "phrygian",
             rotate: int = 0, seed: int | None = None) -> list[Event]:
    """Rolling bass: root-weighted scale degrees on a Euclidean rhythm. Deterministic per seed."""
    rng = random.Random(seed)
    degrees = [0, 0, 0, 2, 4, -1]   # root-heavy with occasional colour
    out: list[Event] = []
    for i, on in enumerate(euclidean(steps, pulses, rotate)):
        if on:
            out.append(Event(note_number(root, scale, rng.choice(degrees)), i * step_ticks, step_ticks, 100))
    return out

def kick(steps: int, *, step_ticks: int, note: int = 36, every: int = 4) -> list[Event]:
    """Four-on-the-floor (or a kick every `every` steps)."""
    return [Event(note, i * step_ticks, step_ticks // 2, 118) for i in range(0, steps, every)]
```
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(midi): Event + hats/bassline/kick generators`

---

### Task 4: SMF writer — `write.py`

**Files:** Create `midi-tools/src/miditools/write.py`, `tests/test_write.py`.
**Interface:** `write_midi(events, path, *, ppq=480, bpm=138.0, channel=0) -> Path` (never overwrites).

- [ ] **Step 1: Failing test** (round-trip with `mido` + collision)
```python
# midi-tools/tests/test_write.py
from pathlib import Path
import mido
from miditools.generate import Event
from miditools.write import write_midi

def test_round_trip(tmp_path: Path):
    out = write_midi([Event(42, 0, 240, 110), Event(42, 480, 240, 70)],
                     tmp_path / "h.mid", ppq=480, bpm=138)
    mid = mido.MidiFile(str(out))
    assert mid.ticks_per_beat == 480
    ons = [m for tr in mid.tracks for m in tr if m.type == "note_on" and m.velocity > 0]
    assert len(ons) == 2
    tempos = [m for tr in mid.tracks for m in tr if m.type == "set_tempo"]
    assert tempos and tempos[0].tempo == mido.bpm2tempo(138)

def test_no_overwrite(tmp_path: Path):
    e = [Event(36, 0, 120, 118)]
    a = write_midi(e, tmp_path / "k.mid")
    b = write_midi(e, tmp_path / "k.mid")
    assert b.name == "k-2.mid" and a != b
```
- [ ] **Step 2: Run → fail** (`pip install mido` into the venv first)
- [ ] **Step 3: Implement**
```python
# midi-tools/src/miditools/write.py
from __future__ import annotations
from pathlib import Path
import mido
from .generate import Event

def _unique(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        cand = path.with_name(f"{path.stem}-{n}{path.suffix}")
        if not cand.exists():
            return cand
        n += 1

def write_midi(events: list[Event], path: Path, *, ppq: int = 480, bpm: float = 138.0,
               channel: int = 0) -> Path:
    """Write a single-track SMF; never overwrites (adds -N). Returns the path written."""
    mid = mido.MidiFile(ticks_per_beat=ppq)
    track = mido.MidiTrack(); mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm)))
    msgs: list[tuple[int, mido.Message]] = []
    for e in events:
        msgs.append((e.start, mido.Message("note_on", note=e.note, velocity=e.vel, channel=channel)))
        msgs.append((e.start + e.dur, mido.Message("note_off", note=e.note, velocity=0, channel=channel)))
    msgs.sort(key=lambda m: (m[0], m[1].type == "note_on"))   # offs before ons at same tick
    prev = 0
    for abs_tick, msg in msgs:
        track.append(msg.copy(time=abs_tick - prev)); prev = abs_tick
    path.parent.mkdir(parents=True, exist_ok=True)
    dest = _unique(path); mid.save(str(dest)); return dest
```
> **Zero-dep swap point:** if avoiding `mido`, replace this module with a stdlib SMF writer
> (MThd + MTrk, variable-length delta times). The `Event` contract and `write_midi` signature stay
> identical, so nothing else changes.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(midi): mido SMF writer (no-overwrite)`

---

### Task 5: `midi-gen` CLI + packaging + venv

**Files:** Create `midi-tools/src/miditools/cli.py`, `midi-tools/src/miditools/__init__.py`,
`midi-tools/pyproject.toml`, `midi-tools/README.md`, `tests/test_cli.py`.

- [ ] **Step 1: Failing test** (CLI writes a file)
```python
# midi-tools/tests/test_cli.py
from pathlib import Path
from miditools.cli import main

def test_euclid_subcommand_writes_file(tmp_path: Path):
    rc = main(["--out", str(tmp_path), "--bpm", "138", "euclid", "--steps", "16", "--pulses", "7"])
    assert rc == 0
    assert list(tmp_path.glob("hats_euclid_7-16_138.mid"))

def test_bass_subcommand_writes_file(tmp_path: Path):
    rc = main(["--out", str(tmp_path), "bass", "--root", "A1", "--scale", "phrygian", "--seed", "1"])
    assert rc == 0
    assert list(tmp_path.glob("bass_phrygian_A1_*.mid"))
```
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement CLI**
```python
# midi-tools/src/miditools/cli.py
from __future__ import annotations
import argparse, os
from pathlib import Path
from . import generate
from .music import note_to_midi
from .write import write_midi

def _out_root() -> Path:
    if "MIDI_OUT_ROOT" in os.environ:
        return Path(os.environ["MIDI_OUT_ROOT"])
    samples = os.environ.get("SAMPLES_ROOT", "/Volumes/Extreme SSD/Production/SAMPLES")
    return Path(samples) / "CURATED" / "MIDI"

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="midi-gen", description="Generate techno MIDI patterns as .mid")
    ap.add_argument("--out", type=Path, default=_out_root())
    ap.add_argument("--bpm", type=float, default=138.0)
    ap.add_argument("--ppq", type=int, default=480)
    sub = ap.add_subparsers(dest="cmd", required=True)
    pe = sub.add_parser("euclid"); pe.add_argument("--steps", type=int, default=16)
    pe.add_argument("--pulses", type=int, default=7); pe.add_argument("--rotate", type=int, default=0)
    pe.add_argument("--note", type=int, default=42)
    pb = sub.add_parser("bass"); pb.add_argument("--steps", type=int, default=16)
    pb.add_argument("--pulses", type=int, default=5); pb.add_argument("--rotate", type=int, default=0)
    pb.add_argument("--root", default="A1"); pb.add_argument("--scale", default="phrygian")
    pb.add_argument("--seed", type=int, default=None)
    args = ap.parse_args(argv)
    step_ticks = args.ppq // 4
    if args.cmd == "euclid":
        events = generate.hats(args.steps, args.pulses, step_ticks=step_ticks, note=args.note, rotate=args.rotate)
        name, channel = f"hats_euclid_{args.pulses}-{args.steps}_{int(args.bpm)}.mid", 9
    else:
        events = generate.bassline(args.steps, args.pulses, step_ticks=step_ticks,
                                   root=note_to_midi(args.root), scale=args.scale, rotate=args.rotate, seed=args.seed)
        name, channel = f"bass_{args.scale}_{args.root}_{args.pulses}-{args.steps}_{int(args.bpm)}.mid", 0
    dest = write_midi(events, args.out / name, ppq=args.ppq, bpm=args.bpm, channel=channel)
    print(f"wrote {len(events)} events -> {dest}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```
- [ ] **Step 4: Write `pyproject.toml`** (match the house style)
```toml
[project]
name = "midi-tools"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = ["mido>=1.3"]

[project.optional-dependencies]
dev = ["pytest>=8"]

[project.scripts]
midi-gen = "miditools.cli:main"

[tool.setuptools.packages.find]
where = ["src"]
```
- [ ] **Step 5: Set up venv + install + run full suite**
```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/midi-tools
~/.venvs/midi-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/midi-tools[dev]"
~/.venvs/midi-tools/bin/pytest /Users/macmini/Projects/eidetic-music-tools/midi-tools -v
```
Expected: all tests pass; `~/.venvs/midi-tools/bin/midi-gen --help` works.
- [ ] **Step 6: README + alias note** — document the venv setup and add a `mg()` alias suggestion to
  `~/.zshrc` (Aliases section), mirroring the `sx`/`ls`/`lc` aliases in `library-tools/README.md`.
- [ ] **Step 7: Commit** — `feat(midi): midi-gen CLI + packaging`

---

## Self-Review

- Euclidean/scale/generator/writer/CLI each have failing-test-first tasks. ✓
- Pure core (`euclid`, `music`, `generate`) separated from IO (`write`, `cli`). ✓
- Never overwrites; deterministic via `--seed`; writes only to output dir. ✓
- Single third-party dep (`mido`) isolated in its own venv; zero-dep swap point documented. ✓
- Type signatures consistent across modules (`Event`, `list[Event]`, `Path` returns). ✓
- No DAW control / MCP (per spec scope). ✓
