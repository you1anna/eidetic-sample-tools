# Ableton tools

**Find saved Live Sets and check their sample dependencies without opening Live.**
Read `.als` files to see tracks, devices and missing media before reorganising
an archive or changing sample-library paths. Sets and audio are never edited.

## Install

In an activated Python 3.12 environment, from the repository root:

```bash
python -m pip install -e ./ableton-tools
```

See [setup](../docs/GETTING-STARTED.md) for the Python environment.

## Generate reports

Choose the project tree to inspect and a directory for the reports:

```bash
als-index --root /path/to/ABLETON_PROJECTS --out /path/to/reports
als-samples --root /path/to/ABLETON_PROJECTS --out /path/to/reports
```

| Report | What it tells you |
|---|---|
| `als-index.tsv` | Each Set's tempo, tracks, scenes, devices and modification time. |
| `als-samples.tsv` | Each Set's sample references, resolved paths and present/missing status. |

Reports reflect saved Sets and files accessible during the scan. Malformed Sets
are skipped with errors on stderr. Check each report's `.metadata.json` sidecar:
`complete: false` means the scan is incomplete. Earlier reports remain in `.history/`.

`--root` selects Ableton projects. To scan several project trees, use
[`ALS_ROOTS`](REFERENCE.md#scan-multiple-roots) instead.

[Report metadata and storage](REFERENCE.md#generate-reports) ·
[Development checks](REFERENCE.md#verify) ·
[Full reference](REFERENCE.md)
