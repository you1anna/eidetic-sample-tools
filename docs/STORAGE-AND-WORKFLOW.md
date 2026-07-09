# Storage and creative workflow

Context for all tooling in this repo. Robin (DJ **Eidetic**) runs a hardware
techno studio: **Octatrack MKII** (clock master), **Digitakt MK1**, **TR-8S**,
into **Ableton** on a Mac (mini and MacBook Air M4). Target sound: hypnotic,
dub, raw, and hard-groove techno at roughly 130–150 BPM.

Everything below is decided unless marked as open.

## Where files live

The Extreme SSD is **APFS**. Verified 2026-07-07 with
`diskutil info "/Volumes/Extreme SSD"`: APFS, mounted read/write, 2 TB total,
~696 GB free at the time. Robin confirmed the SSD is backed up.

| Location | Format | Role |
|---|---|---|
| `/Volumes/Extreme SSD/Production/SAMPLES/` | APFS | Master sample library and production archive |
| `/Users/macmini/Projects/eidetic-music-tools` | APFS (local disk) | This repo on the Mac mini |
| Octatrack CF, Digitakt +Drive, TR-8S SD | exFAT / FAT | Device cards — built by `sample-tools`, disposable and re-syncable |

**Resolved:** the old "back up before APFS migration" blocker closed 2026-07-07.
Physical sample moves remain review-gated: generate a manifest, inspect it, then
apply only reversible moves with undo manifests.

### Setup on each machine

Each machine needs its own Python venv. On the Mac mini:

```bash
brew install ffmpeg python@3.12
python3.12 -m venv ~/.venvs/<tool>
# editable install against /Users/macmini/Projects/eidetic-music-tools/<tool>
```

See each tool's README for the exact install command.

## Creative workflow

The tooling should support how the studio actually works.

### Primary paths (confirmed)

1. **Hardware jam → Ableton.** Record live jams (Octatrack as clock master,
   Digitakt, TR-8S) into Ableton — multitrack or master.

2. **Resample in hardware.** The Octatrack is a live sampler and mangler:
   capture, process, and reuse in the box during performance.

3. **Arrange and finish in Ableton.** Recorded loops and stems are arranged,
   mixed, and finished in Ableton.

Vocals (cuts and loops) enter mainly via Ableton and Octatrack resampling rather
than pre-chopped packs. They need to be **easy to find, audition, and drop in
live** — not just sorted into folders.

### What we are optimising for

Make sampling, live recording, and techno production **dynamic and easy to
play**. The right sound should be reachable instantly, with low friction, so the
setup amplifies creativity instead of interrupting it.

That implies:

- **Fast, well-labelled content.** Consistent naming plus BPM and key tags
  (techno range ~120–150) so the Ableton browser and hardware banks are
  instantly filterable.

- **Two consumers, one library.** Optimise for both Ableton drag-and-drop and
  curated, format-correct hardware card sets (`sample-tools` handles the latter).

- **Close the resample loop.** Good moments from jams and resampling should flow
  back into the library as reusable, named loops and one-shots.

## Tooling in this repo

| Tool | Status | Purpose |
|---|---|---|
| `sample-tools/` | Built | Convert and sync curated samples to device specs (mono for Digitakt). |
| `library-tools/` | Built | Manifest-only review and indexing, plus reversible dry-run classify, de-dupe, sort, and intake. |
| `inventory/` | Folded into `library-tools` | `sample-review` writes TSV indexes; future audio analysis builds on those manifests. |
| `inbox-sort/` | Folded into `library-tools` | `sample-intake` moves new downloads from `00_INBOX/` into `PACKS/`. |
| Vocal / loop prep | Idea | Trim silence, normalise, BPM/key-tag vocal cuts and loops for Ableton and Octatrack. |
| Jam / stem intake | Idea | Organise and label recorded Ableton jam stems so good moments become library assets. |
| Backup | Resolved / maintain | SSD backed up 2026-07-07; keep ongoing backup checks as maintenance, not a blocker. |

**Open question:** whether to surface curated favourites into Ableton's User
Library or Places for one-click access. Worth exploring once the inventory
workflow is stable.
