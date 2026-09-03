# Sample export tool

## Purpose

`sample-export` prepares approved samples for Octatrack MKII, Digitakt MKI and
TR-8S. It validates a manifest or curated crate, converts each source to the
device format with `ffmpeg`, and stages a copy below `_EXPORT/`.

Source audio is never converted in place. Use `--list` and `--dry-run` before a
real export.

## Install

Follow the portable [getting started guide](../docs/GETTING-STARTED.md), or use
the current personal environment:

```bash
brew install ffmpeg python@3.12
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/sample-tools
~/.venvs/sample-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-sample-tools/sample-tools"
```

This installs the `sample-export` command. The repository also keeps a
`bin/sample-export` shim for the personal setup.

## Supported hardware

| Device | Output | Channels | Transfer |
|---|---|---|---|
| Octatrack MKII | 16-bit WAV, 44.1 kHz | Preserve source mono or stereo | CompactFlash card |
| Digitakt MKI | 16-bit WAV, 48 kHz | Mono | Elektron Transfer |
| TR-8S | 16-bit WAV, 48 kHz | Mono by default; approved `stereo-essential` crate rows preserve stereo | SD card import |

Profile files in [`../profiles/devices/`](../profiles/devices/) are the
versioned authority for these capabilities.

## Preview an export

Set the library location first:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
```

Resolve inputs and output names without conversion:

```bash
sample-export digitakt --list
```

Preview conversion counts:

```bash
sample-export digitakt --dry-run
```

Preview every supported device:

```bash
sample-export --all --dry-run
```

`--list` reports missing patterns and naming warnings. `--dry-run` follows the
conversion path but writes no audio.

## Export a reviewed crate

`sample-curate views` writes versioned TSV crates from complete human labels.
Inspect a crate before conversion:

```bash
sample-export digitakt \
  --profile eidetic-studio \
  --crate ../library-tools/manifests/foundation-v1/foundation-v1-one-shots.tsv \
  --list
```

Preview it:

```bash
sample-export digitakt \
  --profile eidetic-studio \
  --crate ../library-tools/manifests/foundation-v1/foundation-v1-one-shots.tsv \
  --dry-run
```

Run the same command without `--list` or `--dry-run` to write converted copies:

```bash
sample-export digitakt \
  --profile eidetic-studio \
  --crate ../library-tools/manifests/foundation-v1/foundation-v1-one-shots.tsv
```

Each crate row contains `sample_id`, `source_path`, `role`, `descriptor` and
`reason`. Before conversion, the exporter checks the content hash, device
capacity, accepted roles, path depth and compact output names.

Digitakt and TR-8S crates reject long-form roles. Octatrack accepts the full
performance supplement.

## Copy to removable media

Octatrack and TR-8S can receive a built export through a mounted filesystem:

```bash
sample-export octatrack \
  --profile eidetic-studio \
  --crate /path/to/foundation-v1-all.tsv \
  --sync /Volumes/OCTACF
```

`--sync` copies an already converted export after conversion finishes. For
profile crates, hardware-native paths such as `EIDETIC-CURATED/AUDIO/` and
`ROLAND/TR-8S/SAMPLE/` are copied directly to the card root. Legacy flat exports
use an `EIDETIC-<DEVICE>/` wrapper.

When `--crate` is supplied, sync copies only the staged WAVs in that resolved
crate plan. It does not scan the rest of the device staging folder, so other
crates and stale files are excluded. Existing staged outputs that conversion
skips are still included when they belong to the selected crate. Before copying,
the exporter checks every selected staged file and its card destination.

Preview the selected transfer scope without writing converted audio or card
files:

```bash
sample-export tr8s \
  --profile eidetic-studio \
  --crate /path/to/foundation-v1-one-shots.tsv \
  --sync /Volumes/TR8S-SD \
  --dry-run
```

The preview reports the selected crate file count. It does not inspect or create
files on the card.

Digitakt's +Drive is not a mounted disk. Stage the Digitakt export, then drag it
into Elektron Transfer. `--sync` is intentionally unsupported for Digitakt.

TR-8S may still require front-panel import after the files reach the SD card,
depending on its firmware and project state.

## Manifest format

Legacy manifests live at `manifests/<device>.txt`. Entries are relative to
`SAMPLES_ROOT`; absolute paths also work. Blank lines and `#` comments are
ignored.

```text
CATALOGUE/KICKS/Goldbaby-909
CATALOGUE/DRUM-LOOPS/Tribal-Techno/*.wav
CATALOGUE/PERC/conga.wav => conga-hi
```

A directory recurses, a glob selects matching files, and `=>` replaces the
output base name. Supported sources are WAV, AIFF, FLAC, MP3 and OGG. Output is
always WAV.

Curated crate TSVs are preferred for the profile-aware workflow because they
carry identity, role and human-selection evidence.

## Conversion rules

- Existing derived outputs are skipped, making normal exports repeatable.
- `--force` replaces existing derived outputs; it does not touch sources.
- Output names are normalised and de-duplicated.
- Digitakt names warn above 24 characters in legacy exports.
- Digitakt crates enforce the 127-sample project limit.
- TR-8S crates enforce one-shot roles, folder limits and the 600-second user
  sample limit used by the current profile.
- Profile crates use compact names built from role, sequence, descriptor and
  content identity.

## Configuration

| Setting | Default |
|---|---|
| `SAMPLES_ROOT` | `/Volumes/Extreme SSD/Production/SAMPLES` |
| `EXPORT_ROOT` | `<SAMPLES_ROOT>/_EXPORT` |
| `MUSIC_TOOLS_PROFILE` | Not set; use built-in device defaults |
| Local profile file | `~/.config/eidetic-sample-tools/config.toml` |

Select a studio profile with `--profile`, the environment variable, or the
local configuration file. The command-line value wins.

## Safety and troubleshooting

- Start with `--list`, then `--dry-run`.
- A missing `SAMPLES_ROOT` stops the command before planning.
- A changed crate hash stops export before conversion.
- Existing outputs are skipped unless `--force` is explicit.
- A missing sync destination returns an error instead of creating a guessed
  mount path.
- Device exports are derived copies. Rebuild them from the backed-up library and
  retained curation evidence.

Read the complete [safety model](../docs/SAFETY.md) and
[workflow guide](../docs/WORKFLOWS.md) before the first card sync.
