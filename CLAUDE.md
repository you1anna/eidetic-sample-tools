# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`AGENTS.md` is the cross-tool entry point and stays authoritative for read-order and
repo boundaries; this file adds the build/test/architecture detail.

## What this repo is

A **public**, personal-first CLI toolkit for hardware electronic musicians. Three
independent Python packages, each installed editable into its own venv:

| Package | Distribution | Commands | Deps |
|---|---|---|---|
| `library-tools/` | `librarytools` | `sample-review`, `sample-sort`, `sample-dedupe`, `sample-intake`, `sample-analyze`, `sample-tag`, `sample-find`, `sample-curate`, `sample-profile`, `sample-near-dupes`, `sample-role-cleanup`, `sample-benchmark`, `sample-classify` (retired) | numpy, soundfile; optional `[classifier]` = torch + librosa |
| `sample-tools/` | `sampletools` | `sample-export` | stdlib + `ffmpeg`/`ffprobe` via subprocess |
| `ableton-tools/` | `abletontools` | `als-index`, `als-samples` | stdlib only (gzip + ElementTree) |

Studio wiring, MIDI sync and session workflow live in the **private** `eidetic-studio`
repo (`~/Projects/eidetic-studio`) — never add studio-wiring docs here.

## Build and test

Each package has its own venv under `~/.venvs/<pkg>`; Python 3.12 at
`/opt/homebrew/bin/python3.12`. Never install globally.

```bash
# Install (editable). library-tools and ableton-tools define a [dev] extra with pytest.
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "library-tools[dev]"

# Test — run from the repo root
~/.venvs/library-tools/bin/python -m pytest library-tools -q     # 135 tests
~/.venvs/sample-tools/bin/python -m pytest sample-tools -q       # 10 tests
~/.venvs/ableton-tools/bin/python -m pytest ableton-tools -q     # 10 tests

# One file / one test
~/.venvs/library-tools/bin/python -m pytest library-tools/tests/test_curate.py -q
~/.venvs/library-tools/bin/python -m pytest library-tools/tests/test_curate.py::test_promote_favourites -q
```

There is no linter, formatter or CI configured — pytest is the whole verification story.
Tests are plain pytest with `tmp_path`, no conftest; they import the installed package, so
an editable install must exist before they run.

Both `librarytools.profiles` and `sampletools.config` locate `profiles/` as
`Path(__file__).resolve().parents[3] / "profiles"` — i.e. the repo root relative to
`<pkg>/src/<mod>/`. A non-editable install breaks profile resolution.

## Architecture

The pipeline is a one-way ratchet from cheap path evidence to expensive audio evidence to
human decisions, with a distinct action level at each stage (see `docs/SAFETY.md`):

1. **Review** (`review.py`) — filename/path heuristics only; writes TSV + split indexes.
   `--no-probe` skips even `ffprobe`. Never touches audio.
2. **Organise** (`sort.py`, `dedupe.py`, `intake.py`) — build a `list[Move]` plan, print it,
   and only mutate under `--apply`. All mutation funnels through `moves.py`:
   `safe_move` returns `missing`/`exists`/`moved` and **never overwrites**; `apply_plan`
   writes a `dest<TAB>src` undo TSV for files that actually moved.
3. **Analyse** (`analyze.py` + `analyze_{sources,features,rules,outputs,types}.py`) — the
   CLI is a thin shell over those modules. Optionally builds the SQLite inventory and
   acoustic features; `--classifier` adds suggestion-only drum-role votes.
4. **Curate** (`curate.py`, `curate_cli.py`) — `migrate-catalogue` / `prepare` / `validate`
   / `promote` / `views` / `undo-promotion`. Promotion re-hashes the source against the
   labelled `sample_id` before copying into `CURATED/`; `undo-promotion` moves copies to
   `_QUARANTINE/promotion-undo/` rather than deleting.
5. **Export** (`sampletools`) — converts crate rows to per-device WAVs under `_EXPORT/`.

### Retrieval layer (`origin.py`, `features.py`, `tagging.py`, `find.py`)

Added on top of the same index, and deliberately **move-free** — it only ever writes to the
database and to `manifests/`.

- `origin.py` recovers pack provenance destroyed by the earlier flattening. `sample-sort`
  renamed files to `{role}-{description}_{source}` and `_description` joins with `-` only, so
  **the first underscore is the origin boundary**. Uppercase in a stem means the file was
  never renamed, so its underscores are the vendor's and parsing them would invent
  provenance. Nothing assumes today's zone names: `resolve_from_path` skips structural
  folders at any depth, so a future restructure doesn't break it.
- `features.py` moves acoustics off paths and onto `sample_id`. The old
  `sample-intelligence.sqlite` is path-keyed and went stale when the library was
  reorganised. Migration matches on `(size, mtime, basename)`; the `(size, mtime)` pair alone
  is ambiguous for 610 keys covering 4,631 files, because unzipping a pack gives many
  same-size files one mtime.
- `tagging.py` — a tag is a saved predicate in `vocabulary.toml`, materialised into `tags`.
  Fix a wrong tag by editing one rule and regenerating; never re-label files.
- `find.py` — keyword search plus `--like` similarity. Similarity is the only thing that
  narrows within a pack (7,826 SA909 samples share every keyword tag). `write_crate` emits
  exactly what `sampletools.export.read_crate_tsv` reads, but search itself spans every zone
  (`PACKS`/`CATALOGUE`/`CURATED`) — `--curated-only` restricts to what the exporter's
  `CURATED/`-only check will actually accept, so a crate built for hardware doesn't need a
  failed export to discover which rows weren't promoted.

Two traps live here, both already fixed and covered by tests: `proposed_name` prefixes files
with their role, so matching instrument words against a raw name calls every `clap-snare-…`
a CLAP and every `hat-cym-…` a CYMBAL — strip the prefix first. And `sort.py` appends `-2` on
filename collisions, which must be stripped from filename tokens but **not** from folder
names, or `riemann-…-techno-1` loses its real trailing number.

### Identity model

`inventory.py` is the spine: `sample_id` is a SHA-256 of file bytes, paths are replaceable
locations. The SQLite DB (`--library-db`, schema in `_ensure_schema`) holds `assets`,
`locations` (path-keyed, relative to root, with `exists_now` cleared for stale scans),
`hash_cache` (dev/inode/size/mtime), `asset_features`, `annotations`, `tags`, `reviews`,
`promotions`. Review history therefore survives a move or exact copy, and any downstream
consumer (crate, promotion) can re-verify content before acting.

Library zones are the first path component: `PACKS/` (intact vendor packs — excluded from
dedupe), `CATALOGUE/` (broad, role-organised, not ear-approved), `CURATED/` (auditioned).
`_EXPORT`, `_TO-DELETE`, `_QUARANTINE` are skipped by scans.

### Profiles

`profiles/studios/*.toml` bind device IDs; `profiles/devices/*.toml` carry the hardware
capabilities (rate, bits, channels, capacity limits, import root). `profiles.py` resolves
studio → devices into frozen dataclasses. Selection precedence: `--profile` →
`MUSIC_TOOLS_PROFILE` → `~/.config/eidetic-sample-tools/config.toml` → `eidetic-studio`.

`sample-tools` keeps built-in `DEVICE_SPECS` for the legacy path and overlays profile
values in `get_profile_spec`; a profile that doesn't enable the device is an error.

### Export paths

`export.py` has two plan builders, and they behave differently:

- `build_plan` — legacy `manifests/<device>.txt` (dir / glob / `src => rename`, relative to
  `SAMPLES_ROOT`), flat output, name-length warnings only.
- `build_crate_plan` — curated crate TSV with the exact schema
  `sample_id, source_path, role, descriptor, reason`. Validates hard: source exists, resolves
  under `CURATED/` (rejects a `CATALOGUE/` or `PACKS/` row even with a matching hash — a crate
  is a promotion, not a search result), SHA-256 matches, Digitakt ≤127 and one-shot roles only,
  TR-8S ≤256 files / ≤600 s, no duplicate compact names. Emits hardware-native layouts
  (`EIDETIC-CURATED/AUDIO/`, `ROLAND/TR-8S/SAMPLE/`); a TR-8S row whose `reason` contains
  `stereo-essential` gets a per-item spec override that preserves stereo.

Existing outputs are skipped (exports are idempotent) unless `--force`. `sync_to_card`
copies a built export; Digitakt has `can_sync=False` because the +Drive is not a mount.

## Invariants — do not weaken

- Move commands preview by default; `--apply` is the only mutation gate, and it approves one
  reviewed plan, not a setting. `sample-export` is the exception: a bare run writes, so
  `--list` then `--dry-run` first.
- Never overwrite a destination; never delete. Extras go to `_TO-DELETE/`, undone promotions
  to `_QUARANTINE/`.
- Model confidence is never permission to move, exclude, promote or export. The drum
  classifier is Experimental and its first ear calibration failed (a high-confidence
  `KICKS → CLAP-SNARE` route was all kicks); near-dupe output needs a human `decision=remove`.
- Source audio is never converted in place.
- `profiles/` mirrors real hardware constraints — don't change without asking.

## Environment and data

| Variable | Purpose |
|---|---|
| `SAMPLES_ROOT` | Library root; default `/Volumes/Extreme SSD/Production/SAMPLES` |
| `EXPORT_ROOT` | Default `<SAMPLES_ROOT>/_EXPORT` |
| `MUSIC_TOOLS_PROFILE` | Studio profile name |
| `DRUM_MODEL_PATH` | Classifier weights; default `library-tools/models/drum-cnn-lstm.model` |
| `ALS_ROOTS` | Colon-separated Ableton roots for `als-*` |

Never commit or copy in: library audio (`/Volumes/Extreme SSD/Production/SAMPLES`),
`library-tools/manifests/` and `library-tools/models/` (gitignored — weights are
user-supplied and unlicensed upstream), `external/`, `.spikes/`. Ableton archive lives at
`/Volumes/Extreme SSD/Production/ABLETON_PROJECTS`, active scratch at `~/Projects/Production`.

## Repo conventions

- Design docs in `docs/superpowers/specs/`, implementation plans in
  `docs/superpowers/plans/`, both `YYYY-MM-DD-<slug>.md`.
- Adopted/rejected/downgraded approaches get a dated record in `decisions/` — including
  failures, which are kept as evidence.
- `STATUS.md` carries a dated **Updated:** line and the current operational position;
  update it when the live-library or maturity picture changes.
- Maturity labels (Stable / Beta / Experimental / Planned / Retired) are defined in
  `docs/ROADMAP.md` and used consistently across the READMEs.

## Current operational state (STATUS.md, 2026-08-04)

**`promote` is permitted.** The 130 absent protected `PACKS/` entries and the one missing
Foundation v1 identity were demoted from blocker to open integrity risk on 2026-08-04
(`eidetic-studio/decisions/2026-08-04-demote-packs-recovery-gate.md`): promotion re-hashes
every labelled source and refuses a stale or missing file, which is the per-file guarantee the
blanket block stood in for. Still do not infer causes for the discrepancies, and treat no
`PACKS/` preservation claim as verified.

**Still blocked:** `--apply` organisation, intake, dedupe and catalogue-migration against the
live library — the SSD remains single-copy (28 GB, no `tmutil` destination), and promotion's
second copy lands on the same disk, so it is not a backup. The confidence-organisation code
behind the 2026-07-18 18-move audit is unmerged. Hardware export and card sync are untested
against the live library; run `--list` then `--dry-run` first.

Active run: `tribal-140-01` — a 63-row audition packet awaiting Robin's listening decisions.
`CURATED/` is still empty (`promotions` table: 0 rows).
