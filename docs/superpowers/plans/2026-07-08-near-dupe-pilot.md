# Near-Dupe Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build manifest-first near-dupe detection with one-family/small-batch audition and approved-only staging.

**Architecture:** Add a focused `librarytools.neardupe` module beside `dedupe.py`. It consumes existing `sample-analyze` feature TSVs, writes review/audition artifacts, and reuses `moves.apply_plan` for reviewed staging. After Robin's short-sample audition failed, the detector is long-loop/high-certainty only by default.

**Tech Stack:** Python 3.12 standard library, existing `librarytools.moves/config`, existing pytest suite.

## Global Constraints

- Never delete sample files.
- Never move from an unreviewed detection result.
- Do not emit short one-shot near-dupe candidates by default; require long loops with `duration_s >= 3.0` and `score >= 0.99`.
- Apply only rows explicitly marked `decision=remove`.
- Move to `_TO-DELETE/near-dupes/` and write undo TSV.
- No new dependencies.

---

### Task 1: Near-Dupe Detection And Pilot Artifacts

**Files:**
- Create: `library-tools/src/librarytools/neardupe.py`
- Create: `library-tools/tests/test_neardupe.py`
- Modify: `library-tools/pyproject.toml`
- Modify: `library-tools/README.md`

**Interfaces:**
- Produces: `load_feature_rows(path: Path) -> list[FeatureRow]`, `find_groups(rows) -> list[NearDupeGroup]`, `write_review(path, groups)`, `write_audition(output_dir, groups, sample_root)`.

- [ ] Write failing tests for same-family acoustic candidates, `--family`, `--limit-groups`, and audition M3U/Markdown.
- [ ] Implement rows, grouping, scoring, canonical choice, TSV and audition writers.
- [ ] Add `sample-near-dupes = "librarytools.neardupe:main"`.
- [ ] Document one-family and small-batch dry runs.
- [ ] Run targeted tests.

### Task 2: Approved-Only Apply

**Files:**
- Modify: `library-tools/src/librarytools/neardupe.py`
- Modify: `library-tools/tests/test_neardupe.py`

**Interfaces:**
- Produces: `build_apply_plan(root: Path, reviewed_manifest: Path) -> list[moves.Move]`.

- [ ] Write failing test proving blank rows are ignored and `decision=remove` rows stage to `_TO-DELETE/near-dupes/`.
- [ ] Implement approved-only apply using `moves.apply_plan`.
- [ ] Run targeted tests and full library suite.

### Task 3: Real Pilot And Hub Note

**Files:**
- Generated: `library-tools/manifests/near-dupes-pilot/*` (gitignored)
- Modify: `/Users/macmini/Projects/command-center/tasks.md`

- [ ] Run a real dry-run pilot against `manifests/sample-intelligence-pilot/sample-features-latest.tsv` with `--limit-groups 10`.
- [ ] Inspect row count and sample checklist paths.
- [ ] Update the hub task row with command, outputs, and next Robin action.
- [ ] Commit the repo changes on `main`, leaving unrelated files alone.
