# Getting started

This guide installs Eidetic Sample Tools and runs a first review without changing
audio. Commands use example paths; replace `/path/to/eidetic-sample-tools` and
`/path/to/SAMPLES` with your own locations.

## Before you begin

You need:

- Python 3.12;
- `ffmpeg` and `ffprobe` on your `PATH`;
- a local clone of this repository; and
- a backup of any library you may later reorganise.

On macOS with Homebrew:

```bash
brew install python@3.12 ffmpeg
```

The first review can run against any sample folder. The later profile-aware
workflow currently targets Octatrack MKII, Digitakt MKI and TR-8S.

## Install the library tools

Create one environment for the working packages:

```bash
cd /path/to/eidetic-sample-tools
python3.12 -m venv .venv
.venv/bin/pip install -e "./library-tools"
```

This installs commands such as `sample-review`, `sample-sort`, `sample-curate`
and `sample-analyze`. See the [library command reference](../library-tools/README.md)
for the complete list.

## Install the export tool

Install the exporter into the same environment:

```bash
cd /path/to/eidetic-sample-tools
.venv/bin/pip install -e "./sample-tools"
```

This installs `sample-export`. See the [sample export reference](../sample-tools/README.md)
for device formats and transfer routes.

## Install Ableton inspection when needed

To index saved Live Sets and report their sample dependencies, add the third
package to the same environment:

```bash
cd /path/to/eidetic-sample-tools
.venv/bin/pip install -e "./ableton-tools"
```

This installs `als-index` and `als-samples`. The package uses Python's standard
library and reads saved `.als` files directly, so Live does not need to be running.

## Optional audio classification and browser review

For model-assisted audition grouping and the local review page, install the
library extras:

```bash
cd /path/to/eidetic-sample-tools
.venv/bin/pip install -e "./library-tools[audio-classifier,review-ui]"
```

These add PyTorch, Transformers, librosa and Flask. The two pinned CLAP models
download on first use and run locally on the CPU; allow time and disk space for
that initial setup. Core review, tag search, `--like` acoustic search and device
export use the base packages.

Follow the [curation workflow](WORKFLOWS.md#3-curate-by-ear) to prepare a packet,
classify it and complete its review. The
[technology guide](TECHNOLOGY.md#optional-local-ai-for-listening-packets) explains
the model cache and human review gates.

## Activate the environment

Activate the environment if you want to use commands without the `.venv/bin/`
prefix:

```bash
source .venv/bin/activate
```

## Point the tools at your library

Most library commands accept an explicit `--root`:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

The exporter reads two environment variables:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export EXPORT_ROOT=/path/to/SAMPLES/_EXPORT
```

`EXPORT_ROOT` is optional. Its default is `_EXPORT` inside `SAMPLES_ROOT`.

Portable studio and device profiles live in `profiles/`. Select a studio profile
with `--profile`, `MUSIC_TOOLS_PROFILE`, or a local configuration file:

```toml
# ~/.config/eidetic-sample-tools/config.toml
profile = "eidetic-studio"
```

Profile selection follows this order: command line, environment variable, local
configuration, then the built-in default.

## Run a read-only review

Start with a summary:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

`sample-review` reads paths and filenames. It never moves, renames, converts or
deletes audio. With the command above, it prints counts and writes no files.

To create review material, name the outputs explicitly:

```bash
sample-review \
  --root /path/to/SAMPLES \
  --no-probe \
  --output manifests/review.tsv \
  --index-dir manifests/index
```

This writes TSV files only. It still does not change the sample library.

## Read the output

The main manifest records the source path, proposed role, sample type, explicit
BPM or key evidence, confidence, hardware-friendly name and warnings.

The split index contains focused views:

```text
high-confidence/<ROLE>.tsv
tempo/techno-core.tsv
tempo/techno-adjacent.tsv
tempo/house-lower.tsv
tempo/too-fast.tsv
tempo/unknown.tsv
review-needed.tsv
```

Open these files in a spreadsheet or text editor. Treat every proposal as review
material, not permission to move audio.

## Make the library searchable

Review tells you what is there. To find things by style, type and origin, build the
search index once:

```bash
sample-tag --root /path/to/SAMPLES --rescan --apply
```

This recovers each sample's pack origin, measures its acoustics against the content
hash, and generates tags from [`vocabulary.toml`](../library-tools/vocabulary.toml).
It reads audio but never moves, renames or converts it.

Then search, and audition what comes back:

```bash
sample-find perc tribal analog --root /path/to/SAMPLES \
  --limit 20 --m3u8 manifests/hunt.m3u8
```

Run `sample-tag` without `--apply` to preview vocabulary coverage before replacing
stored tags. Scanning, origin recovery and feature extraction can still update
the derived index and write a proposal; source audio stays in place.

Once a reference sample has measurements, use its ID or a unique path fragment to
rank candidates by sound:

```bash
sample-find --like YOUR_SAMPLE_ID --role PERC --limit 10
```

Replace `YOUR_SAMPLE_ID` with a real indexed sample ID or an unambiguous fragment
of its path. This compares acoustic measurements and requires no model download.
The [search reference](../library-tools/README.md#sample-find) covers filters,
playlists, kit picks and `--curated-only` crates for already promoted favourites.

## Inspect saved Ableton projects

With `ableton-tools` installed, point both reports at a projects directory:

```bash
als-index --root /path/to/ABLETON_PROJECTS --out manifests/ableton
als-samples --root /path/to/ABLETON_PROJECTS --out manifests/ableton
```

These write `als-index.tsv` and `als-samples.tsv`. They report Set structure and
present or missing sample references without editing a Set or its audio. See the
[Ableton reference](../ableton-tools/README.md) for root configuration.

## Choose your next workflow

- Read [Workflows](WORKFLOWS.md) to move from inspection to curation and export.
- Read [Technology and architecture](TECHNOLOGY.md) for the search, data and model implementation.
- Read the [Safety model](SAFETY.md) before using an apply step.
- Check the [Roadmap](ROADMAP.md) to distinguish stable, beta and experimental
  work.

## Robin's current setup

The personal installation uses separate environments rather than the single
portable environment shown above:

| Item | Current location |
|---|---|
| Repository | `/Users/macmini/Projects/eidetic-sample-tools` |
| Sample library | `/Volumes/Extreme SSD/Production/SAMPLES` |
| Python environments | `~/.venvs/library-tools`, `~/.venvs/sample-tools` and `~/.venvs/ableton-tools` |
| Studio profile | `profiles/studios/eidetic-studio.toml` |

These paths are examples, not requirements. The current studio keeps its sample
library on a backed-up APFS SSD; removable hardware media stays in the format
required by each device.
