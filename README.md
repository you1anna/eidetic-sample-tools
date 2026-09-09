# Eidetic Sample Tools

Search your sample library, audition sounds, and export your favourites for
**Octatrack MKII, Digitakt MKI and TR-8S**. Inspect saved Ableton Live Sets to find
projects and missing samples without opening Live.

[Get started](docs/GETTING-STARTED.md) · [Full workflow](docs/WORKFLOWS.md)

## What you can do

| Tool | Functionality |
|---|---|
| [Library tools](library-tools/README.md) | Search by tags or acoustic similarity; audition in a browser; organise packs, stage exact duplicates and curate favourites. |
| [Sample export](sample-tools/README.md) | Check a selected collection against device limits, create WAV copies with compact names, and transfer supported exports to cards. |
| [Ableton tools](ableton-tools/README.md) | Report Set tempo, tracks and devices; list sample references and flag missing media. |

Search uses filenames, pack origins and measured audio features. Optional local
AI suggests groups for listening; your decisions approve the favourites.

## Architecture

![Architecture: sample audio enters library-tools for indexing, search and human curation, with optional local AI suggestions. Approved copies and TSV crates pass to sample-tools for validation and WAV export to Octatrack, Digitakt and TR-8S. Separately, ableton-tools reads saved Live Sets into project and sample-reference reports. Library state travels with the sample drive.](docs/images/architecture.svg)

[Architecture details](docs/TECHNOLOGY.md) · [Open full-size diagram](docs/images/architecture.svg)

## Try it

Follow [setup](docs/GETTING-STARTED.md) for Python 3.12 on macOS or Linux, then
inspect a sample folder:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

This prints a summary without writing files. Continue with
[search and listening](docs/GETTING-STARTED.md#search-and-listen),
[curation](docs/WORKFLOWS.md#3-curate-by-ear), or
[device export](sample-tools/README.md#preview-then-export).

## Before changing audio

Organisation previews moves and requires `--apply`; applied moves retain undo
records. Curation and export create copies. Export writes those copies unless
you pass `--list` or `--dry-run`. Keep a backup and follow the
[safety model](docs/SAFETY.md). For setup on another Mac or recovery, use the
[library lifecycle guide](docs/LIFECYCLE.md).

## Status

Core review, organisation, conversion and Ableton inspection are established.
Search and curation are beta; browser audition, AI grouping and near-duplicate
detection are experimental. Broader library and hardware validation remains open.
No software licence has been selected.

[Roadmap](docs/ROADMAP.md) · [Release notes](CHANGELOG.md) ·
[Development](docs/DEVELOPMENT.md) · [Optional AI setup](docs/AI-SETUP.md)
