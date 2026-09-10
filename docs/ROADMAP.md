# Roadmap

The next milestone is a larger, varied collection that fits a musical brief and
its target device. Build it in bounded increments: saved choices, manageable
listening, prepared local-AI retrieval, then device budgets and larger transfers.

The first metadata planner and reusable verification tools are implemented.
See [project status](../STATUS.md) for the current checkpoint and unanswered choices.

## Capability status

| Maturity | Available today |
|---|---|
| **Stable** | Library review, preview-based sorting, pack intake, exact deduplication, WAV conversion and read-only Ableton inspection. |
| **Beta** | Content-hash inventory, origin recovery, tag and acoustic search, curation, promotion checks, profiles and selected-crate sync. |
| **Experimental** | Saved collection plans with repeat controls and pins; plan-to-browser batches; optional guarded running-Set inspection/editing; explicit-candidate and vocal-cut audition; CLAP grouping, drum-role benchmarks and conservative near-duplicate detection. |
| **Planned** | Preference-informed retrieval, cohesive set assembly, MIDI generation, bounce analysis and stem separation. |

Stable capabilities have tests and operational use. Beta features are implemented
but still being refined; experimental outputs require evaluation by ear. These
labels are not compatibility or support guarantees.

## Current priorities

1. **Qualify the manageable listening queue.** Frozen plans now open in lazy
   12-sample browser batches with durable identity-based decisions. Verify the
   workflow against a representative large plan and measure listening progress.
2. **Local AI within brief selection.** Prepare reusable audio representations with
   resumable processing and explicit coverage. Combine model relevance with source
   context, tempo suitability and variety; measure useful new sounds per listening minute.
3. **Budgets for each device.** Distinguish browsing storage, project limits and
   internal imports. Account for existing usage and temporary conversion space.
4. **Larger exports with recovery.** Preserve output paths and transfer evidence;
   support interruption without repeatedly rebuilding or copying completed work.
5. **Hardware validation.** Complete the approved 19-file Octatrack trial before a
   substantially larger transfer, then verify each additional device separately.
6. **Live qualification.** Build and load the staged Max for Live device, verify
   loopback inspection and acknowledgement loss handling in the target Live version, then test
   managed audition tracks, routing, audible playback, Set save/reload and cleanup.

Portable setup, explicit library selection and installed-package checks are
already available. Broader library coverage and historical-state reconciliation
remain ongoing work. The [collection assessment](COLLECTION-PLANNING-ASSESSMENT.md)
contains the detailed performance risks and acceptance checks.

## Research with measurable outcomes

Evaluate classification against ear-labelled examples and near-duplicate
candidates through listening. Model confidence alone does not authorise musical
or file-management decisions. The earlier CNN-LSTM drum-role route failed
calibration and remains review-only.

The [sample audition pilot](GROOVE-AUDITION-PILOT.md) now connects explicit
candidates to a saved shortlist and the existing curation workflow. Its Keep/Skip
choices do not influence retrieval, and no improvement in generated suggestions
has been demonstrated. The [first brief trial](SET-GENERATION-TRIAL.md) kept 19 of
24 candidates, comparing contextual picks with model-ranked picks from a narrowed
pool. It did not measure listening time or whole-library AI selection. Future
preference ranking needs the brief attached to decisions and unseen examples for
evaluation. Keep it only if it finds more useful samples with less auditioning.
Reset decisions are not negative labels, and a skip in one brief must not become
a universal rejection.

[Decision records](../decisions/), [specifications](superpowers/specs/) and
[plans](superpowers/plans/) retain that evidence. The dated
[operational status](../STATUS.md) tracks the reference library's recovery and
hardware trials separately from this product roadmap.

The Live bridge vendors reviewed MIT-licensed device source at a pinned upstream
revision. Repository-wide licensing, distribution and release dates remain undecided.
