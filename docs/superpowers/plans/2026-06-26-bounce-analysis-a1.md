# Bounce / Mastering Analysis — Tier A1 (`analysis-tools`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans). Steps use `- [ ]` checkboxes.

**Goal:** A new `analysis-tools` package (`analysistools`, console script `bounce-analyze`) that
reports integrated LUFS, true-peak, spectral balance, mono-compatibility, BPM and key for a bounce
or a directory of bounces — designed to feed confirmed output back into the existing `sample-tools`
export pipeline (CLI composition, not import coupling).

**Architecture:** `src/analysistools/{load,loudness,spectral,tempo_key,report,cli}.py`. Pure-ish DSP
functions over numpy arrays; `report.analyze(path)` orchestrates; CLI formats human + TSV. Reuses
`sampletools.probe.AudioInfo` for a cheap format pre-check before full decode.

**Tech Stack:** Python 3.12, `numpy`, `soundfile`, `librosa`, `pyloudnorm`, pytest. **Heavy deps
isolated** in `~/.venvs/analysis-tools` — never added to the zero-dep `sampletools`/`librarytools`.

## Global Constraints
- Python 3.12; type hints; `pathlib`.
- **Read-only on audio**; writes only reports/TSV to a chosen dir. Not gated by SSD backup.
- Tests use **synthetic signals** with numeric tolerances — no real-music fixtures, no network,
  no model downloads in CI (`monkeypatch` heavy calls where needed).
- Default input root `ANALYSIS_ROOT`, default `/Volumes/Extreme SSD/Production/outputs`.
- **Digitakt rate caveat:** output destined for Digitakt assumes 48 kHz once confirmed (see
  `sample-tools/config.py:55-67`, currently 44100) — surface in the report, don't resample here.

---

### Task 1: Decode + format pre-check — `load.py`
**Files:** Create `analysis-tools/src/analysistools/load.py`, `tests/test_load.py`.
**Interface:** `decode(path) -> tuple[np.ndarray, int]` (shape `(n,)` mono or `(n,2)` stereo), via
`soundfile.read`; `quick_info(path)` delegates to `sampletools.probe` when importable, else ffprobe.

- [ ] **Step 1: Failing test** — write a synthetic WAV with `soundfile.write` (e.g. 1 s 440 Hz at
  44.1k), assert `decode` returns the right sample count and sr.
- [ ] **Step 2: Run → fail** — [ ] **Step 3: Implement** — [ ] **Step 4: Run → pass**
- [ ] **Step 5: Commit** — `feat(analysis): audio decode + format pre-check`

---

### Task 2: Loudness — `loudness.py`
**Files:** Create `loudness.py`, `tests/test_loudness.py`.
**Interface:** `integrated_lufs(x, sr) -> float`; `true_peak_dbtp(x, sr) -> float`.

- [ ] **Step 1: Failing test** — a full-scale sine → LUFS in an expected band; a signal scaled to a
  known dBFS → true-peak within tolerance; an inter-sample-peak construction → `>0 dBTP`.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — `pyloudnorm.Meter(sr).integrated_loudness(x)`; true-peak via 4×
  oversample (`librosa.resample` or polyphase) then `20*log10(max(abs))`.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(analysis): LUFS + true-peak`

---

### Task 3: Spectral balance + mono-compat — `spectral.py`
**Files:** Create `spectral.py`, `tests/test_spectral.py`.
**Interface:** `band_energy(x, sr) -> dict[str,float]` (low <250, mid 250–4k, high >4k, normalized);
`mono_compat(stereo, sr) -> float` (dB energy delta of `L-R` vs `L+R`; near 0 = mono-safe).

- [ ] **Step 1: Failing test** — 60 Hz sine → energy concentrated in `low`; identical L/R → high
  mono-compat (delta near 0); phase-inverted L/R → flagged incompatible (large negative delta).
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — `np.fft.rfft` magnitude binned to bands; mid/side from
  `(L+R)/2`,`(L-R)/2` energies.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(analysis): spectral balance + mono-compat`

---

### Task 4: Tempo + key — `tempo_key.py`
**Files:** Create `tempo_key.py`, `tests/test_tempo_key.py`.
**Interface:** `estimate_bpm(x, sr) -> float`; `estimate_key(x, sr) -> str`.

- [ ] **Step 1: Failing test** — a click train at 138 BPM → bpm within ±2; a tonal signal → a key
  string in the valid set (exact pitch class may be approximate — assert range/format, not exact).
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — `librosa.beat.beat_track` for BPM (clamp/round to the techno
  120–150 sanity range); chroma → Krumhansl-style key estimate or `librosa` chroma argmax mapped to
  pitch-class names + major/minor heuristic.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(analysis): bpm + key estimate`

---

### Task 5: Report + `bounce-analyze` CLI + packaging
**Files:** Create `report.py`, `cli.py`, `__init__.py`, `pyproject.toml`, `README.md`, `tests/test_report.py`.
**Interface:** `Report` dataclass; `analyze(path) -> Report`; human + TSV formatting;
`bounce-analyze = "analysistools.cli:main"`.

- [ ] **Step 1: Failing test** — `analyze` on a synthetic WAV returns a populated `Report`; CLI over
  a tmp dir writes a TSV with one row per file.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — orchestrate Tasks 1–4; human report (e.g. `LUFS -7.2  TP +0.3dBTP(!)
  mono:ok  bpm 138  key Amin  balance: bass-heavy`) + TSV; `--tsv`, `--root`.
- [ ] **Step 4: pyproject** — `dependencies = ["numpy","soundfile","librosa","pyloudnorm"]`,
  `dev=["pytest>=8"]`, console script, `packages.find where=["src"]`.
- [ ] **Step 5: venv + suite**
```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/analysis-tools
~/.venvs/analysis-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/analysis-tools[dev]"
~/.venvs/analysis-tools/bin/pytest /Users/macmini/Projects/eidetic-music-tools/analysis-tools -v
```
- [ ] **Step 6: Real-world smoke** — run on a real bounce in `Production/outputs`, sanity-check LUFS
  against Ableton's loudness meter (`verification-before-completion`).
- [ ] **Step 7: Commit** — `feat(analysis): bounce-analyze CLI + packaging`

---

## Self-Review
- Decode/loudness/spectral/tempo-key/report each test-first with synthetic signals. ✓
- Read-only on audio; reports only. ✓
- Heavy deps isolated in their own venv; zero-dep tools untouched. ✓
- Designed as a feeder into `sample-tools`, not a duplicate export path. ✓
- Digitakt 48k caveat surfaced. ✓
