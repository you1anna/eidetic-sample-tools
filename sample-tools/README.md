# sample-tools

Convert and sync curated samples from the SSD library to **Octatrack MKII**,
**Digitakt MK1**, and **TR-8S**.

Reads a per-device manifest, converts each source to that device's spec with
`ffmpeg`, and stages the result in `SAMPLES/_EXPORT/<DEVICE>/` ready to copy to
a card.

| Item | Path |
|---|---|
| This tool (repo) | `/Users/macmini/Projects/eidetic-music-tools/sample-tools` |
| Sample library | `/Volumes/Extreme SSD/Production/SAMPLES` (APFS SSD) |
| Python venv | `~/.venvs/sample-tools` (per machine) |

## Install

```bash
brew install ffmpeg python@3.12
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/sample-tools
~/.venvs/sample-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/sample-tools"
```

This installs the `sample-export` console script. The repo's `bin/sample-export`
shim calls it (override the venv with `$SAMPLE_TOOLS_VENV`).

## Use

```bash
sx() { ~/.venvs/sample-tools/bin/sample-export "$@"; }   # or: bin/sample-export

sx digitakt --list                       # resolve manifest, show planned files
sx digitakt --dry-run                    # show what would convert
sx digitakt                              # convert → _EXPORT/DIGITAKT/
sx octatrack --sync /Volumes/OCTACF      # convert + copy to CF card
sx --all --dry-run                       # all three devices
```

### Options

| Flag | Effect |
|---|---|
| `--list` | Resolve the manifest and print source → output names and warnings. No conversion. |
| `--dry-run` | Show what would convert without writing files. |
| `--force` | Re-convert even if output already exists (default skips existing = idempotent). |
| `--sync DEST` | Copy the built folder to a mounted card (Octatrack CF, TR-8S SD). |
| `--all` | Run every device. |

## Device specs

All outputs are **16-bit / 44.1 kHz WAV** (`pcm_s16le`).

| Device | Channels | Card sync | Notes |
|---|---|---|---|
| Octatrack | Preserve stereo/mono | Yes (CF card) | Reads WAVs from any folder. |
| Digitakt | **Mono** (`-ac 1`) | No | +Drive is not a disk — use Elektron Transfer. |
| TR-8S | Preserve stereo/mono | Yes (SD card) | May still need on-device Import. |

`--sync` copies into `<DEST>/EIDETIC-<DEVICE>/`.

> **Open item:** community sources suggest the Digitakt's native format may be
> 48 kHz, not 44.1 kHz. Verify on hardware before a large Digitakt export. See
> [`OPERATING-BRIEF-ASSESSMENT.md`](../OPERATING-BRIEF-ASSESSMENT.md).

## Manifests

`manifests/<device>.txt` — one entry per line, resolved relative to
`SAMPLES_ROOT` (absolute paths also work). `#` comments and blank lines are
ignored.

```
KICKS/GR8_001_TUNED_KICKS                          # a folder (recurses)
DRUM-LOOPS/Riemann Kollektion Riemann Tribal Techno 1
DRONE-ATMOS/Analogue Noise/*.wav                   # a glob
PERC/conga.wav => conga-hi                          # rename the output base
```

Source formats `.wav`, `.aif`, `.aiff`, `.flac`, `.mp3`, `.ogg` all decode;
output is always `.wav`. Seed manifests pull whole packs as a starting point —
run `--list` and trim to the exact files you want on each device.

## Environment overrides

| Variable | Default |
|---|---|
| `SAMPLES_ROOT` | `/Volumes/Extreme SSD/Production/SAMPLES` |
| `EXPORT_ROOT` | `<SAMPLES_ROOT>/_EXPORT` |

## Source layout

```
src/sampletools/  config.py probe.py naming.py convert.py export.py cli.py
manifests/        octatrack.txt digitakt.txt tr8s.txt
bin/sample-export shim
```
