# Getting started

Install the tools, inspect a folder and turn your first search into a playlist.
Install from the repository root, then run the commands from any directory.
Replace the sample path with the library attached to the current Mac.

## Install

The documented platforms are macOS and Linux with Python 3.12. Library locking
uses Unix `flock`; native Windows is not supported. CI tests Python 3.12 on both
platforms, even though package metadata allows newer Python versions.

Use Python 3.12 with FFmpeg and FFprobe on your `PATH`. On macOS:

```bash
brew install python@3.12 ffmpeg
```

Clone the repository if needed, then create an isolated environment on this Mac:

```bash
git clone https://github.com/you1anna/eidetic-sample-tools.git
cd eidetic-sample-tools
```

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools"
source "$HOME/.venvs/eidetic-sample-tools/bin/activate"
python -m pip install -e ./library-tools -e ./sample-tools -e ./ableton-tools
python -m pip check
```

Editable installs use this checkout directly: keep it in place. For an installation
that does not depend on keeping the checkout, omit each `-e`. Install from this
repository; the source release is not a promise of availability on a package index.

This combined environment runs the full workflow. The packages are independent;
omit any you do not need, or use separate environments under `~/.venvs/`. Create
and activate an environment separately on each Mac; keep it off the shared SSD.
Set your library path explicitly. Commands require `--root` or `SAMPLES_ROOT`;
there is no machine-specific fallback:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
```

`RUNS` is a shell variable used by these examples to keep reports, listening
packets and crates with the SSD. Library commands also accept `--root`.
`sample-export --root "$SAMPLES_ROOT"` defaults to that library's `_EXPORT/`;
use `--export-root` for a different staging destination. Without `--root`, the
exporter retains the `SAMPLES_ROOT` and optional `EXPORT_ROOT` environment settings.

### Check the installation

```bash
python --version
python -m pip show librarytools sampletools abletontools
sample-review --help
sample-export --help
als-index --help
ffmpeg -version
ffprobe -version
```

In each new terminal, activate the environment again and set the current
`SAMPLES_ROOT`. `command not found` usually means the environment is not active;
`No module named ...` means the selected Python does not have that package.
Use `python -m pip` in the active environment when installing. FFmpeg/FFprobe are
system executables and are not installed by pip. Base Ableton inspection needs
neither; export needs both. On Linux, install FFmpeg through the system package
manager; if SoundFile cannot load libsndfile, install that system library too
(`libsndfile1` on Debian/Ubuntu).

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

For a tested, reinstallable AI environment on an Apple Silicon Mac, use the
[pinned AI setup](AI-SETUP.md). It includes an explicit model download and an
offline check, plus guidance for large libraries. Ordinary commands need no models.

Browser audition alone needs only the small review extra:

```bash
python -m pip install -e './library-tools[review-ui]'
```

For model-based grouping as well:

```bash
python -m pip install -e './library-tools[audio-classifier,review-ui]'
```

This unpinned development alternative adds PyTorch, Transformers, librosa and Flask for audio-based grouping and
browser review. The two pinned CLAP checkpoints download on first use and run
locally on the CPU. Follow the [curation workflow](WORKFLOWS.md#3-curate-by-ear)
to use them.

## Updating an installation

Before changing releases, stop library writers and follow the
[backup and upgrade procedure](LIFECYCLE.md#inspect-before-upgrading). Record
`git rev-parse HEAD` and `python -m pip freeze` outside the checkout so the previous
code revision and dependency versions can be identified. An editable installation
changes when its checkout changes.

After selecting the intended revision, rerun the installation command, including
any optional extras you use, and `python -m pip check`. Run
`sample-library doctor --root "$SAMPLES_ROOT" --json` before writing library data.
Package installation does not migrate the database; use the explicit lifecycle
commands when an upgrade is needed. Do not downgrade tools against a newer live
schema; rehearse recovery using a separate restored backup.

## Next steps

- [Workflows](WORKFLOWS.md): organise, approve favourites and export a crate.
- [Export reference](../sample-tools/README.md): device formats and transfer.
- [Ableton reports](../ableton-tools/README.md): inspect Sets and sample dependencies.
- [Architecture](TECHNOLOGY.md): understand identity, search and model review.

Before moving audio, read the [safety model](SAFETY.md) and verify your library
backup. [Configuration details](../library-tools/README.md#profiles) cover the
bundled profile and selection order.
