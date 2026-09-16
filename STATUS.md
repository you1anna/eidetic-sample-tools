# Project status

**Updated:** 2026-09-16

## Current position

The current objective is to build larger, more varied collections for Octatrack,
Digitakt and TR-8S from a musical brief, with clear repeat controls and budgets
appropriate to each device. Work proceeds in bounded increments with user input
when the musical direction or selection policy is uncertain.

Local AI is part of the intended musical-brief workflow, alongside source context,
tempo checks and human listening. The first collection planner currently selects
from metadata only; whole-library AI selection is not yet implemented.

The brief used so far is hypnotic, groovy tribal techno with rap vocals. The trial
used 140 BPM as a working tempo. Kept sounds felt groovy, tribal and funky; rejected
sounds had unsuitable tempo or a poorer musical fit.

## Working software

| Available | Current scope |
|---|---|
| Library, export and Ableton packages | Search, listening, approved-copy export and read-only saved-Set reports. |
| Experimental Live package | Loopback inspection, versioned snapshots, profile checks, explicit device staging and identity-bound allowlisted edit plans with receipts. |
| Portable library state | Identity, onboarding, history capture, guarded writes, backup and recovery. |
| [Collection planner](docs/COLLECTION-PLANNER.md) | Saved metadata selections, explicit export history, repeat handling, retained pins and visible shortages. Regeneration works offline. |
| [Development tools](docs/DEVELOPMENT.md) | Environment discovery, tests against the checkout, installed-command checks and a repeatable synthetic scale benchmark. |
| [Documentation](docs/README.md) | Functionality-first READMEs, a real interface example, contribution guidance and detailed package/state architecture. |

The planner is experimental. It now connects to lazy 12-sample browser batches
whose Keep/Skip decisions persist by sample identity. It does not interpret the
musical brief, enforce tempo or sound-family variety, or calculate device storage
budgets. Pins and browser Keep retain candidates; neither approves them for export.
Live attachment is optional and experimental.
The [roadmap](docs/ROADMAP.md) distinguishes established features from planned work.

## Trial and verification

The counts and device outcomes below are dated trial evidence, not live library state or the
next task for every collection. Current machine/library UUID, selected release, transfer reports
and unreported hardware checks belong in that run's hand-off. A newer authorised collection may
supersede the trial without changing its historical results. Keep private operational records
outside this public repository.

- The September 9 inventory recorded 23,927 source locations and 21,689 distinct
  file identities. Promotion later added 19 curated copies, not new identities.
- The user reviewed 24 candidates, kept 19 and explicitly approved those 19 as
  favourites: 11 rhythm loops, two vocal loops and six vocal phrases/chops.
- Promotion hashes and all 19 Octatrack WAV exports passed software checks.
  Five repeat the September 7 collection. Transfer and hardware playback of this
  new export remain pending. Full evidence is in the
  [set-generation trial](docs/SET-GENERATION-TRIAL.md).
- A metadata plan selecting 1,000 candidates from the real index took about two
  seconds; its database was unchanged. The separate repeatable benchmark uses
  22,000 synthetic identities and verifies exclusion, pins and offline regeneration.
  Neither measurement establishes musical quality or whole-library AI throughput.
- Verification for `39a4204`: **837 tests passed, two model-download checks skipped**;
  installed-wheel checks and the default scale benchmark passed. The
  [macOS and Linux CI run](https://github.com/you1anna/eidetic-sample-tools/actions/runs/34459559476)
  passed. Earlier real-model installation checks are recorded in [AI setup](docs/AI-SETUP.md).
- The September 10 documentation refresh passed local link/anchor and shell-syntax
  checks. The README inspection command was verified against four synthetic files
  without changing audio or creating state; its folder scope is now explicit.
  The README layout and three package diagrams were rendered and inspected.
  This refresh changes documentation and its image only, not application behaviour.
- The new Live transport, snapshot and edit-plan behavior has focused synthetic
  coverage. Installed-wheel checks now exercise a dependency-light three-package
  core first, then all four packages with optional browser/Live integration.
  Final implementation verification: **891 tests passed, two model-download checks
  skipped**; core-first and optional installed-wheel checks passed. A synthetic
  browser trial verified 12+2 batches and Keep/Skip persistence after server restart.
  A running Set in the target Live version, the staged Max device and physical studio routing have
  not yet been used to qualify these claims.

- September 16 maintenance clarified installed-command selection, dated trial state and the
  distinction between staged receipts, card copy and device import. The exporter and collection-plan
  regression suites passed **99 tests**. No runtime code, hardware profiles or safety defaults changed.

## Next bounded increments

1. Qualify collection-plan listening with a representative large plan: saved
   decisions, visible repeat information, lazy previews and interruption recovery.
2. Prepare resumable local-AI retrieval and combine it with tempo and variety
   controls. Report analysed, cached, failed and unanalysed coverage; measure useful
   new sounds per listening minute with the user.
3. Add aggregate device budgets, free-space checks and reliable larger transfers.
   Validate transfer, playback and saved recall for the currently selected collection on each
   device. The older 19-file trial is historical evidence, not a mandatory replacement for a
   newer authorised run.
4. Complete the target Live runtime gate: build/load the staged device, inspect a
   saved test Set, exercise acknowledgement-loss reconciliation, audition through
   the two managed tracks, and verify audible routing plus save/reload.

The [collection assessment](docs/COLLECTION-PLANNING-ASSESSMENT.md) records the
remaining performance and workflow risks. It is a staged design, not a claim
that those capabilities are already present.

## Choices to record for each collection

- Whether a fresh collection should exclude known exports, retain a favourite
  core, or allow a controlled number of repeats. Retain an already agreed policy in the run.
- Whether the larger collection is mainly a browsing library or a cohesive
  performance set, and its desired size, tempo range and role balance.
- Each device's actual available storage and the amount to reserve. Card space,
  project memory and internal import limits are different constraints.

Historical approvals remain evidence; do not request the same approval again merely because a
new task began. A fresh database does not automatically contain those decisions: preserve supplied
history and record its coverage separately from the current promotion state. The trial did not
measure listening time.

## Live-library state

This section preserves the **September 9 historical snapshot**. It is not a current database
inspection and must not trigger re-onboarding, a rescan or replaying an old export. Inspect the
attached library with `sample-library doctor --root ... --json`, and read its current run record.
A fresh library identity may have incomplete older-history coverage while new work remains usable.

At that checkpoint the SSD was onboarded, available selection history was preserved and another
machine's older history was deferred. Later reconciliation must preserve current decisions rather
than replacing them with that historical snapshot.

No source-audio backup was verified in that retained evidence. A device-card backup or an export
receipt does not fill that gap. Continue to require the appropriate verified backup before
source-moving organisation, intake, deduplication or catalogue migration; do not infer that a later
card transfer established one. The recorded permission for hash-verified promotion copies remains
separate. Profiles and safety defaults have not changed.

The July inventory's absent protected-pack entries and missing Foundation identity
remain unresolved historical integrity findings. They are not a reason to repeat
old work or infer missing files' causes. Preserve the evidence and enforce the
per-file checks. See [library history](docs/LIBRARY-HISTORY.md) for the dated records,
including earlier tests and superseded priorities.

[Workflow](docs/WORKFLOWS.md) · [Safety](docs/SAFETY.md) · [Documentation](docs/README.md)
