# Project status

**Updated:** 2026-07-12

## Current position

Eidetic Sample Tools has a working library-management package, a working device
export package, and a portable studio-profile foundation. The software is ahead
of the live library: the planned SSD catalogue migration and foundation-v1 ear
review have **not been applied**.

The immediate objective remains a small, trusted collection for Octatrack first,
then Digitakt and TR-8S.

## Working software

**Stable**

- Manifest-only library review and TSV indexes.
- Dry-run sorting, pack intake and exact de-duplication.
- Reversible move helpers that do not overwrite destinations.
- Device conversion and staging for Octatrack MKII, Digitakt MKI and TR-8S.

**Beta**

- Portable studio and device profiles.
- SHA-256 sample identity and scan history.
- Ableton-aware catalogue migration planning.
- Human audition packets and hash-verified favourite promotion.
- Profile-aware consumer crates and device validation.

All current automated tests pass. Beta describes operational maturity, not a
known test failure.

## Live-library state

- The Extreme SSD is APFS and backed up, confirmed 2026-07-07.
- No profile-aware catalogue migration has been applied.
- No classifier suggestion has been used to re-file samples.
- The foundation-v1 ear review is in progress; its 216-row label packet remains
  under manual review and is not yet complete.
- No final hardware export has been built from a fully approved foundation-v1
  pool.

The generated database, manifests and research reports are evidence. They are
not proof that a move or musical selection has been approved.

## Beta and research

The acoustic feature layer writes inspectable measurements and shortlist crates.
It cannot decide whether a sound is musically useful.

The optional drum-role classifier is **Experimental** and suggestion-only. Its
first calibration failed: all 10 examples in the proposed
`KICKS → CLAP-SNARE` route were kicks on ear check. That route is rejected and
must not be used for moves, exclusions, curation or export.

The saved full-library audit contains 13,584 rows and 280 high-confidence
drum-role mismatch suggestions. Those numbers describe model output, not measured
accuracy.

Near-duplicate research is also Experimental. Short drum hits proved unreliable,
so the current pilot emits only long, high-certainty loop pairs and still
requires a human removal label.

## Known limits

- Installation still assumes comfort with Python environments and a terminal.
- The current studio is the only end-to-end production environment.
- Human review is intentionally required and can be time-consuming.
- The drum model weights are user-supplied, unlicensed upstream and never
  committed.
- Planned MIDI, Ableton inspection, bounce analysis and stem separation tools do
  not exist as working packages yet.

## Next actions

1. Refresh the stable inventory against the current SSD.
2. Review the catalogue migration manifest and Ableton reference preflight.
3. Apply the migration only after the reviewed plan and backup check agree.
4. Complete the foundation-v1 audition and labels.
5. Promote hash-verified favourites and write consumer views.
6. Preview, build and test the Octatrack export before the other devices.
7. Record real-session outcomes for the exported crate before expanding the
   intelligence layer; see the [Foundation v1 decision corpus](docs/FOUNDATION-V1-DECISION-CORPUS.md).

Follow the canonical [workflow](docs/WORKFLOWS.md) and
[safety model](docs/SAFETY.md) rather than reconstructing commands from research
notes.

## Evidence and decisions

- [Classifier adopted for evaluation](decisions/2026-07-09-drum-role-classifier-adopted.md)
- [Classifier downgraded after calibration](decisions/2026-07-09-drum-role-classifier-downgraded.md)
- [High-precision kicks gate assessment](decisions/2026-07-08-high-precision-kicks-gate-assessment.md)
- [Near-duplicate pilot design](docs/superpowers/specs/2026-07-08-near-dupe-pilot-design.md)
- [Sample intelligence audit](docs/superpowers/specs/2026-07-07-sample-intelligence-audit.md)
- [Product roadmap](docs/ROADMAP.md)
