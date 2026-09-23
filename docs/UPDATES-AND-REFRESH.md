# Update the tools and keep the library current

A software installation and a sample library are separate things. Updating one
does not automatically update the other. The toolkit reports the work required;
the same commands serve a person at the terminal and a client application.

## After updating the toolkit

Select the intended release in your checkout, then check the executable you
actually use. `TOOLKIT_DIR` is that checkout's absolute path:

```bash
sample-library version --checkout "$TOOLKIT_DIR" --json
```

This compares package versions and actual Python/resource bytes with the bundled
release manifest and the chosen checkout. It catches an older non-editable install,
same-version source changes and altered installed files. It does not contact GitHub;
fetch/pull deliberately when choosing an update. A clean Git status against stale
local remote-tracking refs is not evidence that a checkout is current upstream.

If installation is required, use the chosen environment's Python and the
[release procedure](RELEASING.md). Preserve installed extras and dependencies, run
`python -m pip check`, and repeat the version check. An editable installation also
needs a valid release manifest; its live source can change without reinstalling.
The four packages retain independent versions. A library-search release does not
by itself change the exporter or invalidate existing export receipts.

Then inspect the library:

```bash
sample-library status --root "$SAMPLES_ROOT" --checkout "$TOOLKIT_DIR" --json
sample-library refresh --root "$SAMPLES_ROOT" --checkout "$TOOLKIT_DIR" --json
```

`refresh` without `--apply` is a read-only preview, including a full-root file
inspection. It lists the required work. Review that result, then apply:

```bash
sample-library refresh --root "$SAMPLES_ROOT" --checkout "$TOOLKIT_DIR" --apply --json
sample-library status --root "$SAMPLES_ROOT" --checkout "$TOOLKIT_DIR" --check-files --json
```

The apply rechecks under the library writer lock, makes a verified state backup,
performs only necessary stages, and saves a receipt under `.eidetic/runs/`.
The default backup is a new dated entry under `.eidetic/backups/`; use
`--backup-dir /path/on/backup-disk/new-directory` to choose another destination.
A backup on the sample disk is a rollback snapshot, not protection against losing
that disk. State backups do not include source audio. Existing audio backup and
listening/approval rules still apply. An unchanged refresh does no work and creates
no backup or receipt.

## When each kind of work is needed

| What changed | Action | What remains reusable |
|---|---|---|
| Documentation only | None. | Installed code and library data. |
| Search matching or presentation | Install the release; repeat readiness check. | Inventory, measurements and tags unless their own inputs changed. |
| Role detection, origin recovery, tag rules or selected vocabulary | Regenerate generated tags. | Source audio, inventory and current measurements. |
| Added, moved, removed or modified audio | Reconcile the full inventory, then refresh affected derived evidence. | Features keyed to unchanged content identities; human decisions/history. |
| Missing measurements or changed acoustic extractor version | Measure the affected identities only. | Successful current-version measurements. |
| Known decoder/measurement failures | Inspect the warning; use `refresh --retry-failed` when deliberately retrying. | Successful measurements; failed evidence stays visible. |
| Database schema version | Preview the existing backed-up `sample-library migrate`; apply explicitly. | Supported durable history; refresh never silently migrates. |
| AI model revision, prompts or excerpt policy | The next explicit AI operation computes the affected cache entries. | Compatible embeddings; ordinary metadata search needs no model run. |
| Converter, FFmpeg or device settings | Existing export-receipt checks decide whether a conversion can be reused. | Approved originals and unaffected verified exports. |

A package version is not a request to rebuild every derived file. Tag records
carry their own recipe, input and output fingerprints. Older unstamped tags need
one regeneration to establish those records. The existing database schema already
supports the records; this release does not require a schema migration.

## Add a pack occasionally

Finish copying/extracting the intact pack into the library's source area, normally
`PACKS/`. Preserve the archive and follow the existing intake preview/apply rules
if files need organising. Then use the same full-library refresh preview above.
Do not point the full-library database at just the new pack: a complete scan retires
paths it no longer sees. The root UUID check rejects that mismatch.

The preview enumerates audio paths and compares size/mtime without decoding or
hashing audio. Ordinary `status` skips that walk unless `--check-files` is given,
and reports that limitation explicitly. A client starting a fresh selection should
request `--check-files` so added samples cannot be missed silently.

When reconciliation is needed, the existing inventory scan verifies full content
hashes across the root before publishing. It does not trust an inode cache across
machines. Acoustic extraction then skips identities that already have current
measurements, including exact duplicates and moved files. Routine code/tag changes
and unchanged refreshes do not trigger that content scan. File-stat inspection is
not a corruption audit: to verify bytes even when size/mtime were preserved, use
the established explicit full rescan workflow and review its results.

For a large library, batch additions before refreshing. Inspection is linear in
the number of paths; a required inventory scan is linear in source bytes; acoustic
decoding is limited to missing/stale identities. No model download or inference is
part of refresh.

## Rules, failures and retained decisions

The shipped schema-2 vocabulary matches words and explicit aliases. `hihat`,
`hi hat` and `hi-hat` are equivalent; `perc` also finds percussion. `rap` does not
match Trap, `house` does not match Warehouse, and TR808 does not become TR-8.
Literal `name_suffixes` recognise final filename-stem tokens such as `_orig`,
`_x` and `_x2` without making arbitrary fragments into tags.

Schema-1 custom vocabularies retain their declared substring semantics. An update
preserves the selected custom snapshot; it does not silently replace it with the
shipped rules. Use `--vocabulary FILE` on the refresh preview and apply to select
or migrate a custom vocabulary. Its verified snapshot travels with the library.

Refresh replaces only generated tags. Human tags, reviews, favourite decisions,
promotions, picks and frozen collection plans remain. A new inventory can reveal
missing/changed promoted files; it preserves that discrepancy rather than inventing
replacement approval. Check promotion health before exporting affected selections.

An interrupted inventory retains the last completed locations. Completed acoustic
measurements survive an interruption and are reused on retry. Tags and their
freshness record publish in one transaction. Re-run the refresh preview after a
failure; do not delete the database to make the warning disappear.

## Client contract

`version`, `status` and `refresh` JSON use `contract_version: 1`. Exit codes are
`0` (`ready`), `1` (`action_required`), and `2` (`blocked`). An action has a stable
`id`, a `reason`, and an `argv` array for a supported preview command. Clients
must not execute arbitrary shell strings or automatically add `--apply`.

Use `version` without a mounted library. Use `status` before a new selection;
it nests release identity under `runtime`, state under `library`, and returns
`actions`, `issues` and `warnings`. Required installation/schema/data work must be
resolved before declaring that selection ready. Known measurement failures and
obsolete optional AI caches are visible warnings, not mandatory infinite retries.

Choose `sample-library` from the same installation as the consumer commands.
Unknown contract versions, malformed output and status/exit-code disagreement
must fail explicitly. Clients should own their musical brief and hand-off; the
toolkit owns freshness, refresh execution and database details.
