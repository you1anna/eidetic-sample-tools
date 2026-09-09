# Sample export

**Prepare your selected sounds for Octatrack, Digitakt or TR-8S.**
`sample-export` checks a reviewed crate and uses FFmpeg to create WAV copies
with device-compatible formats and compact names. Source audio stays intact.

## Install

In an activated Python 3.12 environment, from the repository root:

```bash
python -m pip install -e ./sample-tools
```

See [setup](../docs/GETTING-STARTED.md) for Python and FFmpeg installation.

## Export targets

| Device | WAV format | Channels | Transfer |
|---|---|---|---|
| Octatrack MKII | 16-bit, 44.1 kHz | Preserve mono/stereo | CompactFlash card |
| Digitakt MKI | 16-bit, 48 kHz | Mono | Elektron Transfer |
| TR-8S | 16-bit, 48 kHz | Mono; `stereo-essential` crate rows preserve stereo | SD card import |

## Preview, then export

Create a crate from [promoted favourites](../docs/WORKFLOWS.md#3-curate-by-ear).
Resolve its contents and preview conversion:

```bash
export SAMPLES_ROOT=/path/to/SAMPLES
export RUNS="$SAMPLES_ROOT/.eidetic/runs"
sample-export digitakt --root "$SAMPLES_ROOT" --crate "$RUNS/crates/digitakt-kit.tsv" --list
sample-export digitakt --root "$SAMPLES_ROOT" --crate "$RUNS/crates/digitakt-kit.tsv" --dry-run
```

Check the selected files, names and counts. Then write converted copies:

```bash
sample-export digitakt --root "$SAMPLES_ROOT" --crate "$RUNS/crates/digitakt-kit.tsv"
```

Output goes to `$SAMPLES_ROOT/_EXPORT/`. The exporter checks curated paths,
source hashes, roles, name collisions and configured device limits. **Running
without a preview flag writes the export**; there is no `--apply` step.
See the [reference](REFERENCE.md#preview-then-export) for output reuse and `--force`.

## Transfer

Drag Digitakt exports into Elektron Transfer. For Octatrack or TR-8S, preview
copying the selected crate to an existing mounted card:

```bash
sample-export tr8s --root "$SAMPLES_ROOT" --crate "$RUNS/crates/tr8s-kit.tsv" \
  --sync /Volumes/TR8S-SD --dry-run
```

After review, removing `--dry-run` exports and copies the selection to the card.
TR-8S may require front-panel import. Verify a
[one-sample hardware round trip](../docs/WORKFLOWS.md#first-device-smoke-test)
before transferring a larger collection.

[Crate format](REFERENCE.md#crate-format) ·
[Profiles and paths](REFERENCE.md#install-and-configure) ·
[Card transfer details](REFERENCE.md#transfer-to-a-card) ·
[Legacy manifests](REFERENCE.md#legacy-path-manifests) ·
[Safety](../docs/SAFETY.md)
