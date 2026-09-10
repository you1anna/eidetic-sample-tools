# Library tools

Find samples by musical tags or acoustic similarity, audition a shortlist, and
copy your favourites into a collection ready for export.

[Setup](../docs/GETTING-STARTED.md) · [Workflow](../docs/WORKFLOWS.md) ·
[Command reference](REFERENCE.md)

## What it does

| Task | Commands |
|---|---|
| Inspect sample names, roles, BPM/key evidence and warnings | [`sample-review`](REFERENCE.md#sample-review) |
| Search tags, pack origins and similar sounds; write playlists | [`sample-tag`](REFERENCE.md#sample-tag), [`sample-find`](REFERENCE.md#sample-find) |
| Save a selection, control repeats and retain chosen sounds | [Collection planner](../docs/COLLECTION-PLANNER.md) |
| Preview sorting, exact deduplication and pack intake | [`sample-sort`, `sample-dedupe`, `sample-intake`](REFERENCE.md#sample-sort-sample-dedupe-sample-intake) |
| Audition explicit candidates in a browser and save a shortlist | [`sample-vibe`](REFERENCE.md#sample-vibe) |
| Record listening decisions, promote favourites and check copies | [`sample-curate`](REFERENCE.md#sample-curate) |
| Suggest listening groups with local AI | [Packet classification](REFERENCE.md#packet-classification) |
| Measure audio and evaluate similar loops or model suggestions | [Analysis and experiments](REFERENCE.md#analysis-and-experiments) |
| Onboard a library, back up its state and recover interrupted work | [`sample-library`](REFERENCE.md#long-lived-and-shared-drive-installations) |
| Inspect resolved device capabilities | [`sample-profile`](REFERENCE.md#sample-profile) |

Core organisation is stable; search and curation are beta. Collection planning,
browser audition, AI classification and near-duplicate detection are experimental.
See the [reference](REFERENCE.md#command-map) for command maturity.

## Try it

Follow [environment setup](../docs/GETTING-STARTED.md#install), then install from
the repository root in the activated Python 3.12 environment:

```bash
python -m pip install -e ./library-tools
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

Inspect a folder without writing files:

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe --summary
```

For search, [onboard the library](../docs/GETTING-STARTED.md#search-and-listen)
first, then build its index and write an audition playlist:

```bash
sample-tag --root "$SAMPLES_ROOT" --rescan --apply
sample-find --root "$SAMPLES_ROOT" perc tribal analog --limit 20 \
  --m3u8 "$RUNS/percussion.m3u8"
```

Tagging writes measurements and generated tags to the index; audio stays in place.
Search terms combine with AND. Use `--any` to broaden a query, or
`--like SAMPLE_ID` to rank by acoustic similarity without AI models.

Next, [audition explicit candidates in the browser](REFERENCE.md#sample-vibe) or
[prepare a listening packet and promote favourites](../docs/WORKFLOWS.md#3-curate-by-ear).
Approved collections pass to [sample-tools](../sample-tools/README.md) for export.

## Before changing a library

- Organisation previews moves; `--apply` executes them and records undo mappings.
  Exact duplicates are staged, never deleted.
- Promotion copies favourites after complete listening labels and hash checks.
  `undo-promotion` moves curated copies to quarantine immediately, without `--apply`.
- Back up source audio and retain labels, manifests and undo records together.
  Follow the [safety model](../docs/SAFETY.md) and [lifecycle guide](../docs/LIFECYCLE.md).

[Full command reference](REFERENCE.md) · [Local AI setup](../docs/AI-SETUP.md)
