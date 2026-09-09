# Portable library lifecycle

Release 0.2 introduces explicit database upgrades and portable state. Each library
has one identity and one writer. Move the SSD between Macs after commands finish
and eject it normally. Each Mac can be installed and onboarded independently;
install a compatible release on a returning Mac before using the SSD there.
Do not put the live database on a network share or synchronise two editable copies.

## What travels with the audio

`SAMPLES/.eidetic/` holds `library.json` (UUID and state format), `library.sqlite`,
operation journals, run manifests, configuration snapshots, imported historical
evidence, and transfer records. Generated feature caches live under `cache/`.
Audio locations in the database are relative to the library root. Machine and
mount paths are diagnostic hints; the UUID establishes library identity.

The Python environments, installed packages and model checkpoints remain local
to each Mac. Set paths for the current mount after activating that Mac's environment:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

`RUNS` is a shell variable for the portable report, packet and crate paths used in
the [workflow examples](WORKFLOWS.md). Recompute it after changing `SAMPLES_ROOT`.
Older explicit output paths remain supported; include any evidence outside
`.eidetic/` when onboarding or backing up.

Explicit `--library-db` remains supported. Otherwise tag, search and curation
resolve `.eidetic/library.sqlite` below the selected `--root`. A repository-local
legacy database requires explicit onboarding or migration. No databases are merged
automatically. If the SSD has no state, ordinary tagging refuses to silently
start a replacement history.

Human decisions, provenance, operation evidence and manifests are durable data.
Caches and exported WAVs can be rebuilt. A state backup does **not** back up source
audio; keep a separately verified audio backup under the existing safety model.

## Set up each Mac independently

The other Mac does not need to be online. Install the tools in an environment on
the current Mac, attach the SSD, then preview its onboarding:

```bash
sample-library onboard --root "$SAMPLES_ROOT" --machine macbook \
  --defer-machine mac-mini
sample-library onboard --root "$SAMPLES_ROOT" --machine macbook \
  --defer-machine mac-mini --apply
```

Use stable machine labels that you recognise. `--defer-machine` records unavailable
history; it does not require a connection to that machine or block normal work.
Setup inspects only evidence available here. It reuses an existing portable database,
or adopts the current machine's recognised legacy database when the SSD has none.
Without either database it creates a new index with incomplete historical coverage.
Existing audio, including `CURATED/`, is not treated as an imported listening decision.
It remains searchable and auditionable. Search-generated hardware crates identify
rows without recorded active promotions as requiring review; an old folder name
cannot supply that approval. Use preserved promotion evidence or listen and promote
through the normal curation workflow.

When the other Mac becomes available, install the current tools there and run the
same command using its own label and local evidence:

```bash
sample-library onboard --root "$SAMPLES_ROOT" --machine mac-mini \
  --library-db /path/to/old/manifests/sample-library.sqlite \
  --include /path/to/old/manifests
```

Review the preview, then repeat with `--apply`. With an active SSD database, the
incoming database and human files are preserved as verified historical evidence;
they never replace current SSD decisions. Doctor reports that history still needs
review, while normal work can continue. Repeating the command reuses unchanged
evidence. Changed offline labels or databases require another capture and retain
both versions. Backups include captured histories and onboarding records.

Capturing a second database does not merge its approvals into the active database.
Keep that evidence while reviewing discrepancies; use the current curation workflow
for new listening decisions. An incomplete coverage report is expected while a
machine is deferred or captured history remains unreconciled.

Automatic discovery checks the current checkout's legacy manifests directory.
For old checkouts or separately installed wheels, supply `--library-db` and repeated
`--include` paths explicitly. Include labels, review state, packet metadata, quotas,
configuration, manifests and undo records stored elsewhere. These tools cannot
prevent an older executable from continuing to write its own local files; upgrade
each Mac before using it and run onboarding again if those records change.

## Inspect before upgrading

```bash
sample-library doctor --root "$SAMPLES_ROOT" --json
sample-library doctor --root "$SAMPLES_ROOT" --library-db /path/to/old/library.sqlite --json
```

Doctor reads settled evidence without creating a database, taking a writer lock,
changing schemas or recovering SQLite journals. Exit `0` means no reported issue,
`1` means review is needed, and `2` means missing or unreadable database evidence.
It is not a complete source-hash audit or proof of musical approval. Pending SQLite
journals must be resolved by the owning database process before inspection.

For an existing installation, collect the current Mac's installed versions and
available evidence. Record unavailable machines with `onboard --defer-machine`;
their absence does not delay use of this Mac. Preserve contradictory and unexplained
evidence; a new scan does not erase an earlier discrepancy.

Rehearse migration on copies first. After reviewing the preview, adoption can copy
the selected legacy database into a new portable destination:

```bash
sample-library migrate --root "$SAMPLES_ROOT" \
  --library-db /path/to/old/sample-library.sqlite \
  --destination "$SAMPLES_ROOT/.eidetic/library.sqlite" \
  --include /path/to/old/manifests --backup-dir /path/to/backup/upgrade-01
```

Add `--apply` to the reviewed command to execute. Existing destination state is
never merged or replaced. Recognised schemas 1–4 upgrade to schema 5 after a
verified backup; actual tables, keys and constraints are checked independently of
the old version stamp. Unknown or newer schemas fail without modification.
Additional evidence is preserved under `imports/`; importing files never invents
favourite decisions. In-place migration is available by omitting `--destination`.

The low-level `init` command is for a **new library with no earlier history**:

```bash
sample-library init --root "$SAMPLES_ROOT"
sample-library init --root "$SAMPLES_ROOT" --apply
```

Existing audio is counted as unverified. Use `onboard` when historical coverage
is incomplete.

## Ongoing work and interruption recovery

Scans publish their inventory only after successful traversal and final checks.
An unavailable drive, unreadable directory or interrupted scan retains the last
completed inventory. Rerun the scan to replace incomplete scan observations.
Full scans rehash audio; device/inode caches are not trusted across Macs.
Repeated analysis archives prior reports under `.history/` before replacing
`*-latest.tsv` outputs. `analysis-run.json` records completion and output hashes;
an incomplete or failed run does not invalidate retained historical evidence.

Moves, promotions and promotion undo persist their intent before changing files.
One unfinished operation blocks unrelated mutations. Inspect and recover it:

```bash
sample-library recover --root "$SAMPLES_ROOT" --json
sample-library recover --root "$SAMPLES_ROOT" --operation-id OPERATION_ID --apply
```

Recovery compares source/destination bytes with the recorded intent. It continues
only verified work and preserves conflicts for investigation. Completed moves
retain ordinary TSV undo records as well as their journals. Moves within a library
use exclusive same-filesystem renames; cross-filesystem moves fail intact.
Sidecar dependencies are reported with move plans, not automatically rewritten.
Recovery writes a portable `.eidetic/operations/<operation-id>.undo.tsv` using
root-relative destination-to-source rows. The original absolute-path undo file
is retained; recovery never overwrites a path from the other Mac.

New listening packets have immutable IDs and refuse to overwrite occupied output
directories. Use a new directory for a new packet. Existing packet versions remain
readable; unsupported versions fail. For a changed mount point, pass the current
`--root` to packet review or playlist regeneration; the library UUID must match.
Global `sample-curate` options go before its subcommand:

```bash
sample-curate --root "$SAMPLES_ROOT" review-packet \
  --labels "$RUNS/session-01/labels.tsv" --open
sample-curate --root "$SAMPLES_ROOT" playlists \
  --labels "$RUNS/session-01/labels.tsv"
```

Promotion status distinguishes active, withdrawn and missing records, with retained
event history. A replayed old promotion cannot resurrect a withdrawn decision.
The review server holds the library writer lock until its process exits. Stop it
in the terminal before scanning, tagging or exporting on that library; closing
the browser tab alone does not release the lock.

Acoustic results carry an extractor version and provenance. Algorithm changes
invalidate reuse. `sample-tag --retry-failed` retries failed measurements while
retaining valid successes. Legacy stat-based imports remain identifiable as
estimates; ambiguous matches are remeasured. Retagging replaces generated tags in
one transaction and preserves human and unclassified legacy tags.

## Export, backup and retention

Use this routine after significant listening or organisation work:

1. Stop writers, including review servers, then run `sample-library doctor` and
   inspect any unfinished operations before continuing.
2. Back up durable state to a new, dated directory on a different backed-up disk.
   Include human evidence stored outside `.eidetic/`; a backup on the sample SSD
   alone does not protect against losing that SSD.
3. Rehearse `sample-library restore` into a new scratch directory and compare
   decision counts and representative evidence with the source. The restored
   directory contains the **contents of `.eidetic/`**, not an audio library.
4. Use `sample-library maintenance --root "$SAMPLES_ROOT" --json` to inspect growth.
   It reports candidates and database caches without deleting them.

| Data | Retention and recovery |
|---|---|
| Source audio in `PACKS/`, `CATALOGUE/`, `CURATED/` | Separate audio backup; absent from state bundles. |
| `.eidetic/library.sqlite`, labels, packets, histories, journals, receipts and manifests | Preserve as durable evidence with the state backup; include external evidence explicitly. |
| `.eidetic/cache/`, `caches/`, `tmp/` | Excluded from state bundles; inspect with maintenance before considering manual cleanup. |
| Embeddings and acoustic features stored in SQLite | Included with the database even though they can be recomputed; maintenance reports their versions and size. |
| `_EXPORT/` | Rebuildable WAVs and conversion receipts; preserve reviewed crates needed to reproduce the selection. |
| Quarantine and incomplete copy stages | Retain until recovery has been reviewed; do not treat them as disposable cache. |
| Local Python environments and model checkpoints | Reinstall locally; keep code revision and dependency records for reproducibility. |

Keep multiple verified backup generations. A failed backup can leave a partial
directory; it is not a valid recovery point. Restore checks manifest structure and
checksums before creating its destination. Correct or recover damaged backup
evidence rather than editing checksums to make verification pass.

Each new exported WAV has a `.receipt.json` sidecar binding source hash, conversion
settings, runtime versions and output hash. Only matching receipts and bytes are
reused. `--list` and `--dry-run` preview as before; stale or unverified existing
outputs require an explicit `--force` rebuild. Crates keep their five TSV columns
and add a versioned `.metadata.json` sidecar. Legacy crates remain readable.

Transfers record per-file progress and hashes under `.eidetic/transfers/`. Transfer
completion is separate from hardware playback/save/reload verification, which
remains unverified until a person tests the instrument. Existing card files outside
the selected transfer are not pruned.

Pass `--root "$SAMPLES_ROOT"` to `sample-export` to select that library's sources,
lock and transfer records, and default staging to its `_EXPORT/`. Use `--export-root`
for an explicit alternative staging path. An explicit `--root` ignores a stale
`EXPORT_ROOT` environment setting from another Mac.

```bash
sample-library backup --root "$SAMPLES_ROOT" --output /path/to/backups/session-01
sample-library backup --root "$SAMPLES_ROOT" --output /path/to/backups/session-01 --apply
sample-library restore --source /path/to/backups/session-01 --output /path/to/restore-check
sample-library restore --source /path/to/backups/session-01 --output /path/to/restore-check --apply
sample-library maintenance --root "$SAMPLES_ROOT" --json
```

Backup uses SQLite's backup API and checksums durable state. Add repeated
`--include` paths for evidence stored elsewhere. Restore verifies every recorded
file into a new directory; it does not replace or activate the live library.
Validate restored identity, decision counts and representative hashes before a
deliberate switch. Maintenance is a preview only. Audio, quarantine, human
decisions and recovery history have no automatic deletion policy.

Its database summary groups embedding storage by model, revision and policy, and
acoustic features by extractor version and provenance, including failed or stale
results. Abandoned hidden promotion-copy stages are listed for recovery review,
not removal.

Ableton TSV reports now include dated input hashes, root availability, parse
failures and a completeness flag in metadata. Replaced reports are archived under
`.history/`. Missing roots and malformed Sets mean an incomplete observation, not
proof that dependencies are absent. Reports never relink or edit Sets.
