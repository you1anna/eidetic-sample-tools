# Release identity and versioning

A release identifies the package bytes that passed verification. Library status
separately identifies which derived data needs maintenance. Installing a search
correction therefore does not, by itself, require scanning audio or measuring it
again. See [library lifecycle](LIFECYCLE.md) for maintenance and
[development](DEVELOPMENT.md) for source and installed-wheel checks.

## Independent package versions

`librarytools`, `sampletools`, `abletontools` and `eidetic-live-tools` use independent
stable semantic versions (`MAJOR.MINOR.PATCH`). A release can advance librarytools
while leaving the exporter unchanged. This preserves reusable export receipts;
the exporter owns its own conversion version and profile checks.

Every change under a package's source directory, including bundled resources,
requires that package's version to increase before release. Changes to its runtime
`[project]` metadata also require an increase: `requires-python`, `dependencies`,
`optional-dependencies`, `scripts`, `gui-scripts` and `entry-points`. Documentation
outside the package's source directory, descriptive project metadata, build or test
tool configuration, and tests alone do not require a version change. The manifest
itself and generated Python bytecode are excluded from this rule.

Use the repository helper to advance one package and its declared `__version__`
when present:

```bash
python3.12 scripts/release.py bump librarytools minor
```

The final argument accepts `major`, `minor`, `patch` or an explicit higher stable
version. Package directory and import names also work. Exact internal dependency
pins are updated in the other pyprojects when necessary; the helper does not
automatically bump other package versions. If an internal pin changes, also bump
the dependent package because its shipped installation requirements changed.

## Prepare and verify

Complete production edits before preparing the bundled manifest:

```bash
python3.12 scripts/release.py prepare
python3.12 scripts/release.py check
python3.12 scripts/release.py check --base HEAD
```

The final command checks the current working tree against the existing commit;
use the previous release commit when checking work that is already committed.
`--base` accepts a local Git ref and never fetches. CI compares against the pull
request base or the preceding pushed commit. It rejects changed source or resources
and changed runtime project metadata with an unchanged version, even if someone
regenerated the manifest. Version decreases also fail. Metadata comparison reads
the parsed `[project]` values, excluding `[build-system]` and `[tool.*] configuration.

All subcommands accept `--checkout /path/to/eidetic-sample-tools`. `prepare` writes
only [the bundled manifest](../library-tools/src/librarytools/resources/release.json).
`check` is read-only. `bump` edits only package versions and exact internal dependency
pins. None of these commands installs or publishes packages or accesses a library.
Preparing the manifest is not evidence that tests passed: run the focused and
combined suites, then build and verify fresh wheels using the
[development guide](DEVELOPMENT.md#verify-installed-packages).

After verification, commit the release on `main` and identify that commit with an
annotated `<distribution>-v<version>` tag, for example `librarytools-v0.3.0`.
Push `main` and that specific tag. Never move a published release tag: changed
package bytes require a new version. The tag locates the full tested checkout;
the bundled hashes verify the installed package bytes. Git tagging and package
index publication are separate actions; this procedure does not publish to PyPI.

The manifest records each distribution's version, import name, source-directory
name and per-file SHA-256 values. Its deterministic JSON contains no local paths,
timestamps, library data or machine identity. It covers all files under each
package directory except its own `resources/release.json`, `__pycache__` content
and `.pyc`/`.pyo` files. The manifest ships in the librarytools wheel; the other
three wheels remain independently installable without librarytools.

## Inspect an installed release

No mounted sample library is needed:

```bash
sample-library version --json
sample-library version --json --checkout /path/to/eidetic-sample-tools
```

The [runtime inspector](../library-tools/src/librarytools/release_runtime.py)
reads actual loaded package locations and hashes their source and resources. It
does not import optional packages, decode audio, read a database or access the
network. A selected checkout is read directly, including uncommitted changes;
same-version source drift therefore remains visible.

Reports have `contract_version: 1`, a top-level `status`, a `packages` object keyed
by distribution name, an `issues` list of strings and an `actions` list. Each
action contains a stable `id`, a human-readable `reason` and an `argv` array; it
is a proposed command, never executed by inspection. The CLI exits 0 for `ready`,
1 for `action_required` and 2 for `blocked`.

Each package reports `expected_version`, `loaded_version`, `installed_version`,
`source_path` and its status. Source imports use the actual checkout's pyproject
for their loaded version, so unrelated old installed metadata is shown separately.
Installed wheel imports use the metadata at the actual package location. Differences
list `changed_files`, `missing_files` and `unexpected_files`. Selecting a checkout
adds `checkout_version` and `checkout_matches`; the latter is null for packages
that cannot be compared, including absent optional packages.

| Package status | Meaning |
|---|---|
| `verified` | Active bytes and version match the bundled release and any selected checkout. |
| `missing_optional` | An optional package is absent; core library readiness is unaffected. |
| `drift` | Active bytes or version differ; an explicit `install_release` action is required. |
| `unverified` | Required identity or manifest cannot be verified. |

An invalid manifest or selected checkout produces `blocked`. Optional missing
sample/export, Ableton or Live packages do not request installation. Leftover
installed metadata with missing package source does request repair. A malformed
checkout produces no guessed installation target. With a valid selected checkout,
installation actions name its affected package directories. Otherwise they name
the exact manifest versions; supply the tested local wheels or configured package
source when installing releases that have not been published to an index.
Repair commands use `--no-deps` with `--force-reinstall` to preserve the environment's
existing dependencies, including a pinned AI environment. After installation, run
the selected interpreter with `-m pip check`, then rerun `sample-library version`
and `sample-library status` before following any library-maintenance action.

Dependency changes are a separate, explicit environment update. Resolve and test
them with the [core dependency constraints](DEVELOPMENT.md#dependency-ownership-and-updates)
or the [AI dependency snapshot](AI-SETUP.md), as appropriate. A package repair does
not update those dependencies; resolve any `pip check` failures through that tested
environment workflow before proceeding.

Hash verification catches inconsistent installation and checkout drift. The
bundled manifest is a consistency record, not a signature or a defence against
someone deliberately replacing both code and its recorded hashes. Ordinary
inspection reads and hashes the installed source once; audio-library size does
not affect this release check.
