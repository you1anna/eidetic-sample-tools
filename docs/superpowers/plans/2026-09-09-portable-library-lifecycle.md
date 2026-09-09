# Portable library lifecycle implementation

Approved in the task conversation on 2026-09-09. One portable library on an
external SSD; either attached Mac can continue work, with one writer at a time.

## Deliverables

- [x] Validated schema migrations, portable UUID identity, read-only diagnostics,
  backup/restore, maintenance preview and atomic inventory publication.
- [x] Durable move/promotion/undo records, recovery, immutable listening packets,
  active promotion views and preservation of human tags.
- [x] Versioned feature extraction, explicit retries and conservative legacy import.
- [x] Verified export receipts, versioned crates and transfer evidence.
- [x] Portable CLI defaults, packaged resources, release versions, repeatable test
  environment, CI and lifecycle documentation.
- [x] Historical schema and interruption tests, integrated lifecycle verification.

## Verification

On 2026-09-09, the complete Python 3.12 suite passed: **566 passed, 2 skipped**.
The skipped checks download and run optional CLAP model checkpoints. The integrated
rehearsal covers schema-1 migration, preserved reviews, scan, listening approval,
promotion, changed mount path, real FFmpeg export and reuse, backup, undo and restore.
Additional tests cover interruption recovery, writer exclusion, future-schema
rejection and read-only evidence inspection. All three 0.2.0 wheels were built and
installed outside the checkout; packaged CLI entry points, resources and a generated
library lifecycle passed smoke checks. macOS/Linux CI is configured but has not run
remotely. See [the lifecycle guide](../../LIFECYCLE.md) for operational commands.

The per-machine rehearsal starts without the older Mac, captures its history later,
preserves current SSD decisions, and verifies repeated setup and changed mount paths.
Regression tests cover identical local paths on different Macs, later-added evidence,
interrupted publication, malformed metadata, archive completeness, and SQLite journals
in additional historical files. Installed wheels also passed real FFmpeg export and
reuse after remount, approval checks, historical capture, backup and restore. A
read-only onboarding preview on the attached SSD succeeded with the Mac mini deferred;
it made no state changes.

Finalisation aligned canonical examples with portable run directories, completed
command help and release notes, and added a reusable installed-package check to
CI. Final regressions cover selected-root defaults in secondary commands and
export manifests, malformed adoption metadata, and corrupt gzip report inputs.
All three final wheels were rebuilt and passed the smoke check in a new Python
3.12 environment outside the checkout. Documentation links and shell examples
were checked; no source audio, live databases or generated user evidence was added.

## Constraints and implementation rulings

Source audio and private operational evidence never enter this public repository.
Do not mutate the attached SSD during implementation. Preserve profiles and all
existing preview/apply gates. The user's follow-up clarifies that each machine must
work independently and the Mac mini may be unavailable for some time. Onboarding
can therefore create usable SSD state with explicitly incomplete historical coverage;
an empty database on the Air is not a replacement for the mini's history.

Use a feature branch in the existing checkout so the result is visible in this
task. Tests use an isolated temporary Python 3.12 environment because the Air lacks
the documented package environments. No global packages are installed.

Database versioning and state discovery are implemented first, with independent
operation/export work in parallel. Inventory owns schema changes; consumers use
its versioned feature, tag and promotion APIs. TSV crate columns remain compatible;
new sidecars declare their format version. Legacy evidence is preserved and unknown
provenance is represented explicitly.

## Independent machine onboarding follow-up

- [x] Repeatable preview/apply onboarding: create, adopt available legacy state,
  or reuse the active SSD database without requiring another machine.
- [x] Preserve later-arriving databases and human files in verified archives;
  retain pending historical review, detect further offline changes, never merge
  decisions or overwrite the active database automatically.
- [x] Explicit export root selection to avoid stale paths from another Mac.
- [x] Preserve search and audition while requiring recorded approval evidence in
  newly generated hardware crates after onboarding with incomplete history.
- [x] Rehearse absent-machine startup, returning-machine history, changed mount,
  repeated setup, interrupted capture and backup/restore.

## Per-machine rollout

Implementation and tests do not change the attached SSD. Each machine can run
onboarding whenever it is available. Record unavailable history explicitly, preserve
and compare it when that machine returns, and keep unresolved decisions visible.
Never merge conflicting databases automatically or infer approval from existing
CURATED paths. The Mac mini is not a prerequisite for MacBook setup or use.
