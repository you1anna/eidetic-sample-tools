# Getting started

Install the tools, inspect a folder and turn your first search into a playlist.
Examples run from the repository root; replace the sample path with your own.

## Install

Use Python 3.12 with FFmpeg and FFprobe on your `PATH`. On macOS:

```bash
brew install python@3.12 ffmpeg
```

From your local clone, create an isolated environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e ./library-tools -e ./sample-tools -e ./ableton-tools
```

The packages are independent; omit any you do not need. Set your library path
explicitly, since the code retains legacy machine-specific defaults:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
```

Library commands also accept `--root`. Converted exports default to
`$SAMPLES_ROOT/_EXPORT`; set `EXPORT_ROOT` to use another destination.

## Inspect a folder

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe --summary
```

This reads names and paths, prints counts and writes nothing. To inspect the
proposed roles, sample types, BPM/key evidence and naming warnings in a table:

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe \
  --output manifests/review.tsv --index-dir manifests/index
```

Open the TSV in a spreadsheet or text editor. The split index groups results by
role, tempo and review priority. Omit `--no-probe` to enable FFprobe duration
fallback. Source audio stays in place.

## Search and listen

Build the content-hash inventory, recover pack origins and generate tags:

```bash
sample-tag --root "$SAMPLES_ROOT" --rescan --apply
```

This writes the derived index, including acoustic measurements, without moving
or converting audio. The default database is
`library-tools/manifests/sample-library.sqlite`. If you supply `--library-db`, use
that same path for subsequent search, analysis and curation commands.

Find a shortlist and write an audition playlist:

```bash
sample-find perc tribal analog --limit 20 --m3u8 manifests/percussion.m3u8
```

Compare sounds against an indexed reference:

```bash
sample-find --like YOUR_SAMPLE_ID --role PERC --limit 10
```

Replace `YOUR_SAMPLE_ID` with a sample ID or a unique path fragment. Similarity
uses measured acoustic features and needs no AI models. See the
[search reference](../library-tools/README.md#sample-find) for filters and kit picks.

To tune the tags, edit [`vocabulary.toml`](../library-tools/vocabulary.toml) and
run `sample-tag` without `--apply` to preview coverage. Scanning and feature
extraction may still update derived data; only `--apply` replaces stored tags.

## Optional listening assistant

```bash
python -m pip install -e './library-tools[audio-classifier,review-ui]'
```

This adds PyTorch, Transformers, librosa and Flask for audio-based grouping and
browser review. The two pinned CLAP checkpoints download on first use and run
locally on the CPU. Follow the [curation workflow](WORKFLOWS.md#3-curate-by-ear)
to use them.

## Next steps

- [Workflows](WORKFLOWS.md): organise, approve favourites and export a crate.
- [Export reference](../sample-tools/README.md): device formats and transfer.
- [Ableton reports](../ableton-tools/README.md): inspect Sets and sample dependencies.
- [Architecture](TECHNOLOGY.md): understand identity, search and model review.

Before moving audio, read the [safety model](SAFETY.md) and verify your library
backup. [Configuration details](../library-tools/README.md#profiles) cover the
bundled profile and selection order.
