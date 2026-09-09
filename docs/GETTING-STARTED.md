# Getting started

Install the tools, inspect a folder and turn your first search into a playlist.
Install from the repository root, then run the commands from any directory.
Replace the sample path with the library attached to the current Mac.

## Install

Use Python 3.12 with FFmpeg and FFprobe on your `PATH`. On macOS:

```bash
brew install python@3.12 ffmpeg
```

From your local clone, create an isolated environment on this Mac:

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools"
source "$HOME/.venvs/eidetic-sample-tools/bin/activate"
python -m pip install -e ./library-tools -e ./sample-tools -e ./ableton-tools
```

This combined environment runs the full workflow. The packages are independent;
omit any you do not need, or use separate environments under `~/.venvs/`. Create
and activate an environment separately on each Mac; keep it off the shared SSD.
Set your library path explicitly, since the code retains legacy machine-specific
defaults:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

`RUNS` is a shell variable used by these examples to keep reports, listening
packets and crates with the SSD. Library commands also accept `--root`.
`sample-export --root "$SAMPLES_ROOT"` defaults to that library's `_EXPORT/`;
use `--export-root` for a different staging destination. Without `--root`, the
exporter retains the `SAMPLES_ROOT` and optional `EXPORT_ROOT` environment settings.

## Inspect a folder

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe --summary
```

This reads names and paths, prints counts and writes nothing. To inspect the
proposed roles, sample types, BPM/key evidence and naming warnings in a table:

```bash
sample-review --root "$SAMPLES_ROOT" --no-probe \
  --output "$RUNS/review.tsv" --index-dir "$RUNS/index"
```

Open the TSV in a spreadsheet or text editor. The split index groups results by
role, tempo and review priority. Omit `--no-probe` to enable FFprobe duration
fallback. Source audio stays in place.

## Search and listen

Set up the current Mac independently using [the lifecycle guide](LIFECYCLE.md).
An unavailable older machine does not block this installation. Preview and onboard:

```bash
sample-library onboard --root "$SAMPLES_ROOT" --machine macbook --defer-machine mac-mini
sample-library onboard --root "$SAMPLES_ROOT" --machine macbook --defer-machine mac-mini --apply
```

Use your own machine labels; omit `--defer-machine` when no machine's history is
outstanding. Specify `--library-db` and `--include` for legacy evidence outside the
current checkout. On a returning machine, onboarding captures its older history
without replacing the active SSD database. Historical review stays visible in
`sample-library doctor` while new work can continue.

Build the content-hash inventory, recover pack origins and generate tags:

```bash
sample-tag --root "$SAMPLES_ROOT" --rescan --apply
```

This writes the derived index, including acoustic measurements, without moving
or converting audio. The default database is
`$SAMPLES_ROOT/.eidetic/library.sqlite`. If you supply `--library-db`, use
that same path for subsequent search, analysis and curation commands.

Find a shortlist and write an audition playlist:

```bash
sample-find --root "$SAMPLES_ROOT" perc tribal analog --limit 20 \
  --m3u8 "$RUNS/percussion.m3u8"
```

Compare sounds against an indexed reference:

```bash
sample-find --root "$SAMPLES_ROOT" --like YOUR_SAMPLE_ID --role PERC --limit 10
```

Replace `YOUR_SAMPLE_ID` with a sample ID or a unique path fragment. Similarity
uses measured acoustic features and needs no AI models. See the
[search reference](../library-tools/README.md#sample-find) for filters and kit picks.

To tune the tags, copy [`vocabulary.toml`](../library-tools/vocabulary.toml) to
`$RUNS/vocabulary.toml`, edit it and pass `--vocabulary "$RUNS/vocabulary.toml"`
to `sample-tag`. Omit `--apply` to preview coverage. Scanning and feature extraction
may still update derived data; `--apply` replaces generated tags while retaining
human and unclassified legacy tags.

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
