# Sample export

Prepare a reviewed collection for Octatrack MKII, Digitakt MKI or TR-8S.
`sample-export` resolves a manifest or curated crate, validates the selection and
uses FFmpeg to create device-specific WAV copies. Source audio stays intact.

## Install and configure

From the repository root, in an activated Python 3.12 environment:

```bash
python -m pip install -e ./sample-tools
export SAMPLES_ROOT=/path/to/SAMPLES
```

Install FFmpeg and FFprobe as described in
[Getting started](../docs/GETTING-STARTED.md). Set `SAMPLES_ROOT` explicitly;
the code retains a legacy machine-specific fallback. `EXPORT_ROOT` defaults to
`$SAMPLES_ROOT/_EXPORT`.

Optional profile selection follows `--profile`, `MUSIC_TOOLS_PROFILE`, then
`~/.config/eidetic-sample-tools/config.toml`. Without a selection, the exporter
uses built-in device defaults. See [profile configuration](../docs/SAMPLE-FOUNDATION-WORKFLOW.md).

## Output formats

These are the toolkit's configured export targets:

| Device | WAV format | Channels | Transfer |
|---|---|---|---|
| Octatrack MKII | 16-bit, 44.1 kHz | Preserve mono/stereo | CompactFlash card |
| Digitakt MKI | 16-bit, 48 kHz | Mono | Elektron Transfer |
| TR-8S | 16-bit, 48 kHz | Mono by default; `stereo-essential` crate rows preserve stereo | SD card import |

Versioned capabilities are in [`profiles/devices/`](../profiles/devices/).

## Preview, then export

Create a crate from [promoted favourites](../docs/WORKFLOWS.md#3-curate-by-ear),
then resolve its inputs and preview conversion:

```bash
sample-export digitakt --crate manifests/digitakt-kit.tsv --list
sample-export digitakt --crate manifests/digitakt-kit.tsv --dry-run
```

Confirm the selected files, names and counts before writing the export:

```bash
sample-export digitakt --crate manifests/digitakt-kit.tsv
```

`--list` reports the plan; `--dry-run` writes no audio. Existing staged outputs
are skipped. `--force` replaces derived outputs without touching sources.

## Crate format

A TSV crate carries the selection's identity and context:

| Column | Value |
|---|---|
| `sample_id` | Full SHA-256 of the source file. |
| `source_path` | Path to the promoted copy inside `CURATED/`, relative to `SAMPLES_ROOT` or absolute. |
| `role` | Canonical role, such as `KICK` or `PERC`. |
| `descriptor` | Short description used in the compact output name. |
| `reason` | Selection context or tags; `stereo-essential` enables TR-8S stereo preservation. |

`sample-curate views` generates crates from promoted favourites, with configurable
targets (`--quotas`) and a filename prefix (`--name`).
`sample-find --curated-only --crate FILE` selects from indexed curated paths.

Before conversion, crate validation checks source location, current hash, role
and output-name collisions. Default capacities are 127 samples for Digitakt and
256 files / 600 seconds per TR-8S plan; selected profiles supply these limits.
Both reject long-form roles. Disabled profile devices are rejected. These checks
do not inspect samples already stored on the instrument.

## Transfer to a card

For Octatrack or TR-8S, preview the selected crate's transfer:

```bash
sample-export tr8s --crate manifests/tr8s-kit.tsv \
  --sync /Volumes/TR8S-SD --dry-run
```

The preview reports the selected file count without inspecting or writing the
card. After review, remove `--dry-run` to convert as needed and copy the crate.
The destination must already exist; the exporter checks every selected staged
file and destination before copying.

With `--crate`, sync includes only that plan's WAVs, including staged files whose
conversion was skipped. Native paths such as `EIDETIC-CURATED/AUDIO/` and
`ROLAND/TR-8S/SAMPLE/` are copied directly below the card root. Legacy flat
exports use an `EIDETIC-<DEVICE>/` wrapper.

Digitakt does not support `--sync`; drag staged exports into Elektron Transfer.
TR-8S may require front-panel import after copying. Complete a
[one-sample hardware test](../docs/WORKFLOWS.md#first-device-smoke-test) before
expanding a crate.

## Legacy path manifests

Without `--crate`, the exporter reads this package's `manifests/<device>.txt`:

```text
CURATED/KICK/
CURATED/PERC/*.wav
CURATED/FX/impact.wav => impact-short
```

Directories recurse, globs select files and `=>` sets an output base name.
Paths are relative to `SAMPLES_ROOT` unless absolute; blank lines and `#`
comments are ignored. Sources may be WAV, AIFF, FLAC, MP3 or OGG.

This path does not carry crate identity or curation checks; retain a separately
reviewed source selection. Preview with `sample-export digitakt --list` or
`sample-export --all --dry-run`. Names are normalised and deduplicated; legacy
Digitakt names warn above 24 characters.

Read the [safety model](../docs/SAFETY.md) before export or card sync.
