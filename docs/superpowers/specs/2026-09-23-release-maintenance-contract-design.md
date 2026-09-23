# Release and library maintenance contract

The toolkit owns the meaning and freshness of its derived data. Clients consume a
versioned JSON report and supported commands; they do not infer freshness from a
package version, a successful `--help`, or private copies of the database.

## Scope and ownership

`librarytools` advances to 0.3.0. Packages retain independent semantic versions:
an unchanged exporter need not change version or invalidate conversion receipts
because the library search code changed. Release tooling records every package's
version and source/resource hashes in a bundled manifest. CI checks the manifest
and rejects changed runtime code shipped under an unchanged version. Runtime
inspection compares actual installed bytes, the bundled manifest, and optionally
the selected checkout. No network fetch occurs during ordinary inspection.

`sample-library version --json [--checkout PATH]` works without a mounted library.
`sample-library status --root ROOT --json [--checkout PATH] [--check-files]`
adds library freshness. Both return `contract_version: 1`. Status uses `ready`,
`action_required`, or `blocked`; exit codes are respectively 0, 1, and 2. Actions
carry stable identifiers, reasons and argument arrays, never executable shell text.
Optional missing packages are reported without blocking core library use.

## Conditions and work

| Condition | Required work |
|---|---|
| Installed code differs from the chosen checkout/release | Install the chosen tested release; inspect again. |
| Search-only code changed | Reinstall; no inventory scan, measurements or tags solely for this change. |
| Role, origin or tag rules/vocabulary changed | Regenerate generated tags from indexed evidence. |
| New, moved, modified or removed source files | Complete full-root inventory reconciliation with content verification. |
| New identities or obsolete/missing acoustic features | Measure only those identities; retain current cached features. |
| Existing measurement failures | Report separately; retry only with `--retry-failed`. |
| Schema differs | Explicit existing backed-up migration; refresh cannot silently migrate. |
| Model revision or excerpt policy changed | Recompute affected embeddings on the next explicit AI run. |
| Device profile/converter changed | Existing export receipt checks decide reuse/rebuild. |
| Documentation alone changed | No install or library maintenance. |

File checks enumerate supported audio paths and stat them without reading audio.
Ordinary status does not claim to detect new files without this check. A refresh
always checks the full bound root; a pack directory cannot retire other packs.
One unchanged inventory check is linear in paths without reading audio. A required
inventory reconciliation retains the existing full-content verification guarantee;
device/inode caches are not trusted across hosts. Decoding and feature extraction
reuse existing identity/version caches. Ordinary software/tag refreshes do not scan
or hash audio. This keeps the maintenance increment bounded without weakening the
existing identity contract or adding a second inventory system.

## Refresh and state contracts

`sample-library refresh --root ROOT --json` previews required work without writes.
`--apply` re-evaluates under the existing library lock, retains a state backup
before changes, scans only if needed, synchronises only missing/stale features,
and publishes generated tags with their dependency stamps atomically. The existing
schema's `state_metadata` holds tag recipe and input fingerprints, the feature
version and the originating librarytools release. Legacy unstamped tags are
explicitly unverified and require one regeneration, not a database rebuild.

Tag input fingerprints include active locations, recovered origins and feature
evidence. Tag recipe fingerprints include the role, origin and tagging code and
vocabulary; search-only changes therefore do not invalidate tags. Human tags,
reviews, promotions, picks and saved candidate plans survive refresh. Interrupted
scans cannot retire locations; interrupted features resume by identity. Failed
measurements remain visible and do not cause an endless automatic retry loop.

The existing `sample-tag --apply` records the same stamps, so supported legacy
commands and the maintenance report agree. The new refresh preview is strictly
read-only; this does not silently alter existing move/export safety defaults.

## Search corrections

Use explicit word/compound aliases for musical vocabulary. `hihat`, `hi hat` and
`hi-hat` match HiHat names; `perc` matches percussion independently of the inferred
role. Keep rap separate from Trap/Vibraphone, rim from Grime, house from Warehouse,
and TR-8 from TR808. Preserve intentional processing suffixes and gear aliases.
Restore OHat recognition. Test both desirable matches and nearby false positives.

## Client behaviour

The private studio invokes installed `sample-library` through the same runtime
selection as `sample-find`. Its session check shows release identity, checkout
drift, data freshness, warnings and the exact supported next action. Fresh studio
searches require the supported contract and a ready library. A missing/old client
API gives an installation action; malformed reports or incompatible schemas fail
closed. Optional AI cache work and known measurement failures are warnings rather
than a block on ordinary metadata search. The studio does not reimplement SQL or
tagging. Adding samples means preview/apply refresh, inspect readiness, then select.

## Validation and deployment

Tests cover the condition matrix, legacy stamps, repeat no-op refresh, one added
file, changed/missing files, preserved approvals, preview byte immutability,
interruption/failure, custom vocabulary and client protocol errors. Installed-wheel
checks exercise release identity and refresh outside the checkout. Final release
verification includes relevant suites, full suites once, packaging checks, an
unchanged-library preview, the reviewed live tag refresh, and TR/OT client searches.
Private library evidence remains outside this public repository. Hardware profiles,
source audio, routing and device transfers are outside this change.
