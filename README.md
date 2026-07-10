# eidetic-music-tools

Tools for Robin's hardware techno studio (DJ **Eidetic**). They manage the sample
library on the Extreme SSD and prepare curated audio for the **Octatrack MKII**,
**Digitakt MK1**, and **TR-8S**.

Target sound: hypnotic, dub, raw, and hard-groove techno at roughly 130–150 BPM.

## What lives here

| Directory | Status | Purpose |
|---|---|---|
| [`sample-tools/`](sample-tools/) | Built | Profile-aware conversion and sync: Octatrack 44.1 kHz, Digitakt/TR-8S 48 kHz, with validated curated crate TSVs or legacy manifests. |
| [`library-tools/`](library-tools/) | Built | Review, index, classify, de-dupe, and intake samples. Manifest-first: dry-run by default, reversible moves only. Two-zone layout: `CURATED/` (role folders) and `PACKS/` (whole vendor packs). |
| `inbox-sort/` | Folded into `library-tools` | Use `sample-intake` to detect vendor packs dropped at the library root or in `00_INBOX/`, normalise names, and move them into `PACKS/`. Dry-run by default. |
| `inventory/` | Folded into `library-tools` | `sample-review` writes TSV indexes for curation without moving originals. |
| `midi-tools/` | Spec only | Generate techno MIDI (Euclidean patterns, basslines, hats) as `.mid` for Ableton and hardware. Spec: [`docs/superpowers/`](docs/superpowers/) `2026-06-26-midi-generator*`. **Build first.** |
| `ableton-tools/` | Spec only | Read-only Ableton `.als` introspection: tempo, key, samples, missing media, reusable loops. Spec: `2026-06-26-ableton-als-introspection*`. |
| `analysis-tools/` | Spec only | Bounce analysis (LUFS, true peak, spectral, mono compatibility, BPM, key). Feeds `sample-tools` export. Spec: `2026-06-26-bounce-analysis-a1*`. |
| `stem-tools/` | Spec only | `demucs` stem separation (drums, bass, vocals, other) for resampling and vocal sourcing. Spec: `2026-06-26-stem-separation*`. **Build last — heavy.** |

For current project status in plain language, see **[`STATUS.md`](STATUS.md)**.

## Storage and workflow

See **[`docs/STORAGE-AND-WORKFLOW.md`](docs/STORAGE-AND-WORKFLOW.md)** for where files live and how the creative workflow fits together.
The profile, catalogue, curation, and hardware-pilot sequence is documented in
**[`docs/SAMPLE-FOUNDATION-WORKFLOW.md`](docs/SAMPLE-FOUNDATION-WORKFLOW.md)**.

The Extreme SSD is **APFS** and backed up (confirmed 2026-07-07). Device cards stay
exFAT or FAT as required by the hardware. The tooling supports: hardware jam →
Ableton, resample in the Octatrack, finish in Ableton.

## Paths on this machine

| What | Where |
|---|---|
| This repo | `/Users/macmini/Projects/eidetic-music-tools` |
| Sample library (not in git) | `/Volumes/Extreme SSD/Production/SAMPLES/` |

Each tool uses its own Python venv under `~/.venvs/`. See each tool's README for
setup.

## Where to start

- **Export samples to hardware:** [`sample-tools/README.md`](sample-tools/README.md)
- **Review and tidy the library:** [`library-tools/README.md`](library-tools/README.md)
- **Curation without AI:** [`library-tools/README.md#manual-curation-workflow`](library-tools/README.md#manual-curation-workflow) — refresh indexes locally, inspect TSV slices, then bring back small examples when rules need improving
