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
sample-find perc tribal analog --limit 20 --m3u8 manifests/hunt.m3u8
```

Run without `--apply` first if you want to see what the vocabulary would match before
writing anything.

## Choose your next workflow

- Read [Workflows](WORKFLOWS.md) to move from inspection to curation and export.
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
| Python environments | `~/.venvs/library-tools` and `~/.venvs/sample-tools` |
| Studio profile | `profiles/studios/eidetic-studio.toml` |

These paths are examples, not requirements. The current studio keeps its sample
library on a backed-up APFS SSD; removable hardware media stays in the format
required by each device.
