# Sample intelligence Tier-1 audio features — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps
> use checkbox (`- [ ]`) syntax for tracking. TDD throughout, as the repo already does.

**Status:** proposed; awaiting Robin's tier + package decision (see
`specs/2026-07-07-sample-intelligence-audit.md`).

**Goal:** Give `sample-analyze` real per-file **audio** features and **within-role**
similarity grouping, so tags and crates describe *what a sound is* — not just its
filename. This closes the gap the audit found: today 0 of 22,916 rows carry any acoustic
signal.

**Architecture:** Add a `librarytools.audiofeatures` module that decodes each sample to
downsampled mono, computes a small feature vector, and caches results in SQLite keyed on
(path, size, mtime). `analyze.py` reads features from the cache to (a) refine character
tags with acoustic reasons and (b) cluster within each role to produce readable virtual
groups. Keep the existing filename/OT-Set/source-registry logic intact — this augments,
it does not replace.

**Tech stack (Tier 1, recommended):** Python 3.12, `numpy`, `soundfile` (libsndfile),
stdlib `sqlite3`, `ffmpeg`/`ffprobe` for decode fallback on non-PCM inputs. **No torch,
no librosa, no demucs.** If Robin chooses Tier 0.5 instead, drop numpy/soundfile and
compute only time-domain features via ffmpeg-decoded raw PCM (see "Tier 0.5 fallback").

## Global constraints

- Phase remains **read-only** against `/Volumes/Extreme SSD/Production/SAMPLES` — decode
  in memory, never write near the samples.
- No deletes, no moves, no OT project rewrites.
- Generated artifacts stay under `library-tools/manifests/` and gitignored.
- SQLite cache lives at `library-tools/manifests/sample-intelligence.sqlite` (gitignored);
  re-runs must skip unchanged files.
- Deterministic outputs: fixed random seed for clustering; stable row ordering.
- Feature extraction must degrade gracefully — an undecodable file records a `null`
  feature row with an error reason, never crashes the run.

## Feature set (Tier 1)

Per sample, from a mono mixdown decoded at 22,050 Hz:

| Feature | Meaning | Cheap method |
|---|---|---|
| `duration_s` | length | frame count / SR |
| `peak`, `rms`, `crest` | level + dynamics | max abs, RMS, peak/RMS |
| `attack_ms` | transient sharpness | time to reach 90% of peak envelope |
| `tail_ms` | decay length | time from peak to −40 dB of peak |
| `head_silence_ms`, `tail_silence_ms` | trim estimate | envelope threshold crossings |
| `centroid_hz` | brightness | spectral centroid (single FFT / STFT mean) |
| `flatness` | noisy vs tonal | spectral flatness (geo mean / arith mean) |
| `sub_ratio` | subbiness | energy < 120 Hz / total |
| `low/mid/high_ratio` | tonal balance | 3-band energy split |
| `onset_density` | busy vs sparse (loops) | spectral-flux peak count / duration |
| `zcr` | brightness/noise proxy | zero-crossing rate |

All features are inspectable and each derived tag keeps a numeric reason
(`tag=subby reason=sub_ratio=0.71`), matching the spec's "no mysterious labels" stance.

## Tasks

### Task 1: SQLite feature cache

**Files:** Create `library-tools/src/librarytools/featurecache.py`,
`library-tools/tests/test_featurecache.py`.

- [ ] Schema: `features(path TEXT PRIMARY KEY, size INT, mtime REAL, <feature cols>,
  error TEXT)`. Helper `get_or_none(path,size,mtime)` returns a cached row only when
  size+mtime match; `upsert(row)` writes.
- [ ] Tests: cache hit on unchanged (path,size,mtime); miss + recompute when mtime
  changes; error rows persisted and re-attempted on next run.

### Task 2: Feature extractor

**Files:** Create `library-tools/src/librarytools/audiofeatures.py`,
`library-tools/tests/test_audiofeatures.py`. Modify `pyproject.toml` (add `numpy`,
`soundfile` as deps; keep them optional-guarded so the filename tools still import without
them).

- [ ] `extract(path: Path) -> FeatureVector | ExtractError`. Decode via `soundfile`; fall
  back to `ffmpeg -f f32le` pipe for formats libsndfile rejects. Mixdown to mono, resample
  to 22050.
- [ ] Compute the feature table above with numpy. Pure functions per feature for unit
  testing against synthetic signals.
- [ ] Tests with generated fixtures: a 50 Hz sine → high `sub_ratio`, low `flatness`,
  low `centroid`; white noise → high `flatness`, high `centroid`; a click → short
  `attack_ms`, short `tail_ms`; a sustained pad → long `tail_ms`, low `onset_density`.

### Task 3: Wire features into analyze

**Files:** Modify `library-tools/src/librarytools/analyze.py`,
`library-tools/tests/test_analyze.py`.

- [ ] `build_feature_rows` reads acoustic features from the cache (populated in a pass
  over `_is_sample_source` rows) and adds the columns to `FeatureRow` and the features TSV.
- [ ] Extend `derive_character_tags` with acoustic rules **in addition to** the existing
  path rules, each carrying a numeric reason:
  - `KICKS/subby` ← `sub_ratio ≥ 0.6`; `KICKS/short` ← `tail_ms ≤ 250`;
    `KICKS/rumble-long` ← `tail_ms ≥ 700 and low_ratio high`; `clicky` ← `attack_ms ≤ 5`.
  - `HATS-CYM/metallic` ← high `flatness`+`centroid`; `tight` ← short `tail_ms`.
  - `DRUM-LOOPS/sparse|busy` ← `onset_density` thresholds; `top-<bpm>` unchanged.
  - `DRONE-ATMOS/dub-wash` ← long `duration`, low `onset_density`, dark `centroid`.
- [ ] Tests: synthetic FeatureRows with acoustic values produce the expected tags/reasons;
  path-only rows still tag as before (no regression).

### Task 4: Within-role similarity grouping

**Files:** Modify `analyze.py`, `test_analyze.py`.

- [ ] `cluster_within_role(rows) -> dict[(role, cluster_label), list[FeatureRow]]`:
  z-score normalise the numeric feature vector per role, run deterministic k-means
  (fixed seed, k chosen by simple heuristic e.g. `min(8, n//30)`), label each cluster
  from its dominant tags (`subby-short`, `rumble-long`, …), pick representatives nearest
  the centroid.
- [ ] Write `manifests/sample-intelligence-pilot/clusters-latest.tsv`
  (path, role, cluster_label, distance_to_centroid, is_representative).
- [ ] Crates draw from clusters (round-robin across clusters for diversity) instead of
  filename families, so a "punchy techno kit" spans distinct *sounds*, not distinct
  *filenames*.
- [ ] Tests: two clearly separable synthetic groups land in different clusters;
  clustering is deterministic across runs.

### Task 5: Report + docs

**Files:** Modify `analyze.py` (`write_report`), `library-tools/README.md`.

- [ ] Report gains a "Clusters" section: per role, cluster labels with counts and one
  representative each — the audition surface Robin actually reads.
- [ ] README: state the new real capability *and* its honest limit (features are acoustic
  now; semantic naming is still heuristic; Tier 2 embeddings remain future work).

### Task 6: Real pilot re-run + verification

- [ ] Recreate the venv with new deps:
  `~/.venvs/library-tools/bin/pip install -e '.[dev]'` (numpy, soundfile).
- [ ] `PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest -q -p no:cacheprovider`
  → all green.
- [ ] Run **with** audio (no `--no-probe`, features on):
  `~/.venvs/library-tools/bin/sample-analyze --root "/Volumes/Extreme SSD/Production/SAMPLES" --pilot`
  → confirm >0 rows now carry acoustic features and acoustic tag reasons, and
  `clusters-latest.tsv` is populated.
- [ ] Manual: audition one representative per KICKS cluster by ear; confirm
  `subby-short` vs `rumble-long` actually sound different. Tune thresholds only from
  concrete misses.

## Tier 0.5 fallback (if Robin rejects new deps)

Drop Tasks 2's numpy/soundfile; decode via `ffmpeg -ac 1 -ar 22050 -f f32le -` into an
`array('f')` and compute only time-domain features: `rms`, `crest`, `attack_ms`,
`tail_ms`, `zcr` (brightness proxy), `onset_density` from RMS-envelope peaks, loop-ishness
from envelope autocorrelation. No `centroid`/`flatness`/`sub_ratio` (those need an FFT →
numpy). Clustering (Task 4) runs on the reduced vector. Weaker sound insight, but zero
`pip install`.

## Tier 2 (future, opt-in — not in this plan)

Small pretrained audio embedding (CLAP/PANNs) → 512-d vector per sample, cached; enables
"more like this" and text search. Pulls in torch; gate behind an explicit
`--embed` flag so the default path stays lightweight.

## Success criteria

- >0 (target: near-100% of decodable) feature rows carry real acoustic values.
- At least some character tags cite acoustic reasons (`sub_ratio=…`, `tail_ms=…`), not
  only `path:`.
- `clusters-latest.tsv` groups sounds within a role such that representatives audibly
  differ.
- Generated crates span distinct sounds, remain small enough to audition, and stay
  read-only.
- Re-run on unchanged library is near-instant (SQLite cache hits).
