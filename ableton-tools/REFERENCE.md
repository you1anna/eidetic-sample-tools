# Ableton tools reference

[← Ableton tools](README.md)

Inspect a project archive without opening each Live Set. `ableton-tools` reads
saved `.als` files to report Set structure and sample dependencies, helping you
find projects and identify missing media before library changes.

It parses gzip-compressed XML using Python's standard library. Live does not
need to be running; Sets and audio are never edited or relinked.

## Install

From the repository root, in an activated Python 3.12 environment:

```bash
python -m pip install -e ./ableton-tools
```

See [Getting started](../docs/GETTING-STARTED.md) for environment setup.
Install independently on each Mac that needs to inspect saved Sets; the other
machine need not be online. Reports can only account for roots available during
that run.

## Generate reports

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
als-index --root /path/to/ABLETON_PROJECTS --out "$RUNS/ableton"
als-samples --root /path/to/ABLETON_PROJECTS --out "$RUNS/ableton"
```

These examples keep dependency evidence with the sample SSD. `--out` is explicit:
choose another backed-up report directory when using Ableton tools independently
of a sample library. `--root` always selects the Ableton project tree to inspect,
not the sample library used here for report storage.

| Report | Contents |
|---|---|
| `als-index.tsv` | One row per Set: path, tempo, track count and names, scene count, devices and modification time. |
| `als-samples.tsv` | Sample references by Set, resolved path and present/missing status. |

Malformed Sets are skipped with parse errors reported on stderr. Reports reflect
saved project data and the files accessible during the scan.

Each TSV has a `.metadata.json` sidecar recording input Set hashes, report hash,
run time, roots and failures. `complete: false` means the report is an incomplete
observation. Earlier reports are retained under `.history/` when regenerated.
Report generation preserves the existing exit behaviour; inspect completeness
and stderr before using a report as dependency evidence.

## Scan multiple roots

Set `ALS_ROOTS` to a colon-separated list and omit `--root`:

```bash
export ALS_ROOTS="/path/to/active-projects:/path/to/project-archive"
als-samples --out "$RUNS/ableton"
```

An explicit `--root` takes precedence. One of these options is required;
omitting both fails before creating reports. Sample-library `SAMPLES_ROOT` is
not used for Ableton project selection.

## Verify

```bash
python -m pip install -e './ableton-tools[dev]'
python -m pytest ableton-tools -q
```
