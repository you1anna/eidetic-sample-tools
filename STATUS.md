# Project status

**Updated:** 2026-07-23

## Current position

Eidetic Sample Tools has three working packages: library management, device
export, and read-only Ableton Live Set introspection. The Ableton package can
index `.als` Sets and report their sample references; it never edits a Set.

The software and the live-library record still need reconciliation. A local
post-run audit dated 2026-07-18 verified 18 authorised catalogue moves. The
confidence-organisation code associated with that work remains on an unmerged
branch. That audit is limited organisation evidence: it is neither proof of a
complete catalogue migration nor permission for further moves. The 2026-07-23
read-only reconciliation scanned 22,952 audio files: all 18 audited destination
paths match their recorded SHA-256 identities and all 18 former source paths are
absent. It also found integrity discrepancies that require human recovery review
before curation promotion or hardware export.

The immediate objective remains a small, trusted collection for Octatrack first,
then Digitakt and TR-8S.

## Working software

**Stable**

- Manifest-only library review and TSV indexes.
- Dry-run sorting, pack intake and exact de-duplication.
- Reversible move helpers that do not overwrite destinations.
- Device conversion and staging for Octatrack MKII, Digitakt MKI and TR-8S.
- Read-only Ableton `.als` Set indexing and sample-reference reports.

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
- A 2026-07-18 local audit verified 18 authorised catalogue moves. Reconcile
  those recorded moves with the 2026-07-23 read-only inventory before planning
  further organisation. All 18 audited destinations match their recorded
  SHA-256 identities, and all 18 former source paths are absent.
- The inventory contains 22,952 audio files. Of 7,689 protected `PACKS/`
  snapshot entries, 130 are absent from the current inventory and were not
  found relocated or changed in place. PACKS preservation is therefore not
  fully verified; do not infer why those entries are absent.
- The confidence-organisation implementation used for that audit is unmerged.
  Its confidence output remains review evidence, never permission to move,
  exclude, promote or export audio.
- The canonical Foundation v1 `labels.tsv` has 216 rows. Of those, 215 current
  rows resolve to decisions represented in the 214-row
  `labels-categorised.tsv` reference because one sample identity is duplicated;
  one canonical sample identity is absent from the current inventory. The
  reference records 169 `keep` and 45 `reject` decisions, with no `favourite`
  rows. It is not a completed canonical label sheet and cannot promote audio.
- The 2026-07-18 audit found no curated audio. No final hardware export has
  been built from a fully approved Foundation v1 pool.

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
- Planned MIDI, bounce analysis and stem separation tools do not exist as
  working packages yet.

## Next actions

1. Conduct a human recovery review of the 130 absent protected `PACKS/` entries
   and the one canonical Foundation v1 sample identity absent from inventory.
   Preserve the 2026-07-23 inventory and do not infer cause or mutate audio
   while resolving the discrepancy.
2. Retain the reconciliation evidence: the 22,952-file inventory confirms all
   18 audited destination hashes and absent former source paths. Use the audit,
   manifests and undo records to review any recovery plan.
3. Block promotion and hardware export until the integrity discrepancies are
   resolved through human recovery review.
4. Review, test and deliberately decide whether the unmerged
   confidence-organisation code belongs in the main workflow. If it is used,
   generate and inspect a fresh preview; only an explicit `--apply` against a
   backed-up library may move audio.
5. Prepare or restore the canonical Foundation v1 audition packet, then listen
   and complete every canonical `labels.tsv` row. The 214-row reference file is
   useful context, not a substitute for the human gate.
6. Validate labels, promote only hash-verified favourites and write consumer
   views. No favourites means no curated promotion.
7. Resolve and preview the Octatrack crate with `--list` and `--dry-run`, then
   build and test it before the other devices.
8. Record real-session outcomes for the exported crate before expanding the
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
