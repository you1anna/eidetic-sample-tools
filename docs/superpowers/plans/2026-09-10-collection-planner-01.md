# Collection planner increment 1

**Completed:** `8707b5f`. Later development-tool improvements are recorded in
`39a4204`; use [project status](../../../STATUS.md) for the next increment.

**Goal:** save reproducible, unreviewed candidate selections with explicit device
history, freshness and shortages, then regenerate from frozen inputs while retaining pins.

**Architecture:** a new `sample-collection` CLI reads the existing inventory and
explicit history files. It writes a new self-contained plan directory, never an
export crate or favourite decision. Regeneration reads the saved plan without
requiring the library drive. Existing search, AI ranking, review and export retain
their behaviour.

**Basis:** [collection assessment](../../COLLECTION-PLANNING-ASSESSMENT.md).
Use the repository's proportional workflow and work on `main`.

## Boundaries

- Python 3.12 and existing dependencies only; no database migration.
- Read library state through the existing guarded read-only access. Reject an
  absent identity, missing complete scan or concurrent change during capture.
- The brief is recorded context. Only explicit metadata search filters affect
  this increment's candidate population; no musical understanding claim.
- Require an explicit device, count and freshness mode for a new plan. Modes are
  `exclude`, `prefer-new` and `allow`; the first two require supplied history.
- Preserve every matching identity and its relative aliases before count or
  history exclusions, so future regeneration cannot silently refresh the pool.
- Use SHA-256 of seed plus sample identity for stable ordering. A pin retains
  membership; it grants no listening or export approval.
- Each revision uses a new output directory. Reject an existing output, symlinks
  and output inside a parent plan. Validate fully before publishing artifacts.
- No audio decoding, copying, model inference, profile edits, curation labels,
  card writes or changes to existing safety gates.

## Tasks and interfaces

### 1. Validated history adapter

Owner: worker, `collection_history.py` and `test_collection_history.py` only.

`load_history(paths, *, library_id, device) -> dict` reads explicit export receipt
files, export directories containing receipts, or the retained historical
selection format. It returns a normalized, versioned snapshot of known original
sample IDs and evidence digests. `validate_history_snapshot(...)` checks saved
snapshots without reopening their original files.

Test first: device filtering, original versus converted hashes, foreign library
identity, malformed or missing evidence, deduplication and partial/unknown coverage.
Legacy reference records inform history; their authority text is never approval.

### 2. Immutable planner and regeneration

Owner: root, `collection_snapshot.py`, `collection_plan.py` and `test_collection_plan.py`.

`create_plan(root, *, device, count, freshness, query, brief, seed, history_paths,
library_db=None) -> dict` captures a guarded inventory snapshot, then selects.
`regenerate_plan(parent, *, seed, count=None, pins=()) -> dict` inherits the frozen
population, history, device, brief, query and freshness. Existing pins are retained;
additional pins must have been selected in the parent. Reject conflicting count
or freshness constraints. All selected rows remain unreviewed.

`read_plan(path) -> dict` validates format, structure and content digest.
`write_plan(plan, output_dir, *, parent_dir=None) -> Path` publishes `plan.json`
and a concise `REVIEW.md` in a newly reserved directory. Content IDs exclude the
creation timestamp. Plan revisions record their parent content ID.

Test first: exact deduplication across aliases; metadata matches through original
aliases; exclusion without silently refilling; unknown history; reproducibility;
different seeds; pins across multiple generations; offline regeneration; tampered
plans; invalid paths/counts; source/database and parent-plan preservation.

### 3. CLI, reference and real-library preview

Owner: worker for `collection_cli.py`, package entry point and CLI tests; root for documentation.

Commands: `sample-collection plan`, `regenerate`, `show`. New-plan flags expose
root, device, count, freshness, terms/role/origin filters, brief, seed, history and
output directory. Regeneration exposes parent plan, count, seed, pins and output.
No automatic history discovery or implicit adoption of saved preferences.

Verify installed-wheel command registration outside the checkout. Run the focused
new tests, then the library suite and relevant cross-package checks. Create a
read-only demonstration against the attached library in temporary output, using
the September reference history. Compare repeat counts under explicit modes and
verify that a pinned sample survives regeneration. Measure plan capture and
regeneration; do not promote or export these unreviewed recommendations.

## Completion record

Implemented all three commands and frozen population/history snapshots. Review
also fixed Markdown rendering of private filenames/briefs, pin membership cost,
and publication coordination with library backups. Destination library identity
is checked before and inside the writer lock; external outputs remain offline.

Focused verification passed 100 tests, including concurrent database changes,
backup lock contention, invalid history, offline regeneration and unreviewed pins.
The final three-package suite passed 821 tests in 16.32 seconds; two optional
CLAP download/run checks were skipped. An installed wheel outside the checkout
regenerated a 1,200-candidate plan with its pin retained and all 240 known prior
Octatrack identities excluded. The same wheel was installed in the existing
toolkit environment without changing dependencies; its command and `pip check`
passed. `git diff --check` also passed.

The live index contained 21,689 identities. A 1,000-candidate plan excluding the
240 recorded Octatrack identities took 1.95 seconds including writing; offline
read/regeneration/write took 1.82 seconds. Its full snapshot was 9.2 MB. These are
metadata measurements, not musical-quality results; the index was unchanged.
The narrower rap/vocal query found seven candidates, four already in supplied
history; exclusion reported three candidates and a nine-candidate shortage when
12 were requested. No listening decisions or export files were changed.

Larger review queues, audio retrieval, sound-family diversity, device budgets
and export execution remain separate increments.
