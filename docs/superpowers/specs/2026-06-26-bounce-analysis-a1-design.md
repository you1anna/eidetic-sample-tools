# Bounce / mastering analysis — Tier A1 (`analysis-tools`) — design

_Date: 2026-06-26. Status: approved, ready for implementation._

## Problem

Bounces leave the studio with no objective check. Before a mixdown re-enters the sample library or
gets taken to a club, there's no quick read on integrated loudness, true-peak (clipping risk),
spectral balance, **mono-compatibility** (critical on club rigs and for the mono Digitakt), or its
BPM/key. The 2026-06-25 operating-brief assessment identified this — Tier **A1** — as the repo's
*genuine* next build: `sample-tools` already lists `librosa`/`soundfile` only as "future work", and
nothing computes loudness today.

## Target model: analyze → report → feed back into `sample-tools`

```
bounce.wav → probe (format) → decode → {LUFS, true-peak, spectral balance, mono-compat, bpm, key}
           → per-file report + TSV → (confirmed good) → re-enter library via existing sample-tools export
```

The connection to the existing pipeline is **CLI composition, not import coupling**: a bounce that
analyses clean is sorted/named via `library-tools` and exported to hardware via `sample-tools` — A1
is a *feeder*, it does not duplicate conversion/export.

## Scope (this session)

**In scope:**
1. `bounce-analyze <file|dir>` computing: integrated **LUFS** + **true-peak** (`pyloudnorm`),
   **spectral balance** (low/mid/high energy via `librosa`), **mono-compatibility** (mid/side or
   L+R vs L−R energy delta), **BPM** estimate, **key** estimate (chroma).
2. Per-file human report + a TSV row per file for batch runs.
3. Reuse `sampletools.probe.AudioInfo` for cheap format facts before heavy decode.
4. CLI + console script + its own venv (isolates `librosa`/`numpy` from the zero-dep tools).

**Out of scope (later / never):**
- Applying fixes (no normalization/limiting) — analysis only; mastering stays manual/in-DAW.
- Loudness *correction* writing new audio (that's a future `sample-tools` mode if wanted).
- Subjective "is the mix good" judgement — this reports numbers, not taste.

## Safety guarantees

- **Read-only on audio**; writes only reports/TSV to a chosen dir. Not gated by the SSD backup.
- Heavy deps (`librosa`, `numpy`, `soundfile`, `pyloudnorm`) live in `~/.venvs/analysis-tools`
  only — they never touch the zero-dependency `sampletools`/`librarytools` runtimes.

## New tool: `analysis-tools/` (package `analysistools`)

| Module | Responsibility |
|---|---|
| `load.py` | `decode(path) -> (samples: np.ndarray, sr: int)` via `soundfile`; reuses `probe` for a fast pre-check. |
| `loudness.py` | `integrated_lufs(x, sr)`, `true_peak_dbtp(x, sr)` (`pyloudnorm` + 4× oversample). |
| `spectral.py` | `band_energy(x, sr) -> {low,mid,high}`; `mono_compat(stereo) -> float` (dB delta). |
| `tempo_key.py` | `estimate_bpm(x, sr)`, `estimate_key(x, sr)` (`librosa` beat + chroma). |
| `report.py` | `analyze(path) -> Report` dataclass; human + TSV formatting. |
| `cli.py` | `bounce-analyze` main + console script. |

**Default input:** `/Volumes/Extreme SSD/Production/outputs` (env-overridable).

**Digitakt rate caveat (cross-ref):** `sample-tools/src/sampletools/config.py:55-67` hardcodes the
Digitakt at 44100 Hz; the assessment notes it is very likely **48000**. Where A1 output is destined
for Digitakt, assume 48k once confirmed on hardware. Not fixed here — flagged so analysis→export
handoff doesn't silently resample.

## Tests (`tests/`)

Use **synthetic signals** (no fixtures of real music, fast, deterministic):
- `test_loudness.py`: a calibrated sine at a known dBFS → expected LUFS/true-peak within tolerance;
  an inter-sample-peak case flags >0 dBTP.
- `test_spectral.py`: low-freq sine → energy concentrated in `low`; a phase-inverted stereo pair →
  `mono_compat` flags incompatibility; identical L/R → compatible.
- `test_tempo_key.py`: a click train at 138 BPM → bpm≈138 within tolerance; tonal signal → stable
  key output (exact pitch class may be approximate — assert it runs and is in range).
- `monkeypatch` heavy model calls where practical to keep CI fast.

## Operator / skill path

Claude Code, local on the Mac (venv `~/.venvs/analysis-tools`). Implementation: `writing-plans` →
`test-driven-development` (synthetic-signal tests with numeric tolerances) →
`verification-before-completion` (run over a real bounce in `Production/outputs`, sanity-check LUFS
against Ableton's own meter).
