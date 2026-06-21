# Two-zone sample library + pack intake — design

_Date: 2026-06-21. Status: approved, ready for implementation plan._

## Problem

The `SAMPLES/` library still doesn't feel cohesive in structure, naming, or clarity,
even after the 2026-06-17 reorg. Root cause: the current rule keeps vendor packs
**whole beneath their dominant role**, so a folder like `KICKS/` mixes two organizing
principles at once — convention-named one-shots *and* whole vendor pack trees with
vendor naming and arbitrary depth. Mixing principles in one place can never read as
cohesive. Separately, new downloads have no reliable intake path, so vendor packs pile
up loose at the top level (e.g. `Dark.Magic.Samples.Underground.Techno.MULTiFORMAT-DECiBEL/`,
`Filterheadz Hardgroove Techno/`), violating the "top level = sound role" rule.

## Target model: two zones

Split the library into two zones that never mix organizing principles:

```
SAMPLES/
  CURATED/      all role folders (KICKS, PERC, HATS-CYM, CLAP-SNARE, DRUM-LOOPS,
                DRUM-KITS, BASS, SYNTH-STAB-CHORD, DRONE-ATMOS, FX-RISE-IMPACT,
                VOCALS, MIDI) — renamed-by-convention, filed by sound role.
  PACKS/        whole vendor packs, kept intact, with normalized folder names.
                (was _PACKS/, which already held "whole multi-role libraries")
  00_INBOX/     drop zone for new downloads
  _EXPORT/      device-ready sets (unchanged)
  _REVIEW/      low-confidence files awaiting curation (unchanged)
  _QUARANTINE/  holding pen (unchanged)
  _TO-DELETE/   staged-for-deletion (nothing deleted without sign-off)
  README.md
```

- `CURATED/` = what you reach for: every file filed by role, named to convention.
- `PACKS/` = raw whole libraries you browse; kept pristine and intact.
- New packs land in `PACKS/`; good finds get promoted into `CURATED/` later (curation,
  out of scope here).

## Scope (this session)

**In scope — all moves reversible, zero deletions:**
1. Create `CURATED/` and `PACKS/`.
2. Move the 12 existing top-level role folders into `CURATED/` (cheap whole-folder
   moves — *not* a content audit).
3. Rename `_PACKS/` → `PACKS/`.
4. Run `sample-intake` on the stray top-level packs (the 2 known + any others) → `PACKS/`
   with normalized slugs.
5. Build the `sample-intake` tool (below).
6. Make the existing tools `CURATED/`-aware (required glue — see Tooling changes).
7. Duplicate sweep via existing `sample-dedupe` (stage to `_TO-DELETE/`, sign-off to delete).
8. Rewrite `SAMPLES/README.md` and update repo `README.md` (`inbox-sort` → built).

**Deferred (later pass):**
- Auditing inside each role folder to sweep embedded vendor packs out to `PACKS/`.
- Curating `_REVIEW/` (5.8 GB / ~1815 flat files) into roles.
- Internal flattening of pack folder structure.

## Safety guarantees (no accidental deletions)

This workflow performs **zero deletions**. Specifically:
- All mutations go through `librarytools.moves.safe_move`, which checks `dest.exists()`
  **before** moving and returns `"exists"` (skip) rather than overwriting. It never
  clobbers — for files or directories.
- Every applied move writes an undo manifest line (`dest \t src`), so each step is
  fully reversible.
- Slug collisions (two packs normalizing to the same name) are resolved with a `-N`
  suffix (same pattern as `sample-sort._unique_dest`), so a move is never skipped into
  a clobber.
- All tools are **dry-run by default**; `--apply` is explicit. The dry-run plan is
  reviewed before any apply.
- Deletion enters **only** via `sample-dedupe`, which *moves* dupes to `_TO-DELETE/`.
  Emptying `_TO-DELETE/` is a separate, explicit, human-approved `rm`.

## New tool: `sample-intake`

New module `librarytools/intake.py`, peer to `sample-sort`, registered as the
`sample-intake` console script.

**Job:** scan the library top level and `00_INBOX/` for stray *pack folders* — a
directory that contains audio and is not in the known set (role folders, staging dirs,
`CURATED/`, `PACKS/`, `00_INBOX/`). For each, plan a move to `PACKS/<slug>`. Loose audio
*files* (not inside a pack folder) are reported and left in `00_INBOX/` for curation,
not moved.

**Whole = whole:** moves the top pack folder only; internal nesting is left untouched
(flattening is curation, deferred).

**Naming — the clarity win.** A pure, unit-tested function:

```python
def normalize_pack_name(raw: str) -> str: ...
```

- lowercase
- drop scene-release group tags, format markers, and release IDs
  (`-DECiBEL`, `MULTiFORMAT`, `WAV`, `FLAC`, `AIFF`, `SCD`, `dcb-5289`, trailing IDs)
- `.`, space, `_` → `-`
- collapse repeated separators; strip leading/trailing separators

Examples:
- `Dark.Magic.Samples.Underground.Techno.MULTiFORMAT-DECiBEL` → `dark-magic-underground-techno`
- `Filterheadz Hardgroove Techno` → `filterheadz-hardgroove-techno`

**Traceability:** original folder names recorded in `PACKS/_manifest.tsv`
(`slug \t original \t date`) so the source name is never lost.

**Safety:** reuses `moves.py`; dry-run by default (`--apply` to execute); writes plan +
undo TSV to `manifests/`; `-N` collision suffixing.

**Tests** (`tests/test_intake.py`): normalization cases (scene tags, format markers,
release IDs, spaces, collapse), stray-vs-known detection, plan building against a temp
tree, dry-run produces no moves, collision suffixing.

## Tooling changes (required glue)

Moving role folders under `CURATED/` would break the file-level tools, so:
- `config.py`: add `CURATED_ROOT = SAMPLES_ROOT / "CURATED"` and
  `PACKS_ROOT = SAMPLES_ROOT / "PACKS"`.
- `sort.py` / `review.py`: role-folder destinations resolve under `CURATED_ROOT`;
  `CURATED/` and `PACKS/` added to the never-walk-from set.
- `dedupe.py` / config `DEDUPE_EXCLUDE`: add `PACKS` so the duplicate sweep keeps vendor
  packs pristine and only dedupes `CURATED/` + `00_INBOX/`.

These are targeted changes to code directly affected by the restructure, not unrelated
refactoring.

## Duplicate sweep

After the restructure, run the existing `sample-dedupe`:
1. Dry-run → review the manifest.
2. `--apply` → *stage* byte-identical dupes into `_TO-DELETE/` (a move, undo-logged).
3. Eyeball `_TO-DELETE/`; delete only on explicit sign-off.

Scope: `CURATED/` + `00_INBOX/` only (PACKS excluded — see Tooling changes).

## Docs

- Rewrite `SAMPLES/README.md`: two-zone model, when each zone is used, the intake
  workflow, naming convention (unchanged), device export targets (unchanged).
- Update repo `README.md`: `inbox-sort` status `planned` → folded into `library-tools`
  as `sample-intake` (built).

## Operator / skill path

Claude Code, local execution against the mounted SSD. Implementation:
`writing-plans` → `test-driven-development` (the normalize function and plan builder are
pure and highly testable) → `verification-before-completion` (dry-run shown before any
`--apply`).
