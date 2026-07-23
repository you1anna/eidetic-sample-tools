# Workflows

Eidetic Sample Tools separates inspection, organisation, curation and export.
Each stage leaves evidence for the next one. No classifier or heuristic gets to
approve a musical decision.

Read the [safety model](SAFETY.md) before using an apply step.

## The operating model

The intended sequence is:

1. Inspect the library and write review material.
2. Plan any structural change and examine its manifest.
3. Listen and mark a small set of trusted sounds.
4. Export approved copies to a device-specific format.
5. Use undo records or quarantine when a decision needs revising.

The tools are useful independently, but this sequence keeps broad library
organisation separate from musical selection.

## Current recovery position

Three working packages support this sequence: library management, device export
and read-only Ableton `.als` inspection. The Ableton tools can index Sets and
report sample references, but never edit a Set.

A local post-run audit dated 2026-07-18 verified 18 authorised catalogue moves.
The 2026-07-23 read-only reconciliation scanned 22,952 audio files and verified
that all 18 audited destination paths match their recorded SHA-256 identities;
all 18 former source paths are absent. The associated confidence-organisation
code is not merged. Treat this as historical organisation evidence only: it does
not establish a complete catalogue, curated audio, verified PACKS preservation
or an exportable crate, and confidence does not permit any additional move.

The reconciliation found 130 absent entries from a 7,689-entry protected
`PACKS/` snapshot; none were found relocated or changed in place. It also found
one canonical Foundation v1 sample identity absent from inventory. These are
blocking integrity discrepancies. Preserve the read-only evidence and conduct a
human recovery review before promotion, export or a new organisation plan; do
not infer their cause or mutate audio while resolving them.

Foundation v1 is still human-gated. Its canonical `labels.tsv` has 216 rows;
215 current rows resolve to decisions in the 214-row `labels-categorised.tsv`
reference because one sample identity is duplicated, and one canonical identity
is absent from inventory. The reference has 169 `keep` and 45 `reject` decisions
but no favourites, so it cannot drive promotion. The 2026-07-18 audit found no
curated audio. Recover the sequence by resolving the integrity discrepancies
through human review, reviewing any future move plan in preview, completing and
validating the canonical listening sheet, and only then promoting hash-verified
favourites and previewing an export.

## Library zones

| Zone | Purpose |
|---|---|
| `PACKS/` | Intact source packs and native Octatrack Sets. |
| `CATALOGUE/` | Broad material organised by role. It may be useful, but it has not all been approved by ear. |
| `CURATED/` | A small working collection that has been auditioned and approved. |

Generated indexes, review packets and export folders sit outside these source
zones. They can be rebuilt from the library and its decision records.

## 1. Inspect without changing audio

**Action level:** Writes derived files.

Start with a read-only summary:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

Write a main TSV and focused indexes when you are ready to inspect rows:

```bash
sample-review \
  --root /path/to/SAMPLES \
  --no-probe \
  --output manifests/review.tsv \
  --index-dir manifests/index
```

For a stable content identity and acoustic evidence, run the analysis layer:

```bash
sample-analyze \
  --root /path/to/SAMPLES \
  --pilot \
  --library-db manifests/sample-library.sqlite
```

This can decode audio and write TSV, SQLite and report files. It does not change
source audio. Content is identified by SHA-256 so review history can survive a
move or exact copy.

## 2. Organise with a reviewed move plan

**Action level:** Moves audio after `--apply`.

Organisation commands preview by default:

```bash
sample-intake --root /path/to/SAMPLES
sample-sort --root /path/to/SAMPLES
sample-dedupe --root /path/to/SAMPLES
```

Read the plan, check destination collisions and confirm the library backup before
running the same command with `--apply`. Applied moves do not overwrite existing
files and write undo records for files that actually moved.

Confidence is a way to prioritise a reviewed plan, not permission to move audio.
The unmerged confidence-organisation work and its 18-move audit do not change
this gate. The reconciliation's PACKS and canonical-label discrepancies block a
fresh plan until human recovery review resolves them.

The profile-aware foundation can plan a legacy-role migration into the
[library zones](#library-zones):

```bash
sample-curate \
  --root /path/to/SAMPLES \
  --library-db manifests/sample-library.sqlite \
  migrate-catalogue \
  --ableton-root /path/to/ABLETON_PROJECTS \
  --manifest manifests/catalogue-migration.tsv \
  --undo manifests/catalogue-migration-undo.tsv
```

The command checks Ableton references before proposing moves. Review the
manifest and add `--apply` only when the preflight and destinations are correct.

## 3. Curate by ear

**Action level:** Copies approved audio.

Prepare an audition packet from the current stable inventory:

```bash
sample-curate \
  --root /path/to/SAMPLES \
  --library-db manifests/sample-library.sqlite \
  prepare \
  --output-dir manifests/foundation-v1-review
```

Listen through `audition.m3u8`. Mark every `labels.tsv` row as `reject`, `keep`
or `favourite`. A favourite also needs its true role and a short descriptor.

Validate the complete label file before promotion:

```bash
sample-curate validate \
  --labels manifests/foundation-v1-review/labels.tsv
```

Promotion verifies the content hash, then copies approved favourites into
`CURATED/`. It does not move the catalogue source:

```bash
sample-curate \
  --root /path/to/SAMPLES \
  --library-db manifests/sample-library.sqlite \
  promote \
  --run-id foundation-v1 \
  --labels manifests/foundation-v1-review/labels.tsv
```

Write consumer views after promotion:

```bash
sample-curate \
  --library-db manifests/sample-library.sqlite \
  views \
  --output-dir manifests/foundation-v1 \
  --labels manifests/foundation-v1-review/labels.tsv
```

## 4. Build device-specific exports

**Action level:** Copies approved audio.

Always resolve and inspect a crate first:

```bash
sample-export digitakt \
  --profile eidetic-studio \
  --crate manifests/foundation-v1/foundation-v1-one-shots.tsv \
  --list
```

Then preview conversion:

```bash
sample-export digitakt \
  --profile eidetic-studio \
  --crate manifests/foundation-v1/foundation-v1-one-shots.tsv \
  --dry-run
```

Running without `--list` or `--dry-run` writes converted copies below the export
root. Octatrack and TR-8S folders can then be copied to mounted media with
`--sync`. Digitakt uses Elektron Transfer.

The exporter checks hashes, device capacity, role compatibility, path depth and
compact names before conversion. See the [export reference](../sample-tools/README.md)
for exact formats.

## 5. Recover or revise a decision

**Action level:** Moves derived audio after an explicit recovery command.

Applied sort, intake, de-duplication and catalogue changes write undo manifests.
Those files record the exact destination-to-source mapping for items that moved;
retain them with the run evidence. The current toolkit does not expose one
generic undo command, so review the record before reversing a move.

Curated promotion has a dedicated recovery command:

```bash
sample-curate \
  --root /path/to/SAMPLES \
  --library-db manifests/sample-library.sqlite \
  undo-promotion \
  --run-id foundation-v1
```

It moves promoted copies to `_QUARANTINE/promotion-undo/`. It does not delete
them. Unlike the organisation commands, this recovery command has no separate
`--apply` flag: running it is the approval step. Device exports are derived
copies and can be removed and rebuilt after checking that the source library is
intact.

## Personal studio workflow

The current Eidetic studio uses the `eidetic-studio` profile with Octatrack MKII,
Digitakt MKI and TR-8S. The supported creative loop is hardware jam → Ableton,
resample in Octatrack, then arrange and finish in Ableton.

The current library lives at `/Volumes/Extreme SSD/Production/SAMPLES/`. Add only
`SAMPLES/CURATED/` to Ableton Places, and use the generated
`ableton-curated.tsv` as the tag and saved-search reference. The external Studio
Knowledge Base remains authoritative for physical wiring; tool profiles describe
only capabilities the software can act on.
