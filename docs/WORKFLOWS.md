# Workflows

Move from a searchable archive to a collection you have heard, selected and
prepared for an instrument. Each stage produces a reviewable output.

Complete [setup](GETTING-STARTED.md) on the current Mac first. Set the attached
library path and a portable location for this guide's outputs:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

The default index is `$SAMPLES_ROOT/.eidetic/library.sqlite`. Use the same
`--library-db` path throughout if you choose a different index. Recompute `RUNS`
when the library mount path changes. No other Mac needs to be available.

## Library zones

| Zone | Purpose |
|---|---|
| `PACKS/` | Intact source packs and native sample Sets. |
| `CATALOGUE/` | Broad material organised for discovery. |
| `CURATED/` | Auditioned favourites copied into a working collection. |
| `_EXPORT/` | Rebuildable, device-specific conversions. |

Search and analysis work before any reorganisation. Keep source audio, labels,
run manifests and undo records backed up; see the [safety model](SAFETY.md).
For the existing reference library, consult the dated
[operational record](../STATUS.md#live-library-state) before applying changes.

## Find a sound now

Onboard the current Mac using the [lifecycle guide](LIFECYCLE.md) before building
the index. This preserves available older history and can record another Mac's
history as pending. State, labels and recovery records travel with the SSD under
`.eidetic/`.

Build the index once, then write a shortlist to a playlist:

```bash
sample-tag --root "$SAMPLES_ROOT" --rescan --apply
sample-find --root "$SAMPLES_ROOT" perc tribal analog --limit 20 \
  --m3u8 "$RUNS/percussion.m3u8"
```

These commands write derived data and leave audio in place. Terms combine with
AND; `--any` broadens the query. Default ranking spreads results across sound
families to reduce repeated variants.

For a measured comparison, replace `YOUR_SAMPLE_ID` with an indexed ID or a
unique path fragment:

```bash
sample-find --root "$SAMPLES_ROOT" --like YOUR_SAMPLE_ID --role PERC --limit 10
```

See the [search reference](../library-tools/REFERENCE.md#sample-find) for vocabulary,
filters and recording kit selections.

## Save a candidate selection

Use the [collection planner](COLLECTION-PLANNER.md) to choose a candidate count,
control known repeats and retain choices while trying a new seed. It writes a
saved plan and a readable summary from existing metadata. The brief is recorded
context at this stage; it does not rank the audio.

Saved plans are not yet connected to browser listening or export crates. Use the
existing [audition workflow](GROOVE-AUDITION-PILOT.md) for explicit source candidates,
then the approval and export steps below. Never treat a planner pin as a favourite.

## 1. Inspect without changing audio

**Action level:** Read-only summary; optional derived files.

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe --summary
sample-review --root "$SAMPLES_ROOT" --no-probe \
  --output "$RUNS/review.tsv" --index-dir "$RUNS/index"
```

Review proposed roles, sample types, naming warnings and uncertain rows. Add
acoustic analysis when you need detailed measurements and pilot reports:

```bash
sample-analyze --root "$SAMPLES_ROOT" --pilot \
  --output-dir "$RUNS/sample-intelligence-pilot" \
  --library-db "$SAMPLES_ROOT/.eidetic/library.sqlite"
```

## 2. Organise with a reviewed move plan

**Action level:** Moves audio only after `--apply`.

Choose the operation you need and inspect its preview:

```bash
sample-intake --root "$SAMPLES_ROOT"
sample-sort --root "$SAMPLES_ROOT"
sample-dedupe --root "$SAMPLES_ROOT"
```

Intake gathers vendor packs, sorting proposes role folders, and deduplication
stages extra byte-identical copies. If sorting and deduplicating, complete the
sorting review first so the duplicate plan reflects the intended layout.

Check the backup, destinations and collisions before repeating an operation with
`--apply`. Applied moves do not overwrite files and record successful moves in
an undo manifest. Refresh the plan after any library change.

For the supported legacy layout, catalogue migration has a separate preview:

```bash
sample-curate --root "$SAMPLES_ROOT" migrate-catalogue \
  --ableton-root /path/to/ABLETON_PROJECTS \
  --manifest "$RUNS/catalogue-migration.tsv" \
  --undo "$RUNS/catalogue-migration-undo.tsv"
```

It requires a complete inventory and checks saved Sets for `CURATED` references.
Review the manifest and preflight before adding `--apply`; inspect affected
Ableton projects after migration. Rescan the index after applied organisation
and before preparing a new listening packet.

## 3. Curate by ear

**Action level:** Writes review files, then copies approved audio.

Set collection targets in `$RUNS/kit-quotas.toml`:

```toml
[quotas]
KICK = 1
PERC = 2
```

Prepare a fresh, named audition packet for those roles:

```bash
sample-curate --root "$SAMPLES_ROOT" prepare \
  --output-dir "$RUNS/session-01" --quotas "$RUNS/kit-quotas.toml"
```

Listen through `audition.m3u8` and fill in `labels.tsv`. Every row needs a
`reject`, `keep` or `favourite` decision. A favourite also needs a canonical
`true_role` and a short `descriptor`. Preparation selects up to twice each target
for comparison. Keep the packet with its scan metadata and quota file. Choose a
new output directory for each packet; preparation refuses to overwrite an existing
packet. `sample-curate` global options, including `--root`, go before the subcommand.

For local-AI grouping of a prepared packet, follow
[packet classification and review](../library-tools/REFERENCE.md#packet-classification).
The browser resolves classification; musical favourite decisions still belong
in `labels.tsv`. Grouped playlists require completed review and a passing
benchmark before publication.

Validate the complete sheet, then explicitly promote the favourites:

```bash
sample-curate --root "$SAMPLES_ROOT" validate --labels "$RUNS/session-01/labels.tsv"
sample-curate --root "$SAMPLES_ROOT" promote \
  --run-id session-01 --labels "$RUNS/session-01/labels.tsv"
```

Promotion checks the entire selection's sources and destinations before copying
favourites into `CURATED/`. It rechecks each source and updates the search index.
A stale packet or changed source is rejected; an automated suggestion never
counts as approval.

Once approved favourites meet the targets, generate device and Ableton views:

```bash
sample-curate --root "$SAMPLES_ROOT" views --labels "$RUNS/session-01/labels.tsv" \
  --output-dir "$RUNS/crates" --quotas "$RUNS/kit-quotas.toml" --name session-01
```

This writes `session-01-all.tsv`, `session-01-one-shots.tsv` and
`ableton-curated.tsv`. Adjust targets to your intended collection; do not add
unapproved favourites to satisfy them. Omitting `--quotas` uses the original
Foundation targets, and the default crate name remains `foundation-v1`.

## 4. Build device-specific exports

**Action level:** Copies approved audio.

Choose a crate, resolve its contents and preview conversion:

```bash
sample-export digitakt --root "$SAMPLES_ROOT" \
  --crate "$RUNS/crates/session-01-one-shots.tsv" --list
sample-export digitakt --root "$SAMPLES_ROOT" \
  --crate "$RUNS/crates/session-01-one-shots.tsv" --dry-run
```

Check that both previews contain the intended selection. Running the same
command without either preview flag writes converted copies under `_EXPORT/`.
The exporter rechecks hashes, curated paths, roles, names and device limits.

Octatrack and TR-8S exports can be copied to mounted media with `--sync`; Digitakt
uses Elektron Transfer. See the [export reference](../sample-tools/REFERENCE.md)
for formats and transfer scope.

### First-device smoke test

Start with one representative promoted sample in a minimal crate. Run `--list`,
then `--dry-run`, then the export command. Inspect the staged WAV before transfer.
On the instrument, load it, make an audible pattern, save and reload. Record
whether the sample and assignment survive before expanding the crate. Software
validation covers the files; this round trip checks the instrument workflow.

## 5. Recover or revise a decision

**Action level:** Read-only checks; an explicit recovery command moves copies.

Verify a recorded promotion before reuse:

```bash
sample-curate --root "$SAMPLES_ROOT" check --run-id session-01
```

To withdraw that run's curated copies:

```bash
sample-curate --root "$SAMPLES_ROOT" undo-promotion --run-id session-01
```

This moves copies to `_QUARANTINE/promotion-undo/` and removes their locations
from active search. It has no `--apply` flag: running the recovery command is
the approval step. The promotion remains in history as withdrawn. A retry of its
old run cannot recreate it; a new listening decision needs a new promotion run.

If an operation was interrupted, inspect its journal with
`sample-library recover --root "$SAMPLES_ROOT" --json` before starting another
mutation. Follow the [recovery procedure](LIFECYCLE.md#ongoing-work-and-interruption-recovery)
to resume verified work.

Sort, intake, deduplication and migration retain undo manifests, but there is no
generic undo command. Review each recorded destination-to-source mapping before
reversing a move. Undo records are not backups.
