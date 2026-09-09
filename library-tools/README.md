# Library tools

Find useful sounds in a large archive and build a collection worth playing.
`library-tools` combines content-hash inventory, musical tags, acoustic search
and recorded listening decisions. Organisation commands preview file moves;
search and analysis leave source audio in place.

## Install

From the repository root, in an activated Python 3.12 environment:

```bash
python -m pip install -e ./library-tools
```

See [Getting started](../docs/GETTING-STARTED.md) for environment setup, FFmpeg
and library paths. Set `SAMPLES_ROOT` or pass `--root` explicitly. Index commands
share `$SAMPLES_ROOT/.eidetic/library.sqlite` by default; use the same
`--library-db` wherever you override it.

Commands that need a sample library reject missing selection before doing work.
The [pinned AI setup](../docs/AI-SETUP.md) covers optional model installation,
offline verification, resource controls and reuse across a large library.

The examples keep generated reports, packets and crates on the library drive:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

Recompute `RUNS` after changing the mount path. Explicit output paths remain
supported, including older repository-local paths; preserve those separately or
include them when onboarding and backing up.

## Long-lived and shared-drive installations

Use `sample-library doctor --root "$SAMPLES_ROOT" --json` before upgrading.
`sample-library onboard --root "$SAMPLES_ROOT" --machine NAME` previews repeatable
setup on the current Mac; repeat with `--apply`. Use `--defer-machine NAME` for
another Mac's unavailable history. Later onboarding captures that history without
overwriting newer SSD decisions. No connection to the other Mac is required.

`sample-library` also provides explicit init, migrate, backup, restore and recovery
commands plus a maintenance preview. Follow the [lifecycle guide](../docs/LIFECYCLE.md)
before adopting old machine-local state onto the SSD. `sample-tag --retry-failed`
retries failed measurements; successful results retain versioned provenance.

## Command map

| Task | Commands | Maturity |
|---|---|---|
| Diagnose, onboard, upgrade and recover portable state | `sample-library` | Beta |
| Inspect names, roles and metadata | `sample-review` | Stable |
| Plan sorting, exact deduplication and pack intake | `sample-sort`, `sample-dedupe`, `sample-intake` | Stable |
| Recover origin, tag and search | `sample-tag`, `sample-find` | Beta |
| Prepare listening packets, promote favourites and check copies | `sample-curate` | Beta |
| Inspect configuration | `sample-profile` | Beta |
| Measure audio and build inventory | `sample-analyze` | Beta; interpretation experimental |
| Evaluate model suggestions and similar loops | `sample-benchmark`, `sample-role-cleanup`, `sample-near-dupes` | Experimental |
| Audition samples and keep a shortlist for curation | `sample-vibe` | Experimental; explicit candidates |

See the [roadmap](../docs/ROADMAP.md) for maturity definitions. Each command has
`--help`; the [workflow guide](../docs/WORKFLOWS.md) joins them into a session.

## Review and organise

### `sample-review`

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe --summary
sample-review --root "$SAMPLES_ROOT" --no-probe \
  --output "$RUNS/review.tsv" --index-dir "$RUNS/index"
```

The summary writes nothing; the second command writes TSV review material.
Fields include proposed role, loop/one-shot type, explicit BPM/key evidence,
tempo group, compact name and warnings. Indexes split by role, tempo and review
priority. Omit `--no-probe` for FFprobe duration fallback.

BPM parsing excludes instrument names such as 707, 808, 909, 303 and SH101.
Role confidence and tempo fit prioritise review; they never approve removal.

### `sample-sort`, `sample-dedupe`, `sample-intake`

```text
sample-sort [--root PATH] [--include-review] [--apply]
sample-dedupe [--root PATH] [--apply]
sample-intake [--root PATH] [--apply]
```

- **Sort** plans flat role folders; `--include-review` collects uncertain files
  in `_REVIEW/`. Numeric suffixes resolve name collisions without overwriting.
- **Dedupe** compares file bytes and moves extras to `_TO-DELETE/dupes/` only
  with `--apply`. It never deletes them. Sort first if both operations are needed.
- **Intake** finds vendor packs at the root or in `00_INBOX/`, normalises their
  folder names and plans moves into `PACKS/`. Loose root audio is excluded.

All three preview by default and record successful applied moves for undo.
Default plans and undo manifests are written under `$RUNS`; durable recovery
journals live beside them under `$SAMPLES_ROOT/.eidetic/operations/`.
Check the backup and plan before applying; regenerate plans after library changes.
The older `sample-classify [--root PATH] [--no-probe] [--apply]` coarse sorter is
retired; use review and sort for new workflows.

## Search

### `sample-tag`

```text
sample-tag [--root PATH] [--library-db FILE] [--vocabulary FILE]
           [--rescan] [--skip-features] [--retry-failed] [--apply]
           [--legacy-cache FILE] [--proposal FILE]
```

Recovers origins from pack folders, filename tokens and identical copies; reuses
or extracts acoustic features; evaluates [`vocabulary.toml`](vocabulary.toml).
Tags are rules over evidence:

```toml
[[tag]]
name = "tribal"
group = "style"
origin_matches = ["tribal"]
name_matches = ["conga", "bongo", "djembe", "cowbell"]
```

Without `--apply`, it writes a coverage proposal. Scans, origins and measurements
can still update the derived index. `--apply` replaces generated tags from the
vocabulary while preserving human and unclassified legacy tags; neither mode
moves, renames or converts audio. The coverage proposal defaults to
`$RUNS/vocabulary-proposal.txt`. `--legacy-cache` can import compatible measurements
from an older installation; it does not import listening approval.

### `sample-find`

```text
sample-find [TERMS...] [--root PATH] [--library-db FILE]
            [--role R] [--style S] [--gear G] [--character C] [--origin O]
            [--any] [--curated-only] [--like PATH|ID] [--preferred] [--no-spread]
            [--limit N] [--m3u8 FILE] [--crate FILE] [--kit-id ID]
```

Terms combine with AND across tags, origins and names; `--any` matches any term.
Default ranking spreads results across sound families. `--no-spread` sorts
alphabetically; `--like` ranks acoustic distance to an indexed ID or unique path
fragment; `--preferred` ranks recorded kit picks.

```bash
sample-find --root "$SAMPLES_ROOT" perc tribal analog --limit 20 \
  --m3u8 "$RUNS/percussion.m3u8"
sample-find --root "$SAMPLES_ROOT" --like YOUR_SAMPLE_ID --role PERC --limit 10
```

`--like` uses min-max normalised Euclidean distance over measured features.
It requires no model download. `--kit-id` records the returned selection as a
future ranking signal; picks do not replace curation decisions.

`--crate` writes the [export schema](../sample-tools/README.md#crate-format).
Use `--curated-only` to restrict results to indexed `CURATED/` paths. The exporter
rejects the entire crate if any source is outside that zone or fails its hash
check. New search crates also record whether their exact copies have active
promotion evidence; rows missing that evidence require review before export.
This matters after onboarding with incomplete historical records: existing curated
files remain searchable, but their folder alone cannot approve a generated crate.
Search warns when a written crate contains uncurated or unverified rows.

## Curation

### `sample-curate`

Global options go before the subcommand:

```text
sample-curate [--root PATH] [--library-db FILE] SUBCOMMAND ...
```

| Subcommand | Required options | Result |
|---|---|---|
| `prepare` | `--output-dir` | Labels, scan metadata and an audition playlist; optional `--quotas`. |
| `classify-packet` | `--labels`, `--benchmark` | Audio predictions, cached embeddings and review candidates. |
| `review-packet` | `--labels` | Local playback and classification review; optional `--open`, `--port`. |
| `playlists` | `--labels` | Rebuilds playlists after review and benchmark gates pass. |
| `validate` | `--labels` | Checks every required listening decision. |
| `promote` | `--labels`, `--run-id` | Hash-checks sources and copies favourites into `CURATED/`. |
| `views` | `--labels`, `--output-dir` | Device and Ableton TSVs; optional `--quotas` and `--name`. |
| `check` | None | Read-only verification; optional `--run-id`, `--json`. |
| `undo-promotion` | `--run-id` | Moves curated copies into quarantine immediately; no `--apply` gate. |
| `migrate-catalogue` | `--ableton-root`, `--manifest`, `--undo` | Legacy-layout plan; `--apply` moves after preflight. |

Follow the [curation walkthrough](../docs/WORKFLOWS.md#3-curate-by-ear).
Promotion requires a complete label set; every favourite needs a canonical role
and descriptor. Sources and destinations are preflighted before writing, and
promotion and undo update indexed locations immediately. Migration checks for
`CURATED` references in saved Sets and requires a reviewed plan and backed-up library.

`prepare` and `views` accept a TOML file through `--quotas`. Its `[quotas]` table
maps canonical roles to non-negative integer targets, with at least one positive
target. Views require enough promoted favourites to meet those targets.
`--name` sets the crate filename prefix using letters, digits, hyphens or
underscores. Defaults retain the Foundation quotas and `foundation-v1` prefix.

### Packet classification

Install the optional local models and review UI:

```bash
python -m pip install -e './library-tools[audio-classifier,review-ui]'
```

After preparing a packet:

```bash
sample-curate --root "$SAMPLES_ROOT" classify-packet \
  --labels "$RUNS/session-01/labels.tsv" \
  --benchmark "$RUNS/session-01/benchmark-labels.tsv"
sample-curate --root "$SAMPLES_ROOT" review-packet \
  --labels "$RUNS/session-01/labels.tsv" --open
```

Two pinned CLAP checkpoints run sequentially and cache embeddings. The ensemble
uses acoustic form evidence and audio content prompts; filenames have zero
decision weight. Its nine groups cover rim, tom and percussion hits; percussion
and drum loops; vocal stabs, phrases and long sources; and out-of-brief material.

Review every exception and one blind sentinel per accepted group. A failed
sentinel reopens that group. The UI supports notes, undo and resume, writes
`review-state.json` atomically and generates the 24-row benchmark when the queue
completes. Do not edit benchmark rows manually.

The review server holds the library writer lock for its lifetime. Stop the server
in the terminal when the session is finished; closing the browser tab alone does
not stop it. After SSD handoff, the explicit `--root` rebinds a portable packet to
the attached library only when its UUID matches. Regenerate playlists to refresh
absolute audio paths for the current mount.

Grouped playlists require complete review and at least 22/24 form and 19/24
joint content/group matches. This permits shortlist publication; musical
approval still requires decisions in `labels.tsv`.

For prompt-tuning reruns, `--carry-review` retains human decisions by sample hash
and reopens newly affected automatic samples. `--restart-review` archives and
discards prior decisions; the flags are mutually exclusive. Undo or changed
classification withdraws stale playlists to `archive/stale-publications/` until
new evidence passes. Initial name-derived playlists are retained in `archive/`.

After removing label rows, regenerate playlists immediately:

```bash
sample-curate --root "$SAMPLES_ROOT" playlists --labels "$RUNS/session-01/labels.tsv"
```

Missing or stale classification fails validation. Read the
[architecture guide](../docs/TECHNOLOGY.md#optional-local-ai-for-listening-packets)
for model execution and publication details.

### Promotion integrity checks

```bash
sample-curate --root "$SAMPLES_ROOT" check --run-id session-01 --json
```

Omit `--run-id` to check all recorded promotions. Current bytes are hashed for
the original, curated copy and relevant promotion-undo quarantine path. Results
are `ok`, `missing` or `changed`; a matching quarantined copy is accounted for
only when its original also matches.

| Exit | Meaning |
|---|---|
| `0` | No discrepancies among recorded promotions. Empty history reports no promotions. |
| `1` | Missing or changed content. |
| `2` | Invalid input, unknown run or unreadable evidence. JSON mode returns an `error` object. |

The check reads a settled database without modifying its schema or sidecars.
Pending journal evidence or a database change during the query returns `2`.
Finish other database work before retrying; retained journals may need recovery
by the owning tool. This checks recorded paths only, without rescanning,
repairing or restoring files, and does not certify the whole library.

## Analysis and experiments

### `sample-vibe`

Hear explicit candidates in a local browser, Keep or Skip them, then compare the
saved shortlist. The main screen has one player with seek, looping and Undo.
This is an audition and curation tool; it does not generate candidates from a vibe
or learn from your choices. The existing search and classification methods are
unchanged.

```bash
sample-vibe prepare --root "$SAMPLES_ROOT" \
  --anchor "PACKS/example/percussion-loop.wav" \
  --vocal "CATALOGUE/VOCALS/example-phrase.wav" \
  --output-dir "$HOME/Library/Application Support/Eidetic Sample Tools/auditions/session-01" \
  --bpm 140
sample-vibe serve \
  --session-dir "$HOME/Library/Application Support/Eidetic Sample Tools/auditions/session-01" \
  --open
```

Install the `review-ui` extra and FFmpeg. Preparation creates previews in a new
session outside the source library; listening and saving do not require an index.
`shortlist.json` records the latest per-source decisions, independently of
`sample-find --preferred` kit picks. It is not a complete training history.

The Kept view can download a playlist or prepare a normal curation packet from the
exact selected originals. Packet preparation requires a bound index and complete
scan. It creates `keep` rows; explicit favourites, roles and descriptors remain
necessary before promotion and device export. The equivalent CLI commands are
`sample-vibe playlist` and `sample-vibe packet`.

The [audition guide](../docs/GROOVE-AUDITION-PILOT.md) covers input limits, saved
choices, export handoff and the separate optional `/vocal-lab` experiment.
The server binds only to the Mac's `127.0.0.1`; iPhone audio forwarding is unverified.
Stop it with Ctrl-C and rerun `serve` to resume.

### `sample-analyze`

```text
sample-analyze [--root PATH] [--output-dir DIR] [--pilot]
               [--feature-cache FILE] [--no-probe] [--profile NAME]
               [--library-db FILE] [--classifier]
```

`--pilot` writes source registries, features, reports and candidate crates under
`$RUNS/sample-intelligence-pilot` unless `--output-dir` is supplied. It refreshes
the portable inventory when present; `--library-db` selects an explicit database.
`--no-probe` skips duration and acoustic extraction. Candidate crates require human
curation before hardware use.

`--classifier` invokes the older CNN-LSTM drum-role experiment. Its first route
failed ear calibration, so output remains suggestion-only. It requires the
separate `classifier` extra and user-supplied weights at
`models/drum-cnn-lstm.model` relative to this package, or `DRUM_MODEL_PATH`.
Upstream weights are unlicensed and must remain uncommitted.

### `sample-near-dupes`

```text
sample-near-dupes [--features FILE] [--output-dir DIR] [--root PATH]
                  [--family TEXT] [--limit-groups N]
                  [--apply-manifest FILE] [--apply]
```

The pilot emits long, high-certainty loop pairs; short-hit similarity proved
unreliable. Audition and mark `decision=remove`, then pass the reviewed TSV with
`--apply-manifest`. It still previews unless `--apply` is explicit.

Features default to `$RUNS/sample-intelligence-pilot/sample-features-latest.tsv`
and output to `$RUNS/near-dupes-pilot`, resolved from the selected `--root`.
Pass `--features` or `--output-dir` to reuse evidence stored elsewhere.

### `sample-role-cleanup` and `sample-benchmark`

```text
sample-role-cleanup prepare --audit FILE --root PATH --output-dir DIR
sample-benchmark prepare --output-dir DIR [--root PATH] [--features FILE]
                         [--per-role N] [--max-duration SECONDS]
sample-benchmark score --output-dir DIR [--root PATH] [--model cnn-lstm]
```

Cleanup freezes classifier routes into deterministic audition packets; every
calibration row must be labelled before a route can advance. Benchmark preparation
selects feature-spanning one-shots (default duration cap: 2.5 seconds); scoring
reports precision, recall and confusion against ear labels. Failed routes stay
rejected. Neither tool authorises audio moves or musical selections.

Benchmark features default to the selected library's
`.eidetic/runs/sample-intelligence-pilot/sample-features-latest.tsv`. Choose a
named portable packet directory with `--output-dir "$RUNS/benchmark-session-01"`;
explicit feature and output paths remain supported.

## Profiles

### `sample-profile`

```text
sample-profile {show,validate} [--profile NAME] [--source-kb FILE]
```

`show` prints resolved capabilities. `validate` checks version and date headers
against a supplied source document; it does not test hardware compatibility.

Selection order: `--profile`, `MUSIC_TOOLS_PROFILE`,
`~/.config/eidetic-sample-tools/config.toml`, then the bundled `eidetic-studio`
profile. Profiles describe supported capabilities; additional devices also need
export and transfer implementation. See [configuration](../docs/SAMPLE-FOUNDATION-WORKFLOW.md).

Retain manifests, labels and undo records together. The
[safety model](../docs/SAFETY.md) defines apply, backup and recovery requirements.
