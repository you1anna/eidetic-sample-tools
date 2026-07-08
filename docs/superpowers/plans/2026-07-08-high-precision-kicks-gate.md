# High-Precision KICKS Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a manifest-only KICKS gate to `sample-analyze` so contaminated KICKS rows are bucketed as `likely_kick`, `review`, or `reject_as_kick`, and only `likely_kick` rows can become KICKS representatives or device-crate picks.

**Architecture:** Keep the work inside `librarytools.analyze`, beside the existing Tier-1 feature rows, cluster selection, crate selection, and curated-role conflict code. The gate is a deterministic evidence ladder over existing `FeatureRow` acoustic fields and role-conflict signals; it writes a TSV audit and reuses the same gate inside representative/crate candidate filters.

**Tech Stack:** Python 3.12, existing `numpy`/`soundfile` Tier-1 feature cache, stdlib `csv`/`dataclasses`/`pathlib`, pytest. No new dependencies.

## Global Constraints

- Manifest-only against `/Volumes/Extreme SSD/Production/SAMPLES`.
- No sample moves, deletes, renames, conversions, or SSD cleanup.
- No `sample-sort` / `sample-intake` changes.
- No PANNs, YAMNet, CLAP, Basic Pitch, ADTOF, torch, TensorFlow, or model downloads in this pass.
- Optimize for precision: a real but ambiguous kick may stay in `review`; a non-kick must not become a KICKS representative.
- Use only existing cached acoustic features: duration, attack, tail, low/sub/high ratios, centroid, flatness, onset density, crest, and zcr.
- A fresh Robin ear-check is required before wider taxonomy rollout or any physical reclassification manifest.

---

## File Structure

- Modify `library-tools/src/librarytools/analyze.py`: add `KickGateRow`, `kick_gate`, `kick_audit`, `write_kick_audit`, gate-aware candidate filtering, CLI/report integration.
- Modify `library-tools/tests/test_analyze.py`: add tests for gate buckets, known failed KICKS representatives, TSV output, representative/crate exclusion, and CLI artifact writing.
- Modify `library-tools/README.md`: document `kick-audit-latest.tsv`, gate meanings, and the high-precision KICKS workflow.
- Generated only: `library-tools/manifests/sample-intelligence-pilot/kick-audit-latest.tsv` during real runs. This stays gitignored.

---

### Task 1: Audit Row And TSV Writer

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Produces: `KickGateRow`
- Produces: `write_kick_audit(path: Path, rows: list[KickGateRow]) -> None`

- [ ] **Step 1: Write the failing TSV writer test**

Add this near the other writer tests in `library-tools/tests/test_analyze.py`:

```python
def test_write_kick_audit_outputs_required_columns(tmp_path: Path):
    rows = [
        analyze.KickGateRow(
            path=Path("CURATED/KICKS/solid.wav"),
            current_role="KICKS",
            sample_type="one-shot",
            duration_s=0.31,
            attack_ms=4.0,
            tail_ms=180.0,
            sub_ratio=0.82,
            low_ratio=0.91,
            mid_ratio=0.08,
            high_ratio=0.01,
            centroid_hz=180.0,
            flatness=0.02,
            onset_density=0.5,
            zcr=0.02,
            kick_gate="likely_kick",
            confidence="high",
            reasons="sub_ratio=0.82;crest=8",
            review_action="audition-as-kick",
        )
    ]
    out = tmp_path / "kick-audit-latest.tsv"

    analyze.write_kick_audit(out, rows)

    written = list(csv.DictReader(out.open(), delimiter="\t"))
    assert written[0]["path"] == "CURATED/KICKS/solid.wav"
    assert written[0]["kick_gate"] == "likely_kick"
    assert written[0]["review_action"] == "audition-as-kick"
```

- [ ] **Step 2: Run the focused test and verify it fails**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest tests/test_analyze.py::test_write_kick_audit_outputs_required_columns -v -p no:cacheprovider
```

Expected: FAIL with `AttributeError: module 'librarytools.analyze' has no attribute 'KickGateRow'`.

- [ ] **Step 3: Add the audit dataclass and writer**

In `library-tools/src/librarytools/analyze.py`, add this dataclass after `CuratedRoleConflict`:

```python
@dataclass(frozen=True)
class KickGateRow:
    path: Path
    current_role: str
    sample_type: str
    duration_s: float | None
    attack_ms: float | None
    tail_ms: float | None
    sub_ratio: float | None
    low_ratio: float | None
    mid_ratio: float | None
    high_ratio: float | None
    centroid_hz: float | None
    flatness: float | None
    onset_density: float | None
    zcr: float | None
    kick_gate: str
    confidence: str
    reasons: str
    review_action: str
```

Add this writer near `write_curated_role_conflicts`:

```python
def _fmt_audit_value(value: float | None) -> str:
    return _fmt_num(value) if value is not None else ""


def write_kick_audit(path: Path, rows: list[KickGateRow]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, delimiter="\t")
        writer.writerow([
            "path", "current_role", "sample_type", "duration_s", "attack_ms", "tail_ms",
            "sub_ratio", "low_ratio", "mid_ratio", "high_ratio", "centroid_hz",
            "flatness", "onset_density", "zcr", "kick_gate", "confidence",
            "reasons", "review_action",
        ])
        for row in rows:
            writer.writerow([
                row.path.as_posix(), row.current_role, row.sample_type,
                _fmt_audit_value(row.duration_s), _fmt_audit_value(row.attack_ms),
                _fmt_audit_value(row.tail_ms), _fmt_audit_value(row.sub_ratio),
                _fmt_audit_value(row.low_ratio), _fmt_audit_value(row.mid_ratio),
                _fmt_audit_value(row.high_ratio), _fmt_audit_value(row.centroid_hz),
                _fmt_audit_value(row.flatness), _fmt_audit_value(row.onset_density),
                _fmt_audit_value(row.zcr), row.kick_gate, row.confidence,
                row.reasons, row.review_action,
            ])
```

- [ ] **Step 4: Run the focused test and verify it passes**

Run the same pytest command from Step 2.

Expected: PASS.

### Task 2: Gate Rules And Regression Fixtures

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Consumes: `FeatureRow`
- Produces: `kick_gate(row: FeatureRow) -> KickGateRow`

- [ ] **Step 1: Extend the `_feature_row` test helper**

Replace `_feature_row` in `library-tools/tests/test_analyze.py` with a version that accepts these extra keyword arguments and passes them through to `analyze.FeatureRow`: `sample_type`, `duration`, `peak`, `rms`, `crest`, `attack_ms`, `low_ratio`, `mid_ratio`, `high_ratio`, `onset_density`, `zcr`, and `audio_error`. Keep the current default values for existing tests, except set `duration_s=duration` and `audio_error=audio_error`.

- [ ] **Step 2: Write failing gate tests**

Add tests for these exact cases:

```python
def test_kick_gate_marks_strong_compact_low_transient_as_likely():
    row = _feature_row(
        "CURATED/KICKS/solid-low-transient.wav",
        source_kind="curated-sample",
        sub_ratio=0.82,
        low_ratio=0.91,
        high_ratio=0.01,
        tail_ms=180.0,
        centroid_hz=180.0,
        flatness=0.02,
        tags="subby;short",
        duration=0.31,
        crest=8.0,
        attack_ms=3.5,
        onset_density=0.4,
        zcr=0.02,
    )

    gate = analyze.kick_gate(row)

    assert gate.kick_gate == "likely_kick"
    assert gate.confidence == "high"
    assert gate.review_action == "audition-as-kick"
```

```python
def test_kick_gate_rejects_role_conflicts_and_loops():
    clap = _feature_row(
        "CURATED/KICKS/kick-clap-lastmin2-sp12f_samples.wav",
        source_kind="curated-sample",
        sub_ratio=0.3,
        low_ratio=0.3,
        high_ratio=0.2,
        tail_ms=220,
        centroid_hz=1200,
        flatness=0.1,
        tags="short",
    )
    loop = _feature_row(
        "CURATED/KICKS/Kick Loops/Kick020.wav",
        source_kind="curated-sample",
        sub_ratio=0.8,
        low_ratio=0.9,
        high_ratio=0.02,
        tail_ms=900,
        centroid_hz=140,
        flatness=0.02,
        tags="subby;rumble-long",
        sample_type="loop",
        duration=4.0,
        crest=5.5,
        onset_density=5.0,
    )

    assert analyze.kick_gate(clap).kick_gate == "reject_as_kick"
    assert analyze.kick_gate(loop).kick_gate == "reject_as_kick"
```

```python
def test_kick_gate_routes_missing_or_borderline_audio_to_review():
    missing = _feature_row(
        "CURATED/KICKS/unreadable.wav",
        source_kind="curated-sample",
        sub_ratio=0.0,
        low_ratio=0.0,
        high_ratio=0.0,
        tail_ms=0.0,
        centroid_hz=0.0,
        flatness=0.0,
        tags="",
        audio_error="decode failed",
    )
    borderline = _feature_row(
        "CURATED/KICKS/borderline-low.wav",
        source_kind="curated-sample",
        sub_ratio=0.44,
        low_ratio=0.5,
        high_ratio=0.08,
        tail_ms=260,
        centroid_hz=900,
        flatness=0.08,
        tags="short",
        duration=0.45,
        crest=6.0,
    )

    assert analyze.kick_gate(missing).kick_gate == "review"
    assert analyze.kick_gate(missing).review_action == "decode-or-manual-review"
    assert analyze.kick_gate(borderline).kick_gate == "review"
```

Add one regression test named `test_kick_gate_does_not_pass_failed_kicks_audition_representatives`. Build rows for the 8 failed representatives in `library-tools/manifests/sample-intelligence-pilot/audition/kicks-representatives.md` using the numeric values in `sample-features-latest.tsv`; assert no row returns `likely_kick`.

- [ ] **Step 3: Run the focused tests and verify they fail**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest \
  tests/test_analyze.py::test_kick_gate_marks_strong_compact_low_transient_as_likely \
  tests/test_analyze.py::test_kick_gate_rejects_role_conflicts_and_loops \
  tests/test_analyze.py::test_kick_gate_routes_missing_or_borderline_audio_to_review \
  tests/test_analyze.py::test_kick_gate_does_not_pass_failed_kicks_audition_representatives \
  -v -p no:cacheprovider
```

Expected: FAIL with `AttributeError: module 'librarytools.analyze' has no attribute 'kick_gate'`.

- [ ] **Step 4: Implement the gate**

Add constants and helper functions in `library-tools/src/librarytools/analyze.py`:

```python
KICK_MIN_LIKELY_SUB_RATIO = 0.55
KICK_MIN_LIKELY_LOW_RATIO = 0.55
KICK_MAX_LIKELY_HIGH_RATIO = 0.25
KICK_MAX_LIKELY_DURATION_S = 0.90
KICK_MAX_LIKELY_TAIL_MS = 450.0
KICK_MAX_LIKELY_CENTROID_HZ = 2200.0
KICK_MAX_LIKELY_FLATNESS = 0.45
KICK_MAX_LIKELY_ONSET_DENSITY = 2.0
KICK_MIN_LIKELY_CREST = 5.0
KICK_MAX_LIKELY_ZCR = 0.12
```

Implement `kick_gate(row)` with this order:

1. If the current role is not `KICKS`, return `review` / `not-kicks-scope`.
2. If `curated_role_conflict(row)` returns a conflict, return `reject_as_kick`.
3. If `row.audio_error` is set or required acoustic fields are missing, return `review`.
4. If `sample_type == "loop"`, `duration_s >= 3.0`, or `onset_density >= 4.0`, return `reject_as_kick`.
5. If `high_ratio >= 0.45`, or `centroid_hz >= 3500 and sub_ratio < 0.45`, or `zcr >= 0.18`, return `reject_as_kick`.
6. Return `likely_kick` only when all constants above pass.
7. Return `review` for every remaining KICKS row.

- [ ] **Step 5: Run the focused tests and verify they pass**

Run the same pytest command from Step 3.

Expected: PASS.

### Task 3: Audit Builder And Gate-Aware Selection

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`

**Interfaces:**
- Consumes: `kick_gate(row: FeatureRow) -> KickGateRow`
- Produces: `kick_audit(rows: list[FeatureRow]) -> list[KickGateRow]`
- Changes: KICKS rows must pass `likely_kick` before `_cluster_vector`, `_device_one_shot_candidate`, or `_audition_candidate` can select them.

- [ ] **Step 1: Write failing tests**

Add tests proving:

```python
def test_kick_audit_includes_only_kicks_candidates_sorted_by_path():
    # Include one HATS-CYM row, one likely KICKS row, and one review KICKS row.
    # Assert only the two KICKS rows appear, sorted by path, with gates ["review", "likely_kick"].
```

```python
def test_cluster_within_role_uses_only_likely_kicks_for_kicks():
    # Use two likely KICKS rows and one review KICKS row.
    # Assert cluster output contains a likely path and excludes the review path.
```

```python
def test_build_crates_excludes_non_likely_kicks():
    # Build crates from one likely KICKS row and one review KICKS row.
    # Assert the likely path appears somewhere and the review path appears nowhere.
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest \
  tests/test_analyze.py::test_kick_audit_includes_only_kicks_candidates_sorted_by_path \
  tests/test_analyze.py::test_cluster_within_role_uses_only_likely_kicks_for_kicks \
  tests/test_analyze.py::test_build_crates_excludes_non_likely_kicks \
  -v -p no:cacheprovider
```

Expected: FAIL because `kick_audit` does not exist and KICKS candidate filters still allow review rows.

- [ ] **Step 3: Add audit builder and gate-aware filters**

Add:

```python
def kick_audit(rows: list[FeatureRow]) -> list[KickGateRow]:
    return sorted(
        [
            kick_gate(row)
            for row in rows
            if row.role == "KICKS" or (_curated_folder_role(row.path) or row.role) == "KICKS"
        ],
        key=lambda item: item.path.as_posix(),
    )


def _passes_kick_gate(row: FeatureRow) -> bool:
    return row.role != "KICKS" or kick_gate(row).kick_gate == "likely_kick"
```

Then require `_passes_kick_gate(row)` in `_cluster_vector`, `_device_one_shot_candidate`, and `_audition_candidate`.

- [ ] **Step 4: Run focused tests and existing representative/crate tests**

Run the focused command from Step 2, then:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest \
  tests/test_analyze.py::test_cluster_within_role_separates_synthetic_audio_groups_deterministically \
  tests/test_analyze.py::test_build_crates_keeps_digitakt_and_tr8s_one_shot_oriented \
  tests/test_analyze.py::test_build_crates_includes_octatrack_set_install_plan \
  -v -p no:cacheprovider
```

Expected: PASS.

### Task 4: CLI Artifact, Report Counts, And README

**Files:**
- Modify: `library-tools/src/librarytools/analyze.py`
- Modify: `library-tools/tests/test_analyze.py`
- Modify: `library-tools/README.md`

**Interfaces:**
- Consumes: `kick_audit(rows: list[FeatureRow]) -> list[KickGateRow]`
- Produces CLI artifact: `kick-audit-latest.tsv`
- Extends `write_report(..., kick_audit_rows: list[KickGateRow] | None = None) -> None`

- [ ] **Step 1: Write failing CLI and report tests**

Extend `test_main_writes_full_pilot_artifacts_without_moving_sources` with:

```python
assert (out / "kick-audit-latest.tsv").exists()
```

Add a report test that calls:

```python
analyze.write_report(out, [], [], [], {}, kick_audit_rows=audit)
```

Assert the report contains:

```text
## KICKS Gate
- likely_kick: 1
- review: 1
```

- [ ] **Step 2: Run focused tests and verify they fail**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest \
  tests/test_analyze.py::test_main_writes_full_pilot_artifacts_without_moving_sources \
  tests/test_analyze.py::test_report_includes_kick_gate_counts \
  -v -p no:cacheprovider
```

Expected: FAIL because the CLI does not write `kick-audit-latest.tsv` and `write_report` has no `kick_audit_rows` parameter.

- [ ] **Step 3: Integrate audit into report and CLI**

In `main`, compute:

```python
kick_audit_rows = kick_audit(features)
```

Write:

```python
write_kick_audit(args.output_dir / "kick-audit-latest.tsv", kick_audit_rows)
```

Pass `kick_audit_rows` to `write_report`, and print:

```python
print(f"  KICKS audit rows: {len(kick_audit_rows)}")
```

In `write_report`, add a `## KICKS Gate` section with counts for `likely_kick`, `review`, and `reject_as_kick`.

- [ ] **Step 4: Update README**

Add `kick-audit-latest.tsv` to the generated artifact list. Document:

```markdown
For KICKS, trust only the high-precision gate. `likely_kick` rows can enter the next audition packet; `review` rows need manual ear-check before use as KICKS; `reject_as_kick` rows remain visible in manifests but are excluded from KICKS representatives and device-crate picks. This does not move or rename files.
```

- [ ] **Step 5: Run focused tests and verify they pass**

Run the same focused pytest command from Step 2.

Expected: PASS.

### Task 5: Full Verification And Real Pilot Run

**Files:**
- Generated only under `library-tools/manifests/`

**Interfaces:**
- Consumes: `sample-analyze --pilot`
- Produces: refreshed `kick-audit-latest.tsv`, `clusters-latest.tsv`, crates, and report with KICKS gate counts.

- [ ] **Step 1: Run the full test suite**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
PYTHONPATH=src ~/.venvs/library-tools/bin/python -m pytest -q -p no:cacheprovider
```

Expected: all tests pass.

- [ ] **Step 2: Run the real manifest-only pilot**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
~/.venvs/library-tools/bin/sample-analyze --root "/Volumes/Extreme SSD/Production/SAMPLES" --pilot
```

Expected: command exits 0, prints `[MANIFEST-ONLY]`, and writes under `library-tools/manifests/sample-intelligence-pilot/`. No files under `/Volumes/Extreme SSD/Production/SAMPLES` are moved, renamed, deleted, converted, or copied.

- [ ] **Step 3: Inspect KICKS gate counts**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
python3 -c 'import csv,collections,pathlib; rows=csv.DictReader(pathlib.Path("manifests/sample-intelligence-pilot/kick-audit-latest.tsv").open(), delimiter="\t"); print(collections.Counter(row["kick_gate"] for row in rows))'
```

Expected: output includes `likely_kick` and `review`. If the counter prints only `likely_kick`, tighten Task 2 thresholds using the failed representative fixtures.

- [ ] **Step 4: Verify KICKS representatives are all likely kicks**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
python3 -c 'import csv,pathlib; audit={r["path"]: r["kick_gate"] for r in csv.DictReader(pathlib.Path("manifests/sample-intelligence-pilot/kick-audit-latest.tsv").open(), delimiter="\t")}; bad=[]; rows=csv.DictReader(pathlib.Path("manifests/sample-intelligence-pilot/clusters-latest.tsv").open(), delimiter="\t"); [bad.append((r["path"], audit.get(r["path"]))) for r in rows if r["role"]=="KICKS" and r["is_representative"]=="yes" and audit.get(r["path"])!="likely_kick"]; print(bad)'
```

Expected: `[]`.

- [ ] **Step 5: Verify device crates do not contain non-likely KICKS**

Run:

```bash
cd /Users/macmini/Projects/eidetic-music-tools/library-tools
python3 -c 'import csv,pathlib; audit={r["path"]: r["kick_gate"] for r in csv.DictReader(pathlib.Path("manifests/sample-intelligence-pilot/kick-audit-latest.tsv").open(), delimiter="\t")}; bad=[]; root=pathlib.Path("manifests/sample-intelligence-pilot/crates"); files=list(root.rglob("*.txt")); [bad.append((p.as_posix(), line.strip(), audit.get(line.strip()))) for p in files for line in p.read_text().splitlines() if line and not line.startswith("#") and line.strip() in audit and audit[line.strip()]!="likely_kick"]; print(bad)'
```

Expected: `[]`.

## Self-Review

- Spec coverage: the plan implements the manifest output, three gate buckets, existing-feature-only evidence ladder, representative/crate exclusion, tests against known failed KICKS examples, and real-run verification.
- Boundaries: the plan excludes sample moves, `sample-sort`, `sample-intake`, and heavy ML.
- Type consistency: `KickGateRow`, `kick_gate`, `kick_audit`, `write_kick_audit`, and `kick_audit_rows` are defined before later tasks consume them.
