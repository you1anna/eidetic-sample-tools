# Sample Intelligence Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only `sample-analyze` pilot that produces visible Octatrack Set registry, source registry, feature, tag, crate, and report artifacts for the two Elektron pack pilots.

**Architecture:** Add a focused `librarytools.analyze` module beside the existing review/sort tools. Keep phase 1 stdlib-only: classify from paths, file metadata, optional `ffprobe` duration, and inspectable rules; write TSV/Markdown/text outputs under `library-tools/manifests/`.

**Tech Stack:** Python 3.12, stdlib `argparse`, `csv`, `dataclasses`, `pathlib`, optional local `ffprobe` through existing `librarytools.probe`, pytest.

## Global Constraints

- Phase 1 is read-only against `/Volumes/Extreme SSD/Production/SAMPLES`.
- No deletes.
- No moves.
- No OT project rewrites.
- Generated artifacts live under `library-tools/manifests/` and remain gitignored unless a specific curated manifest is intentionally promoted.
- Avoid phase-1 dependencies such as `torch`, `demucs`, or large embedding models.
- Start inside `library-tools` because the output is curation/indexing, not mix/master analysis.

---

### Task 1: Octatrack Set Registry

**Files:**
- Create: `library-tools/src/librarytools/analyze.py`
- Create: `library-tools/tests/test_analyze.py`
- Modify: `library-tools/pyproject.toml`

**Interfaces:**
- Produces: `detect_ot_sets(root: Path) -> list[OtSet]`
- Produces: `write_ot_sets(path: Path, sets: list[OtSet]) -> None`
- Produces CLI: `sample-analyze --root <SAMPLES> --pilot --output-dir <DIR>`

- [ ] **Step 1: Write failing OT detector and writer tests**

```python
from pathlib import Path
import csv

from librarytools import analyze


def _make(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    return path


def test_detect_ot_set_registers_project_audio_and_docs(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Caught on Tape 808+909"
    _make(pack / "project.work")
    _make(pack / "bank01.work")
    _make(pack / "arr01.work")
    _make(pack / "pattern.strd")
    _make(pack / "AUDIO" / "COT_BD_Orig.wav")
    _make(pack / "Install Guide.pdf")

    sets = analyze.detect_ot_sets(root)

    assert len(sets) == 1
    assert sets[0].set_name == "Caught on Tape 808+909"
    assert sets[0].project_root == Path("PACKS/Caught on Tape 808+909")
    assert sets[0].audio_pool_root == Path("PACKS/Caught on Tape 808+909/AUDIO")
    assert sets[0].project_file_count == 3
    assert sets[0].strd_file_count == 1
    assert sets[0].audio_file_count == 1
    assert sets[0].doc_path == Path("PACKS/Caught on Tape 808+909/Install Guide.pdf")
    assert sets[0].handling_policy == "preserve-set"


def test_write_ot_sets_outputs_tsv(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    pack = root / "PACKS" / "Cult of SP1200"
    _make(pack / "project.work")
    _make(pack / "AUDIO" / "SP_Kick_TapeSat.wav")
    out = tmp_path / "ot-sets.tsv"

    analyze.write_ot_sets(out, analyze.detect_ot_sets(root))

    rows = list(csv.DictReader(out.open(), delimiter="\t"))
    assert rows[0]["set_name"] == "Cult of SP1200"
    assert rows[0]["inferred_device"] == "octatrack"
    assert rows[0]["handling_policy"] == "preserve-set"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`
Expected: FAIL with import/name error because `librarytools.analyze` does not exist.

- [ ] **Step 3: Implement OT detector and TSV writer**

Create `library-tools/src/librarytools/analyze.py` with an `OtSet` dataclass, ignored-file helpers, audio/doc extension sets, `detect_ot_sets`, and `write_ot_sets`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`
Expected: PASS.

- [ ] **Step 5: Add CLI entry point**

Modify `library-tools/pyproject.toml`:

```toml
sample-analyze = "librarytools.analyze:main"
```

- [ ] **Step 6: Commit**

Run: `git add library-tools/src/librarytools/analyze.py library-tools/tests/test_analyze.py library-tools/pyproject.toml docs/superpowers/plans/2026-07-07-sample-intelligence-pilot.md && git commit -m "feat(library): register octatrack sample sets"`

### Task 2: Source Registry And Suffix Tags

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Produces: `parse_processing_suffix(path: Path) -> tuple[str, str]`
- Produces: `build_source_registry(root: Path, ot_sets: list[OtSet]) -> list[SourceRow]`
- Produces: `write_source_registry(path: Path, rows: list[SourceRow]) -> None`

- [ ] **Step 1: Write failing source registry tests**

Tests should prove AppleDouble/hidden files are ignored, OT audio is marked `octatrack-set-audio`, OT project files are marked `octatrack-set-project`, PDFs are `document`, curated files are `curated-sample`, and suffixes map `Orig`, `Tape`, `TapeSat`, `X`, `X2` to inspectable tags.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 3: Implement registry rows and suffix parser**

Add `SourceRow`, `parse_processing_suffix`, `build_source_registry`, and `write_source_registry`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 5: Commit**

Run: `git add library-tools/src/librarytools/analyze.py library-tools/tests/test_analyze.py && git commit -m "feat(library): index sample intelligence sources"`

### Task 3: Feature Rows And Character Tags

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Produces: `build_feature_rows(root: Path, sources: list[SourceRow], probe_durations: bool = False) -> list[FeatureRow]`
- Produces: `derive_character_tags(row: FeatureRow) -> tuple[str, str]`
- Produces: `write_features(path: Path, rows: list[FeatureRow]) -> None`

- [ ] **Step 1: Write failing feature/tag tests**

Tests should cover KICKS short/subby from path and duration, HATS-CYM metallic/tight from path/name hints, DRUM-LOOPS sparse/top/BPM hints, and TapeSat suffix producing `tape-saturated` with reason.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 3: Implement lightweight feature rows and tag rules**

Reuse `librarytools.review.build_item` for role, sample type, BPM, key, tempo fit, proposed names, and add inspectable tag/reason strings.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 5: Commit**

Run: `git add library-tools/src/librarytools/analyze.py library-tools/tests/test_analyze.py && git commit -m "feat(library): derive sample character tags"`

### Task 4: Device Crate Suggestions

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Produces: `build_crates(rows: list[FeatureRow]) -> dict[str, list[CrateEntry]]`
- Produces: `write_crates(output_dir: Path, crates: dict[str, list[CrateEntry]]) -> None`

- [ ] **Step 1: Write failing crate tests**

Tests should prove Digitakt and TR-8S crates stay tight and one-shot oriented, Octatrack includes a whole-Set install plan plus usable pool paths, and Ableton includes broader audition rows.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 3: Implement deterministic crate selection**

Select small, stable sorted lists. Device manifests must be plain text paths relative to `SAMPLES_ROOT`, matching `sample-tools` manifest style.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 5: Commit**

Run: `git add library-tools/src/librarytools/analyze.py library-tools/tests/test_analyze.py && git commit -m "feat(library): suggest hardware sample crates"`

### Task 5: Pilot CLI And Report

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`
- Modify: `library-tools/README.md`

**Interfaces:**
- Produces CLI: `sample-analyze --root <SAMPLES> --pilot --output-dir manifests/sample-intelligence-pilot --no-probe`
- Produces: `ot-sets-latest.tsv`, `source-registry-latest.tsv`, `sample-features-latest.tsv`, `crates/<device>/*.txt`, `reports/pilot.md`

- [ ] **Step 1: Write failing CLI integration test**

Test that a synthetic root produces every expected artifact and leaves source files untouched.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`

- [ ] **Step 3: Implement CLI orchestration and Markdown report**

Wire `main()` to run detector, registry, features, crates, and report writers.

- [ ] **Step 4: Run focused and full tests**

Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py -v`
Run: `cd library-tools && ~/.venvs/library-tools/bin/python -m pytest -q`

- [ ] **Step 5: Commit**

Run: `git add library-tools/src/librarytools/analyze.py library-tools/tests/test_analyze.py library-tools/README.md && git commit -m "feat(library): add sample analyze pilot cli"`

### Task 6: Real Pilot Run

**Files:**
- Generated only under `library-tools/manifests/` unless an artifact is intentionally promoted later.

**Interfaces:**
- Consumes: `sample-analyze`
- Produces: real pilot outputs for Caught on Tape and Cult of SP1200 where available.

- [ ] **Step 1: Run real pilot without probing first**

Run: `cd library-tools && ~/.venvs/library-tools/bin/sample-analyze --root "/Volumes/Extreme SSD/Production/SAMPLES" --pilot --no-probe`

- [ ] **Step 2: Inspect counts**

Run: `wc -l library-tools/manifests/sample-intelligence-pilot/*latest.tsv`
Run: `find library-tools/manifests/sample-intelligence-pilot/crates -type f -maxdepth 3 -print`

- [ ] **Step 3: If pilot packs are absent, report absence clearly**

Expected: command exits 0 and writes an empty or partial report explaining what was found.

- [ ] **Step 4: Commit only source/docs**

Generated manifests remain gitignored. Commit source and docs only after tests and pilot command complete.
