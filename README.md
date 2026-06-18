# eidetic-music-tools

Tooling for Robin's (DJ **Eidetic**) hardware techno studio — managing the sample
library on the Extreme SSD and getting curated, format-correct material onto the
**Octatrack MKII**, **Digitakt MK1**, and **TR-8S**.

Target sound: hypnotic / dub / raw / hard-groove techno (~130–150 BPM).

## Layout

| Dir | Status | What it does |
|---|---|---|
| [`sample-tools/`](sample-tools/) | ✅ built | Convert + sync curated samples to each device's spec (16-bit/44.1 WAV; mono for Digitakt). Manifest-driven CLI. |
| [`library-tools/`](library-tools/) | ✅ built | Manifest-only sample review/indexing by category, loop/one-shot type, BPM, key, tempo fit, plus dry-run classify and de-dupe tools. |
| `inbox-sort/` | planned | Classify/rename new downloads from `SAMPLES/00_INBOX/` into role folders. |
| `inventory/` | folded into `library-tools` for now | `sample-review` emits TSV indexes that drive curation without moving originals. |

## Storage & workflow

See **[`docs/STORAGE-AND-WORKFLOW.md`](docs/STORAGE-AND-WORKFLOW.md)** for the storage
strategy (the SSD should move from exFAT → **APFS** since it's Mac-only; cards stay exFAT;
**backup is the current top priority — there is none yet**) and the creative-workflow vision
the tooling is built to serve (hardware jam → Ableton, resample in the OT, finish in Ableton).

## Note on layout

This repo lives at the **root of the SSD (exFAT for now)**, but Python virtualenvs do **not**
belong on exFAT (no exec bits / symlinks). Each tool's venv lives on the Mac under `~/.venvs/`
and is editable-installed against the source here — and **each machine needs its own venv**.
See each tool's `README.md` for setup.

The library itself lives at `/Volumes/Extreme SSD/Production/SAMPLES/` (not in this
repo) — see its `README.md` for the taxonomy and naming convention.

For low-token, human-run curation steps, start with
[`library-tools/README.md`](library-tools/README.md#low-token-manual-workflow):
refresh the manifest index locally, inspect focused TSV slices, then bring back
small examples/counts when the rules need improving.
