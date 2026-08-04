# Project status

**Updated:** 2026-08-04

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
absent. It also found integrity discrepancies that remain unexplained; as of
2026-08-04 they are an open risk rather than a promotion block (see "Live-library
state" below).

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

- **The Extreme SSD has no current backup.** The earlier "backed up, confirmed 2026-07-07"
  claim was checked on 2026-07-31 and does not hold: `tmutil destinationinfo` reports no
  destinations configured on the Mac mini. 28 GB across 22,952 audio files is single-copy,
  including material that cannot be re-downloaded. **No `--apply` organisation, intake,
  dedupe or catalogue-migration command may run until this is resolved.**
- **Promotion is permitted again as of 2026-08-04** (Robin's decision; recorded in
  `eidetic-studio/decisions/2026-08-04-demote-packs-recovery-gate.md`). `sample-curate
  promote` is a hash-verified **copy** — it re-resolves every labelled row against the
  inventory, re-computes its SHA-256 and refuses a stale or missing source before copying,
  so it carries the per-file guarantee the blanket block was standing in for.
  `undo-promotion --run-id <id>` moves copies to `_QUARANTINE/promotion-undo/`.
  **This is not a backup:** promotion writes a second copy on the same physical disk, and a
  drive failure still loses both. Robin declined a backup on 2026-08-04 with this stated.
  Hardware export and card sync remain untested against the live library.
- A 2026-07-18 local audit verified 18 authorised catalogue moves. Reconcile
  those recorded moves with the 2026-07-23 read-only inventory before planning
  further organisation. All 18 audited destinations match their recorded
  SHA-256 identities, and all 18 former source paths are absent.
- The inventory contains 22,952 audio files. Of 7,689 protected `PACKS/`
  snapshot entries, 130 are absent from the current inventory and were not
  found relocated or changed in place. PACKS preservation is therefore not
  fully verified; do not infer why those entries are absent. **As of 2026-08-04 this is an
  open integrity risk rather than a block** — it stays unexplained and may never be
  explained, and no preservation claim about `PACKS/` should be treated as verified.
  Demonstrated in practice on 2026-08-04: the `tribal-140-01` packet contained one such row
  (`04b454c5…`, the known Foundation recovery blocker in
  `foundation-v1-recovery-20260723/unresolved.tsv`); it was caught by the per-file check and
  removed, leaving the other 63 rows unaffected.
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

## Retrieval layer (added 2026-07-31)

`sample-tag` and `sample-find` make the library searchable by style, type and origin without
moving a file. Verified against the live library, which was byte-identical before and after
(22,952 audio files, 27,672 files total, 28 GB):

- Pack origin recovered for 20,300 of 21,306 distinct samples (95.3%) across 44 packs.
  10,067 came from a surviving folder, 10,231 from the filename token the sorter left behind.
- 21,304 acoustic measurements moved from the stale path-keyed cache onto `sample_id`, with
  no re-decoding required; 2 failed and are recorded.
- 83,606 tags written from `vocabulary.toml` — the `tags` table had been empty since it was
  created.
- `sample-find --crate` output was accepted by `sample-export octatrack --list`, which
  re-verified every SHA-256 against the bytes on disk.

**Gap closed 2026-08-01:** that verification ran against a `CURATED/`-located sample, but
`build_crate_plan` had no check that a crate row's source lived there at all — a matching
hash from anywhere in the library, including unreviewed `CATALOGUE/` or `PACKS/` material,
would pass. That let `sample-find --crate` build a crate `sample-export` would convert
without the ear-review `sample-curate promote` step in between, contradicting this repo's own
promote-then-export invariant (`docs/WORKFLOWS.md` §3–4) and `eidetic-studio`'s WIP export-set
contract. `build_crate_plan` now rejects any row outside `CURATED/`; `sample-find --curated-only`
lets a search be scoped to what will actually pass before a crate is written.

This also bears on the 130 absent protected `PACKS/` entries. The evidence points to earlier
flattening rather than loss: 935 orphaned `.wav.asd` sidecars sit in `PACKS/` where audio was
moved out, and the pack that `unresolved.tsv` records as missing
(`gr8-tech-house-top-loops`) still has 50 samples present in the index under recovered
origin. That is not a completed recovery review, but it narrows what remains to be explained.
**Corroborated 2026-08-04:** the `tribal-140-01` packet drew one row from exactly that pack
(`PACKS/gr8-tech-house-top-loops/125bpm_Wav_Loops/Top Loop 2.wav`) — the whole
`125bpm_Wav_Loops/` sub-folder is gone while the rest of the pack is indexed, which fits the
flattening explanation rather than wholesale loss. It is still not proof, and no cause should
be inferred. Promotion was unblocked separately on the strength of the per-file hash check,
not on this evidence.

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
