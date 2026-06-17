# Sample library cleanup — design

**Date:** 2026-06-17
**Status:** approved, ready for implementation plan
**Goal:** Sort the messy bulk of the SSD sample library by **sound type** (loops /
one-shots / pads-drones / other) and **de-dupe**, with deliberately light tooling.
Keep it simple, token-cheap, and fully reversible — the SSD is exFAT with **no backup**.

## Context

Robin (DJ **Eidetic**) runs a hardware techno studio (Octatrack MKII, Digitakt MK1,
TR-8S → Ableton). The sample library lives at
`/Volumes/Extreme SSD/Production/SAMPLES` (~78 GB, ~52k files). It was recently
reorganised into single-role folders (KICKS, PERC, DRUM-LOOPS, BASS,
SYNTH-STAB-CHORD, DRONE-ATMOS, VOCALS, CLAP-SNARE, FX-RISE-IMPACT, MIDI), but the
bulk of the content still sits in two large catch-all areas that are fragmented,
deeply nested, and duplicated.

Survey findings (in scope vs whole library):
- `_PACKS/` ~26,927 files, `DRUM-KITS/` ~14,457 files — the mess to sort.
- ~43,460 `.wav`, plus aif/flac/etc.
- Duplicate heuristic (size + name): ~1,366 groups / ~2,747 files / ~2.4 GB.

Hardware constraint: DT/OT/TR-8S read **only filenames and folders** (no metadata
DB), and the Ableton browser is mostly folder+filename driven. So organisation must
live in names and folders, not tags.

## Scope

**In scope (sort by type):**
- `_PACKS/`
- `DRUM-KITS/`
- `00_INBOX/` (intake; currently empty)

**Out of scope (left untouched):** the curated single-role folders (KICKS, PERC,
DRUM-LOOPS, BASS, SYNTH-STAB-CHORD, DRONE-ATMOS, VOCALS, CLAP-SNARE, FX-RISE-IMPACT,
MIDI), `_EXPORT/`, and the `sample-tools` export pipeline.

## Target structure

Four new top-level type folders under `SAMPLES/`, each keeping **one level of pack
grouping** so provenance survives and 27k files don't collapse into one unusable,
collision-prone folder:

```
LOOPS/<pack>/...          # BPM in name, "loop" in file/folder, or duration >= ~1 bar
ONE-SHOTS/<pack>/...      # "hit/shot/oneshot" in name, or short duration (< ~1.5s)
PADS-DRONES/<pack>/...    # "pad/drone/atmos/texture/swell" in name/folder
OTHER/<pack>/...          # anything unmatched — nothing dropped or wild-guessed
```

`<pack>` = the source pack folder name (the top in-scope folder a file came from),
so e.g. `_PACKS/Riemann Tribal Techno 1/loop_132.wav` →
`LOOPS/Riemann Tribal Techno 1/loop_132.wav`.

## Components

Two small scripts in a new `library-tools/` directory in this repo. Python 3.12,
pathlib, type hints. Venv stays on the Mac (`~/.venvs/...`), not on exFAT.

### 1. `classify`

Walks the in-scope folders and assigns each audio file to one of the four type
buckets using **cheap signals, cheapest first**:

1. **Filename + folder-path keywords** (instant, no I/O beyond the walk):
   - loop: `loop`, `lp`, a `NNN`bpm token, `bpm`
   - one-shot: `oneshot`, `one-shot`, `one_shot`, `hit`, `shot`, `stab`, `single`
   - pad/drone: `pad`, `drone`, `atmos`, `texture`, `swell`, `ambient`
2. **Duration probe** (`ffprobe`) **only for files no keyword matched** — keeps the
   probe count low. Heuristic: `< ~1.5s` → one-shot; `>= ~1.5s` → loop. (Threshold
   tunable.)
3. Still unresolved → **OTHER**.

**Dry-run is the default.** It prints a counts table (files per bucket, how many
resolved by keyword vs probe vs fell to OTHER) and writes the full per-file move
plan to a manifest on disk (`library-tools/manifests/classify-<timestamp>.tsv`:
`source<TAB>dest<TAB>reason`). No files move.

`--apply` reads the manifest and performs the moves, writing an **undo manifest**
(`source<TAB>dest`) so every move is reversible. Moves only — never deletes. Skips a
move if the destination already exists (logs the collision rather than overwriting).

### 2. `dedupe`

Operates on the ~2,747 same-size+name candidates (recomputed at run time, not
hard-coded):

1. Group files by `(size, basename)`.
2. For groups with >1 member, hash (e.g. SHA-256) **only those files** to confirm
   byte-identical duplicates.
3. Pick a **canonical** copy (shallowest path; tie-break by shortest path string),
   move the rest to `_TO-DELETE/dupes/` preserving relative structure, write an undo
   manifest.

Dry-run default; `--apply` to move. Nothing is deleted — `_TO-DELETE/` is staging
for a later human sign-off pass.

## Data flow

```
scan in-scope folders
  -> classify (dry-run): counts table + classify-<ts>.tsv manifest
  -> [human reviews counts; tune keyword/threshold; re-run dry-run]
  -> classify --apply: moves + undo-classify-<ts>.tsv
  -> dedupe (dry-run): counts + dedupe-<ts>.tsv manifest
  -> dedupe --apply: moves dupes to _TO-DELETE/dupes/ + undo-dedupe-<ts>.tsv
```

Order matters: classify first (so dedupe sees the final layout), then dedupe.

## Error handling & safety

Non-negotiable, because the SSD is exFAT (no journaling) with no backup:

- **Move, never delete.** Dupes go to `_TO-DELETE/dupes/`, not `rm`.
- **Dry-run by default**; `--apply` is explicit.
- **Every apply writes an undo manifest** (`source<TAB>dest`) enabling a reverse pass.
- **No overwrite:** if a destination exists, skip and log — never clobber.
- **OTHER absorbs uncertainty** — no aggressive guessing.
- **AppleDouble / metadata files** (`._*`, `.DS_Store`, `.asd`) are ignored by the
  classifier (not moved into type buckets); cleaning them is out of scope for now.
- Respect global rules: keep FLAC originals; BPM range 65–135 is a detection bound,
  **not** a filter — no file is skipped for being outside it.

## Testing

- Unit-test the **classifier decision function** (pure: given a path + optional
  duration, return a bucket + reason) against a table of representative names —
  loops, one-shots, pads, ambiguous. No disk needed.
- Unit-test the **dedupe grouping/canonical-pick** logic on synthetic
  `(size, name, path)` tuples.
- Manual: run `classify` dry-run on the real library, sanity-check the counts table
  and spot-check a sample of the manifest before any `--apply`.

## Token discipline

The scripts do all per-file work locally and emit only a **summary counts table**
plus on-disk manifests. The assistant reviews the small summary and spot-checks —
never loads the full multi-thousand-row file list into context.

## Out of scope (YAGNI for now)

- BPM/key detection and tagging (later `inventory/` tool).
- Re-sorting the already-curated role folders.
- Deleting anything (staging only).
- Cleaning `.asd` / AppleDouble / empty dirs (separate, optional later pass).
- Any GUI, database, or search index.
