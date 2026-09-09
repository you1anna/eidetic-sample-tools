# Roadmap

The next milestone is a repeatable path from a fresh library to a tested hardware
crate. Priorities are simpler setup, clearer configuration and evidence that the
workflow transfers across libraries.

## Capability status

| Maturity | Available today |
|---|---|
| **Stable** | Library review, preview-based sorting, pack intake, exact deduplication, WAV conversion and read-only Ableton inspection. |
| **Beta** | Content-hash inventory, origin recovery, tag and acoustic search, curation, promotion checks, profiles and selected-crate sync. |
| **Experimental** | Explicit-candidate audition and shortlist UI, vocal-cut audition, CLAP grouping, drum-role benchmarks and conservative near-duplicate detection. |
| **Planned** | Preference-informed retrieval, cohesive set assembly, MIDI generation, bounce analysis and stem separation. |

Stable capabilities have tests and operational use. Beta features are implemented
but still being refined; experimental outputs require evaluation by ear. These
labels are not compatibility or support guarantees.

## Adoption priorities

1. **Portable setup.** Establish a consistent installation and upgrade path;
   replace remaining machine-specific defaults with explicit configuration.
2. **A shorter first session.** Join indexing, search, audition and export with
   clearer progress and actionable preflight reports.
3. **Hardware validation.** Verify minimal crates through transfer, playback,
   assignment and save/reload on each supported device.
4. **Broader library coverage.** Test different pack structures, naming schemes
   and formats; evaluate broader tag vocabularies and listening briefs.
5. **Clear recovery.** Improve the path from manifests and integrity reports to
   a reviewed recovery action, retaining preview and undo guarantees.

## Research with measurable outcomes

Evaluate classification against ear-labelled examples and near-duplicate
candidates through listening. Model confidence alone does not authorise musical
or file-management decisions. The earlier CNN-LSTM drum-role route failed
calibration and remains review-only.

The [sample audition pilot](GROOVE-AUDITION-PILOT.md) now connects explicit
candidates to a saved shortlist and the existing curation workflow. Its Keep/Skip
choices do not influence retrieval, and no improvement in generated suggestions
has been demonstrated. The next proposed evaluation is to capture the listening
brief with decisions, reserve unseen examples for judging, and compare existing
retrieval with a lightweight preference reranker using cached features or
embeddings where appropriate. Keep this work only if it finds more useful samples
with less auditioning. Reset decisions are not negative labels, and a skip in one
brief must not become a universal rejection.

[Decision records](../decisions/), [specifications](superpowers/specs/) and
[plans](superpowers/plans/) retain that evidence. The dated
[operational status](../STATUS.md) tracks the reference library's recovery and
hardware trials separately from this product roadmap.

Licensing, distribution and release dates remain undecided.
