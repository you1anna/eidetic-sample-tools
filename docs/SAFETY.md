# Safety model

## The short version

Preview first. Read the manifest. Listen before promoting. Apply only against a
backed-up library.

Eidetic Sample Tools never treats a model score as permission to move audio.
Commands that organise files default to a dry run, do not overwrite destinations
and record successful moves. Export and curation work with copies.

## Action levels

| Action level | Effect on source audio |
|---|---|
| **Read-only** | Reads paths, metadata or audio and prints a result. |
| **Writes derived files** | Creates manifests, databases, reports or audition packets; source audio stays in place. |
| **Moves audio after `--apply`** | Previews by default; moves only after explicit approval and records successful moves. |
| **Copies approved audio** | Creates curated or converted copies; source audio stays in place. |

Representative commands:

| Command | Default action | Mutation gate |
|---|---|---|
| `sample-review` | Prints a summary or writes requested TSV files | Never moves audio |
| `sample-analyze` | Writes analysis manifests, reports and caches | Never moves audio |
| `sample-tag` | Writes origin, measurements and tags to the index | Never moves audio |
| `sample-find` | Prints matches; writes playlists and crates | Never moves audio; has no apply path |
| `sample-sort` | Writes a move plan | `--apply` moves audio and writes an undo manifest |
| `sample-dedupe` | Writes a duplicate plan | `--apply` moves extras to `_TO-DELETE/dupes/` |
| `sample-intake` | Writes an intake plan | `--apply` moves detected packs |
| `sample-curate migrate-catalogue` | Writes a migration plan | `--apply` moves audio after preflight |
| `sample-curate promote` | Copies hash-verified favourites | Complete human labels and an explicit command |
| `sample-export --list` | Prints resolved source and output names | No conversion |
| `sample-export --dry-run` | Prints planned conversions | No conversion |
| `sample-export` | Writes converted copies under the export root | Running without a preview flag |
| `sample-export --sync` | Copies a built export to mounted media | Explicit destination path |

## Preview before apply

Run a command without `--apply`, save its plan, and inspect source and destination
paths. Check for surprising categories, name collisions, stale roots and device
capacity errors.

An apply flag is confirmation of a specific reviewed plan, not a general setting.
Refresh the plan after the library changes.

`sample-export` is different: its normal action writes converted copies. Use
`--list` to resolve inputs and `--dry-run` to preview conversion first.

## Manifests and content hashes

Manifests make decisions inspectable. They show what a command read, proposed or
changed. Keep the plan, labels and undo record together under a named run.

The stable inventory uses a SHA-256 `sample_id`. An exact copy keeps the same
identity even if its path changes. Promotion checks the current source against
that identity before copying, which prevents a reviewed row from silently
pointing at changed content.

A hash proves content identity. It does not prove that a label is musically
correct or that two similar-sounding files are interchangeable.

## Human approval

Listening is the final gate for:

- promotion into `CURATED/`;
- drum-role correction;
- near-duplicate removal decisions; and
- device performance crates.

Classification confidence is not measured musical correctness. The first
drum-role calibration demonstrated this directly: a high-confidence proposed
route failed the ear check and was rejected.

Audition packets make the decision explicit. Complete every required label,
record uncertainty as uncertainty, and reject a route when its calibration does
not hold.

## Undo and quarantine

Move-based tools never overwrite an existing destination. Applied operations
write undo records only for files that actually moved. These records are plain
TSV evidence; keep them until the new layout and dependent projects are verified.

Exact duplicates are moved to `_TO-DELETE/`, not deleted. Deletion remains a
separate human decision outside these tools.

Promotion recovery moves curated copies to `_QUARANTINE/promotion-undo/`. This
preserves the copy for inspection while removing it from the active collection.

## Limits of automation

Filename rules, acoustic features and models can narrow a review. They cannot
judge whether a sound is good, useful in a set, correctly perceived by a person,
or safe to remove from a musical workflow.

The experimental drum classifier and near-duplicate detector therefore produce
candidates only. They do not authorise moves, exclusions, curation or hardware
exports.

Device validation is narrower and more reliable: it can check format, duration,
capacity, hash, role and path rules. It still cannot choose the right sounds for
a performance.

## Backup responsibilities

Undo records are not backups. Keep the master library on a backed-up filesystem
and verify that backup before a large apply operation.

Treat device cards and `_EXPORT/` as rebuildable copies. Keep source packs,
catalogue audio, human labels and manifests on backed-up storage. When an Ableton
project may refer to a path, run the reference preflight and verify the project
after migration.
