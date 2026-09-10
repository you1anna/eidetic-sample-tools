# Project status

**Updated:** 2026-09-10

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

## Next bounded increments

1. Qualify collection-plan listening with a representative large plan: saved
   decisions, visible repeat information, lazy previews and interruption recovery.
2. Prepare resumable local-AI retrieval and combine it with tempo and variety
   controls. Report analysed, cached, failed and unanalysed coverage; measure useful
   new sounds per listening minute with the user.
3. Add aggregate device budgets, free-space checks and reliable larger transfers.
   Complete the existing 19-file Octatrack hardware round trip before a substantially
   larger transfer; validate other devices separately.
4. Complete the target Live runtime gate: build/load the staged device, inspect a
   saved test Set, exercise acknowledgement-loss reconciliation, audition through
   the two managed tracks, and verify audible routing plus save/reload.

The [collection assessment](docs/COLLECTION-PLANNING-ASSESSMENT.md) records the
remaining performance and workflow risks. It is a staged design, not a claim
that those capabilities are already present.

## Choices still requiring user input

- Whether a fresh collection should exclude known exports, retain a favourite
  core, or allow a controlled number of repeats. No default preference is assumed.
- Whether the larger collection is mainly a browsing library or a cohesive
  performance set, and its desired size, tempo range and role balance.
- Each device's actual available storage and the amount to reserve. Card space,
  project memory and internal import limits are different constraints.

The existing 19 favourites remain approved; further choices do not require asking
for that approval again. Listening time was not supplied and remains unmeasured.

## Live-library state

The SSD was onboarded on September 9. Available September selection history was
preserved; the Mac mini's older database history remains deferred. It can be
reconciled later without replacing current decisions.

No source-library backup has been verified in the retained evidence. The existing
block on `--apply` organisation, intake, deduplication and catalogue migration
therefore remains. Hash-verified promotion copies remain permitted under the
recorded August 4 decision. Profiles and safety defaults have not changed.

The July inventory's absent protected-pack entries and missing Foundation identity
remain unresolved historical integrity findings. They are not a reason to repeat
old work or infer missing files' causes. Preserve the evidence and enforce the
per-file checks. See [library history](docs/LIBRARY-HISTORY.md) for the dated records,
including earlier tests and superseded priorities.

[Workflow](docs/WORKFLOWS.md) · [Safety](docs/SAFETY.md) · [Documentation](docs/README.md)
