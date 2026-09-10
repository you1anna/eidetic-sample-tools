# State and data contracts

This guide describes the records that connect the packages, what they establish,
and how their lifecycle differs from source audio. For commands, use the
[workflow](WORKFLOWS.md) and [library lifecycle](LIFECYCLE.md) guides.

[System overview](TECHNOLOGY.md) · [Library](../library-tools/ARCHITECTURE.md) ·
[Export](../sample-tools/ARCHITECTURE.md) · [Ableton](../ableton-tools/ARCHITECTURE.md)

## Ownership and storage

Typical locations below follow the documented workflow. Explicit output and
database paths can live elsewhere and need their own backup arrangements.

| State | Typical location | Owner and purpose |
|---|---|---|
| Library identity | `SAMPLES/.eidetic/library.json` | Library lifecycle; binds portable records to a UUID rather than one Mac's mount path. |
| Active index | `.eidetic/library.sqlite` | `library-tools`; assets, locations, metadata, decisions and derived features. |
| Mutation journals | `.eidetic/operations/` | Organisation and curation; reconcile filesystem work with database updates. |
| Captured older state | Under `.eidetic/`, recorded by onboarding | Preserve machine histories without replacing newer active decisions. |
| Reports, packets and crates | `.eidetic/runs/` in the guide examples | Explicit command outputs; retain the evidence used for decisions. |
| Collection revisions | User-selected new directory per revision | `plan.json` and `REVIEW.md`; self-contained, unreviewed metadata selections. |
| Browser audition | User-selected session directory outside the source library | Prepared previews, `session.json` and `shortlist.json`. |
| Curated copies | `SAMPLES/CURATED/` | Approved source-format copies; tracked as promotions. |
| Converted output | `SAMPLES/_EXPORT/` by default | `sample-tools`; device WAVs and adjacent `.wav.receipt.json` files. |
| Card-copy evidence | `.eidetic/transfers/` | `sample-tools`; per-run copy status and output hashes. |
| Ableton reports | Explicit report directory | TSV, `.tsv.metadata.json` and retained `.history/` reports. |
| Python environments and model files | Each machine's local disk | Installation/runtime state, separate from the portable library. |

The [state resolver](../library-tools/src/librarytools/state.py) prefers an
explicit database path, otherwise the portable database. It detects legacy
state requiring capture or adoption instead of silently opening or merging it.
The state directory cannot be a symlink. A library marker is only created by a
write path that explicitly needs it.

## Identity, paths and observations

`sample_id` is SHA-256 of the complete source file. Byte-identical copies share
an ID. Audio conversion and embedded metadata edits change it. The database
therefore separates an asset from its current and historical locations.

Paths locate bytes; they do not replace identity. Modern curation packets retain
a library UUID and can resolve source-relative paths against an explicitly
selected current root. A packet without a UUID cannot be rebound to a different
root. Audition sessions retain their prepared root and verify both original and
preview bytes; they are not automatically portable just because the index is.

A complete inventory scan describes an observation, not a continuously monitored
filesystem. Operations that promote, convert or serve audio recheck the relevant
files. Saved plans can be regenerated offline because their candidates and
history are embedded, but offline regeneration cannot establish current file
availability or approve those sounds.

## Records exchanged between stages

| Record | Current format | Contract |
|---|---|---|
| Library marker | `format_version: 1` | Library UUID and creation metadata; SQLite schema 5 has a matching identity row. |
| Collection plan | `eidetic-collection-plan`, version 1 | Full snapshot, history, policy, pins, choices, counts and content digests. Every selected decision is `unreviewed`. |
| Audition state | `schema_version: 1` | Registered originals, verified previews and separate `keep` / `skip` / `unreviewed` shortlist decisions. |
| Curation packet | `packet_format_version: 1`; supported packet schemas 1–3 | Candidate evidence, editable listening labels and identity-aware root resolution where available. |
| Generated crate | Five-column TSV + `eidetic-crate`, version 1 sidecar | `sample_id`, `source_path`, `role`, `descriptor`, `reason`; TSV hash and approval evidence when supplied. |
| Export receipt | `eidetic-export`, version 1 | Original and converted hashes, settings, tool/runtime versions, output size and software verification. |
| Transfer journal | `eidetic-transfer`, version 1 | Device, destination, selected output hashes and per-file copy status. |
| Ableton report metadata | `eidetic-ableton-report`, version 1 | Roots, input hashes, errors, exclusions, report hash, row count and completeness. |

These are versioned application formats, not interchangeable JSON documents.
Loaders validate the formats they accept. A digest detects changed content; it is
not a signature or independent proof of human approval. The planner additionally
reconstructs the selection to verify that its stored policy produces its choices.

Legacy five-column crates remain accepted without a sidecar as separately
reviewed inputs. Generated approval metadata is checked when present. The
exporter does not independently reconstruct the entire human review history
from SQLite; see the [export boundary](../sample-tools/ARCHITECTURE.md#input-contracts).

## Decisions are not interchangeable

| Evidence | What it establishes | What it does not establish |
|---|---|---|
| Metadata match or AI suggestion | A reason to consider or group a sample | Musical suitability or favourite approval. |
| Pin in a plan | Retain membership in later revisions | Listening, ordering position or export approval. |
| Browser Keep | Keep the original in this shortlist | A validated favourite with an export role and name. |
| Favourite and active promotion | Approved identity and curated copy for the curation workflow | Device compatibility or current hardware contents. |
| Verified export receipt | Matching source, settings, runtime and output bytes | A successful card transfer or instrument test. |
| Completed transfer | Selected copied bytes matched their expected hashes | Continued presence on the card or playable instrument state. |

Freshness uses original sample IDs from supplied export receipts or supported
delegated history, scoped to one device. Converted output hashes identify
different bytes. Missing history is **unknown**, and absence from supplied
records means only **not in those records**. Transfers do not form a live device
inventory. Details: [collection history](COLLECTION-PLANNER.md).

## Writer coordination and publication

Library mutations share the persistent `.eidetic/writer.lock` using non-blocking
Unix `flock`. The lock file remains after release; deleting it is not a recovery
procedure. Model subprocesses inherit the held descriptor for cache writes.
Classification review holds the library lock for the server's lifetime, while
the independent audition shortlist uses a session-local lock for each write.

The exporter implements the compatible protocol using its own standard-library
[state guard](../sample-tools/src/sampletools/export_state.py). It refuses newer
or inconsistent state and unfinished operations; it does not migrate or adopt a
library. Plans written inside portable state join the library lock and validate
the destination UUID. External plan directories do not lock the source drive.

Guarded read-only SQLite inspection requires settled database evidence, checks
the database fingerprint before and after, and avoids creating sidecars. It
aborts on detected changes instead of publishing a mixed snapshot. These locks
coordinate participating processes; they do not prevent unrelated programs from
changing audio or make a cloud-synchronised live database safe.

## Interruption and recovery

| Work | Publication boundary | After interruption |
|---|---|---|
| Inventory scan | Observations become current locations in one SQLite transaction. | An unfinished traversal does not replace the last complete view. |
| Move or promotion | Filesystem publication, database update and per-item journal progress are separate steps. | Recovery validates paths/hashes and reconciles journal items; the batch is not a filesystem/SQLite transaction. |
| Saved plan | New directory with individually written review and JSON files. | Ordinary errors clean up the new directory; a process crash can leave a partial directory. Parent revisions stay intact. |
| Conversion | Verified temporary WAV is renamed, then its receipt is published. | A WAV without its receipt is unverified and requires an explicit rebuild. |
| Card transfer | Each file is copied and verified through a temporary destination; the journal advances per file. | Completed files remain. A rerun can reuse matching card bytes and records a new transfer. |
| Ableton report | Previous files are archived; TSV and metadata are replaced separately. | A mismatched report/sidecar pair can be detected using the report hash. |

Atomic replacement applies to individual files, not entire collections. The
operation journal's purpose is to make partial work inspectable and recoverable.
Follow [recovery commands](LIFECYCLE.md) rather than editing state by hand.

## Backups, upgrades and derived data

The [backup implementation](../library-tools/src/librarytools/lifecycle.py) takes
the writer lock, uses SQLite's backup API, and checksums copied durable state.
It excludes transient lock/cache files and does not back up source audio. Output
directories outside the state tree are outside that bundle too.

Database opening validates structure and version; it cannot silently migrate.
Supported older schemas require an explicit migration with a verified backup.
An unknown or newer schema is rejected. Onboarding captures older machine
evidence without turning it into current approval; deferred history can remain
visible while current work proceeds.

Features and embeddings can be recomputed, but their versions and provenance
matter. Tags include their source, and human decisions are retained separately
from generated annotations. Maintenance should distinguish expendable derived
data from listening decisions, receipts, journals and historical evidence.
