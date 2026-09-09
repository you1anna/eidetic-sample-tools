# Ableton tools

Inspect a project archive without opening each Live Set. `ableton-tools` reads
saved `.als` files to report Set structure and sample dependencies, helping you
find projects and identify missing media before library changes.

It parses gzip-compressed XML using Python's standard library. Live does not
need to be running; Sets and audio are never edited or relinked.

## Install

From the repository root, in an activated Python 3.12 environment:

```bash
python -m pip install -e './ableton-tools[dev]'
```

See [Getting started](../docs/GETTING-STARTED.md) for environment setup.

## Generate reports

```bash
als-index --root /path/to/ABLETON_PROJECTS --out manifests/ableton
als-samples --root /path/to/ABLETON_PROJECTS --out manifests/ableton
```

| Report | Contents |
|---|---|
| `als-index.tsv` | One row per Set: path, tempo, track count and names, scene count, devices and modification time. |
| `als-samples.tsv` | Sample references by Set, resolved path and present/missing status. |

Malformed Sets are skipped with parse errors reported on stderr. Reports reflect
saved project data and the files accessible during the scan.

## Scan multiple roots

Set `ALS_ROOTS` to a colon-separated list and omit `--root`:

```bash
export ALS_ROOTS=/path/to/active-projects:/path/to/project-archive
als-samples --out manifests/ableton
```

An explicit `--root` takes precedence. Set one of these options to avoid the
legacy machine-specific root defaults.

## Verify

```bash
python -m pytest ableton-tools -q
```
