# Changelog

## Unreleased

- Add local test-environment discovery and a synthetic collection-planner scale
  benchmark. Installed-wheel checks now cover planning and offline regeneration,
  with both CI smoke passes isolated from the checkout's Python path.
- Add experimental `sample-collection` plans with explicit per-device export
  history, freshness modes, deterministic regeneration, inherited pins and
  visible shortages. Plans freeze metadata and remain unreviewed; source audio,
  existing listening decisions and export gates are unchanged.
- Require `--root` or `SAMPLES_ROOT` for sample-library commands and `--root` or
  `ALS_ROOTS` for Ableton reports; remove machine-specific library defaults.
- Add a hashed Python 3.12 Apple Silicon AI dependency snapshot and `sample-ai`
  download/doctor/offline-check commands for the two existing CLAP checkpoints.
- Expose classification thread, batch and timeout controls; default to two
  threads and two files per batch, retain completed embeddings on timeout, and
  add an opt-in CI workflow for real-model verification.
- Restore reports malformed backup metadata as a controlled CLI error before
  writing a destination, with regression coverage for preview and apply.
- Wheel checks resolve declared dependencies in a fresh base installation before
  testing the optional browser UI; CI also checks dependency consistency.
- Clarified installation, upgrades, dependency updates and routine data retention;
  development extras include browser-test dependencies and Git ignores `.eidetic/`.
- Added an experimental `sample-vibe` chooser for explicit audio candidates:
  single-source playback, Keep/Skip, Undo and a resumable shortlist.
- Kept originals can be handed to a playlist or a standard curation packet with
  their exact identities and paths. Packet creation requires a bound index and
  complete scan; favourite approval, promotion and export checks still apply.
- Preserved the optional vocal-cut audition at `/vocal-lab`, separate from the
  main chooser and its decisions.
- Documented the current limits: saved choices do not train a model or alter
  search rankings, and candidate quality has not been shown to improve. See the
  [audition guide](docs/GROOVE-AUDITION-PILOT.md).

## 0.2.0 — 2026-09-09

Libraries can now travel between independently configured Macs while retaining
their identity, current decisions and historical evidence. Each Mac runs
`sample-library onboard`; another machine's unavailable history can be deferred
without blocking new work.

- Explicit, validated upgrades from historical database schemas, with verified
  backups and refusal to modify unknown or newer state.
- Single-writer coordination, complete-scan publication, durable operation
  journals, interruption recovery, and retained decision histories.
- Repeatable capture of older databases and human files without overwriting
  active SSD decisions. Changed historical inputs require a new verified capture.
- Versioned measurements and generated tags, retained analysis reports, and
  maintenance diagnostics for caches and incomplete evidence.
- Hash-verified export receipts and selected-file transfer records. Explicit
  export roots support different mount paths. Search-generated crates retain
  approval evidence; legacy curated folders alone cannot supply it.
- Versioned Ableton report metadata records input identity and completeness,
  with replaced reports archived for comparison.
- Bundled profiles and vocabulary for installed packages, pinned test
  dependencies, and macOS/Linux CI with an installed-wheel lifecycle check.

### Upgrade notes

The default index is now `SAMPLES/.eidetic/library.sqlite`. Keep each Mac's
environment on its local disk and onboard that machine against the attached
library. Historical databases and files stay preserved; contradictory decisions
are not merged automatically. Use explicit `--library-db` and `--include` paths
for evidence outside the current checkout.

Existing unverified exports require `--force` to rebuild. Crates retain their
five-column TSV format, with new metadata sidecars. Existing preview/apply gates
and hardware profiles remain unchanged. State backups do not contain source audio.

See [setup](docs/GETTING-STARTED.md), the [lifecycle guide](docs/LIFECYCLE.md) and
the [operational record](STATUS.md) before applying changes to an existing library.
This source release does not itself migrate a live library or publish packages.
