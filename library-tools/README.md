# Library tools

## Purpose

The library package reviews, organises, curates and analyses large sample
libraries. It is the library-management half of **Eidetic Sample Tools**.

The default posture is cautious: review commands leave audio in place, move
commands preview first, and musical decisions remain human decisions.

## Install

Follow the portable [getting started guide](../docs/GETTING-STARTED.md), or use
the current personal environment:

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-sample-tools/library-tools[dev]"
```

The experimental drum classifier is optional and heavy:

```bash
~/.venvs/library-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-sample-tools/library-tools[classifier,dev]"
```

Its upstream weights have no software licence and are not shipped in this
repository. Locally supplied weights belong at
`library-tools/models/drum-cnn-lstm.model` and must remain uncommitted.

## Commands at a glance

| Command | Maturity | Purpose | Audio effect by default |
|---|---|---|---|
| `sample-review` | Stable | Write a filename- and path-based review. | None; optional TSV output only |
| `sample-sort` | Stable | Plan role-based moves from confident review rules. | Dry run |
| `sample-dedupe` | Stable | Find byte-identical copies and stage extras. | Dry run |
| `sample-intake` | Stable | Route loose vendor packs into `PACKS/`. | Dry run |
| `sample-analyze` | Beta / Experimental | Build stable inventory and acoustic evidence; optionally run the drum classifier. | Derived files only |
| `sample-near-dupes` | Experimental | Produce conservative near-duplicate audition groups. | Derived files; reviewed apply is a dry run by default |
| `sample-role-cleanup` | Experimental | Turn classifier routes into human calibration packets. | Derived files only |
| `sample-benchmark` | Experimental | Prepare ear-labelled model benchmarks and score them. | Derived files only |
| `sample-tag` | Beta | Recover pack origin, measure acoustics and regenerate search tags. | Derived files only |
| `sample-find` | Beta | Find samples by style, type and origin; write playlists and crates. | None |
| `sample-profile` | Beta | Show or validate portable studio profiles. | None |
| `sample-curate` | Beta | Plan catalogue migration, curate by ear and write consumer views. | Depends on subcommand |
| `sample-classify` | Retired | Legacy coarse loop/one-shot sorter. | Dry run |

Stable means used in the current personal workflow and covered by tests. Beta is
implemented but still being refined. Experimental output needs extra scrutiny.
Retired commands remain available for old workflows but are not recommended for
new ones.

## Safe starting point

Print a summary without writing files or changing audio:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

Write a review manifest and focused indexes:

```bash
sample-review \
  --root /path/to/SAMPLES \
  --no-probe \
  --output manifests/review.tsv \
  --index-dir manifests/index
```

Use `--no-probe` when filename and path evidence is enough. Omit it when you
want `ffprobe` duration fallback.

## Review and index

### `sample-review`

```text
sample-review [--root PATH] [--output FILE] [--index-dir DIR]
              [--summary] [--no-probe]
```

The main TSV keeps musical axes separate:

| Field | Meaning |
|---|---|
| `main_category` | Proposed role such as kicks, bass or vocals |
| `sample_type` | Loop, one-shot, texture or unknown |
| `bpm` / `key` | Explicit path or filename evidence; never guessed |
| `tempo_fit` | Advisory tempo group, not a deletion decision |
| `proposed_name` | Hardware-friendly filename |
| `warnings` | Review notes such as a Digitakt name over 24 characters |

`--index-dir` writes high-confidence role files, tempo views and
`review-needed.tsv`. BPM parsing deliberately avoids treating instrument names
such as 707, 808, 909, 303 and SH101 as tempos.

## Organise and deduplicate

### `sample-sort`

```text
sample-sort [--root PATH] [--include-review] [--apply]
```

Plans confident moves into flat role folders. `--include-review` also gathers
low-confidence files in `_REVIEW/`. It does not overwrite a destination; name
collisions receive a numeric suffix. `--apply` performs the moves and writes an
undo manifest.

### `sample-dedupe`

```text
sample-dedupe [--root PATH] [--apply]
```

Compares file bytes, not names alone. `--apply` moves extra exact copies to
`_TO-DELETE/dupes/` for later inspection. It never deletes them.

Run sorting before exact de-duplication so the duplicate plan reflects the
intended layout.

### `sample-intake`

```text
sample-intake [--root PATH] [--apply]
```

Finds whole vendor packs at the library root or in `00_INBOX/`, normalises their
folder names and plans moves into `PACKS/`. Loose audio at the root is not
treated as a pack.

### `sample-classify` — retired

```text
sample-classify [--root PATH] [--no-probe] [--apply]
```

This older command sorts `_PACKS/`, `DRUM-KITS/` and `00_INBOX/` into coarse
sound-type buckets. Use `sample-review` and `sample-sort` for new role-based
work. The command remains available when the older loop/one-shot split is useful.

## Find samples and load hardware

### `sample-tag`

```text
sample-tag [--root PATH] [--library-db FILE] [--vocabulary FILE]
           [--rescan] [--skip-features] [--apply]
```

Builds the search index in three read-only steps: recovers each sample's pack origin,
moves acoustic measurements onto the content hash, then regenerates tags from
[`vocabulary.toml`](vocabulary.toml).

Origin survives the earlier flattening because `sample-sort` renamed files to
`{role}-{description}_{source}`, leaving the pack token in the filename. Where a folder still
names the pack it is used directly, and a sample that also exists somewhere with intact
provenance inherits it by content hash. On the current library that resolves 20,300 of 21,306
samples (95.3%) across 44 packs.

A tag is a saved predicate over evidence, not a label applied per file:

```toml
[[tag]]
name = "tribal"
group = "style"
origin_matches = ["tribal"]
name_matches = ["conga", "bongo", "djembe", "cowbell"]
```

Run without `--apply` to write a coverage proposal listing what each rule would match and
why. Edit the vocabulary, re-run, and tags regenerate — you never re-label samples.

### `sample-find`

```text
sample-find [TERMS...] [--role R] [--style S] [--gear G] [--character C] [--origin O]
            [--any] [--curated-only] [--like PATH|ID] [--preferred] [--no-spread]
            [--limit N] [--m3u8 FILE] [--crate FILE] [--kit-id ID]
```

Terms match across every tag group and are ANDed unless `--any` is given.

`--like` ranks by measured acoustic distance instead of keywords. This is what narrows
*within* a pack: 7,826 Goldbaby SA909 samples share every keyword tag they will ever have, so
only sound can separate them. It is plain min-max normalised euclidean distance over the
measured features — no clustering and no model.

Results spread across sound families by default, so "find me a bongo" returns different
bongos rather than eight round-robin takes of one. Use `--no-spread` for a flat alphabetical
list.

`--crate` writes the schema `sample-export` already reads, which makes search-to-hardware two
commands — but `sample-export` rejects any row whose source isn't already promoted into
`CURATED/`, so add `--curated-only` to search only what will actually pass:

```bash
sample-find kick --gear 909 --character subby --curated-only --limit 16 \
  --crate manifests/ot-kit-01.tsv --kit-id ot-kit-01
sample-export octatrack --profile eidetic-studio --crate manifests/ot-kit-01.tsv --list
```

Without `--curated-only`, a written crate may still contain `CATALOGUE/`- or `PACKS/`-sourced
rows; `sample-find` warns at write time, and `sample-export` refuses the whole crate until
those samples are promoted with `sample-curate`.

`--kit-id` records what went into a kit. Those picks accumulate into a preference signal that
`--preferred` sorts by, so the trusted set builds itself out of real use instead of requiring
a labelling session up front.

## Curate trusted samples

### `sample-curate`

Global options must appear before the subcommand:

```text
sample-curate [--root PATH] [--library-db FILE] SUBCOMMAND ...
```

| Subcommand | Required options | Effect |
|---|---|---|
| `migrate-catalogue` | `--ableton-root`, `--manifest`, `--undo` | Writes a migration plan; `--apply` moves after preflight. |
| `prepare` | `--output-dir` | Writes an audition playlist and labels. |
| `validate` | `--labels` | Checks that required human decisions are complete. |
| `promote` | `--labels`, `--run-id` | Hash-checks and copies approved favourites to `CURATED/`. |
| `views` | `--labels`, `--output-dir` | Writes device and Ableton consumer TSVs. |
| `undo-promotion` | `--run-id` | Moves promoted copies to quarantine. |

Use the complete [curation workflow](../docs/WORKFLOWS.md#3-curate-by-ear).
Promotion accepts only a complete label set. Every favourite needs a canonical
role and a short descriptor.

## Analyse and run experiments

### `sample-analyze`

```text
sample-analyze [--root PATH] [--output-dir DIR] [--pilot]
               [--feature-cache FILE] [--no-probe] [--profile NAME]
               [--library-db FILE] [--classifier]
```

`--pilot` writes source registries, acoustic features, reports and suggested
device crates. `--library-db` adds a stable SHA-256 inventory. `--no-probe`
skips duration and acoustic extraction for a faster path-only pass.

`--classifier` runs the optional drum-role model and writes review candidates.
It does not authorise moves, exclusions, curation or hardware crates. The first
high-confidence route tested in the current library failed its ear calibration,
so classifier output remains strictly experimental.

### `sample-near-dupes`

```text
sample-near-dupes [--features FILE] [--output-dir DIR] [--root PATH]
                  [--family TEXT] [--limit-groups N]
                  [--apply-manifest FILE] [--apply]
```

The default pilot emits only long, high-certainty loop pairs. Short-hit acoustic
similarity was not reliable enough. Review the TSV and mark `decision=remove`
before passing it back with `--apply-manifest`; the operation still previews
unless `--apply` is also present.

### `sample-role-cleanup`

```text
sample-role-cleanup prepare --audit FILE --root PATH --output-dir DIR
```

Freezes a classifier audit into deterministic role-to-role audition packets.
Every calibration row must be labelled before a route can advance. A failed
route stays rejected.

### `sample-benchmark`

```text
sample-benchmark prepare --output-dir DIR [--root PATH]
                         [--features FILE] [--per-role N]
                         [--max-duration SECONDS]
sample-benchmark score --output-dir DIR [--root PATH]
                       [--model cnn-lstm]
```

`prepare` selects a deterministic, feature-spanning set of one-shots for human
labels. The default duration cap is 2.5 seconds. `score` reports per-role
precision, recall and confusion against those ear labels.

## Profiles

### `sample-profile`

```text
sample-profile {show,validate} [--profile NAME] [--source-kb FILE]
```

`show` prints the resolved studio and device capabilities. `validate` compares
the profile's source version with the header of the external Studio Knowledge
Base. It does not inspect wiring or walk an archive directory.

Profile selection order is command line, `MUSIC_TOOLS_PROFILE`,
`~/.config/eidetic-sample-tools/config.toml`, then the built-in default.

## Output files

Common derived outputs include:

```text
manifests/review.tsv
manifests/index/high-confidence/<ROLE>.tsv
manifests/index/review-needed.tsv
manifests/sample-library.sqlite
manifests/sample-intelligence-pilot/
manifests/foundation-v1-review/
manifests/foundation-v1/
```

These are review evidence and generated views. Their presence does not mean that
an audio move or musical decision has been approved.

## Safety and recovery

- Review a plan before every `--apply`.
- Verify the library backup before a large move.
- Keep run manifests, human labels and undo records together.
- Do not delete `_TO-DELETE/` or `_QUARANTINE/` without a separate ear and path
  check.
- Re-run a plan after the library changes.

See the full [safety model](../docs/SAFETY.md) for action levels, hashes,
automation limits and recovery behaviour.
