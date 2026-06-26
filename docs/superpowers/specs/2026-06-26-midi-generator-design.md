# MIDI generator (`midi-tools`) — design

_Date: 2026-06-26. Status: approved, ready for implementation. Build first._

## Problem

Capturing a rhythmic or harmonic idea for hypnotic/dub/raw/hard-groove techno (~130–150 BPM)
currently means programming it by hand on the Octatrack/Digitakt or in Ableton. There's no fast
way to generate variations — Euclidean rhythms, polymeter, probability-driven hat patterns,
rolling basslines in a chosen scale — as plain `.mid` files that drop straight into Live's browser
or load onto the hardware. This is the lowest-effort, most immediately *playable* creative win in
the toolset, and it has no external-data or backup prerequisites.

## Target model: pure pattern functions → Standard MIDI File

A small `miditools` package whose core is **pure, unit-testable functions** (rhythm + pitch),
wrapped by a thin writer and CLI. No DAW state, no realtime, no network.

```
idea (CLI flags) → generate Events (pure) → write .mid (mido) → drop into Live / load on device
```

- **Rhythm** is generated independently of pitch (Euclidean / probability), then mapped onto
  pitches via a **scale** so the same groove can drive drums or a bassline.
- Output is a single-track (or 1-track-per-part) `.mid` at a chosen PPQ + tempo, written to a
  target dir (default `SAMPLES/CURATED/MIDI/`), **never overwriting** (a `-N` suffix is added).

## Scope (this session)

**In scope:**
1. Euclidean rhythm generator (`steps`, `pulses`, `rotate`) — exact pulse count, rotatable.
2. Scale/pitch mapping (minor, phrygian, minor-pentatonic — the techno-useful set), degree→MIDI.
3. Pattern generators: probability/accent **hats**, **hypnotic bassline** (rolling root + scale
   degrees on a Euclidean rhythm), simple **kick** + **fill**.
4. SMF writer (via `mido`): tempo meta, correct PPQ, note on/off, per-part channel.
5. `midi-gen` CLI + console-script entry point + its own venv.

**Out of scope (later / never):**
- **No DAW control / Ableton MCP** — this writes files only.
- Humanize/swing curves, chord voicings, song arrangement — later pass.
- Reading MIDI back for analysis (the analysis tool owns audio, not MIDI).

## Safety guarantees

- **Writes new files only**; never overwrites (`-N` suffix on collision, same pattern as
  `librarytools.sort._unique_dest`). Never deletes. Not gated by the SSD backup.
- Deterministic given a `--seed` so a good roll is reproducible.

## New tool: `midi-tools/` (package `miditools`)

| Module | Responsibility |
|---|---|
| `euclid.py` | `euclidean(steps, pulses, rotate=0) -> list[bool]` (Bresenham/Bjorklund). |
| `music.py` | `SCALES` table + `note_number(root, scale, degree) -> int`. |
| `generate.py` | `Event(note,start,dur,vel)` dataclass + `hats(...)`, `bassline(...)`, `kick(...)` → `list[Event]`. |
| `write.py` | `write_midi(events, path, *, ppq, bpm, channel) -> Path` (mido; `-N` collision). |
| `cli.py` | `main(argv)->int`; `midi-gen` console script. |

**CLI shape (illustrative):**
```
midi-gen euclid --steps 16 --pulses 7 --rotate 0 --bpm 138 --note 42   # hats
midi-gen bass  --steps 16 --pulses 5 --root A1 --scale phrygian --bpm 138 --seed 3
```
Default out dir: `$SAMPLES_ROOT/CURATED/MIDI/` (env-overridable, mirrors `config.py` pattern).
Filenames encode intent: `hats_euclid_7-16_138.mid`, `bass_phrygian_A1_5-16_138.mid`.

**Dependency note:** recommend **`mido`** (small, well-maintained, robust SMF round-tripping).
A ~50-line stdlib SMF writer is the zero-dependency alternative consistent with the repo's
no-third-party ethos for `sampletools`/`librarytools`; the implementation plan uses `mido` and
flags the swap point if Robin prefers zero deps. Either way the venv is per-tool under
`~/.venvs/midi-tools`.

## Tests (`tests/`)

- `test_euclid.py`: pulse count equals `pulses` for many (steps,pulses); known patterns
  (E(3,8)=`x..x..x.`, E(5,8), E(7,16)); rotation; edge cases (pulses 0, pulses==steps).
- `test_music.py`: degree→MIDI for minor/phrygian incl. octave wrap; root parsing (`A1`→33).
- `test_generate.py`: hats place one event per pulse; velocities accent on downbeats; bassline
  notes stay in scale; deterministic under `--seed`.
- `test_write.py`: round-trip — write then re-open with `mido`, assert tempo, ppq, note count,
  first/last event timing; collision adds `-N`.

## Operator / skill path

Claude Code, local on the Mac (venv under `~/.venvs/midi-tools`). Implementation:
`writing-plans` → `test-driven-development` (rhythm/pitch functions are pure and highly testable)
→ `verification-before-completion` (round-trip a generated file; eyeball/drag into Live).
