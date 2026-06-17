# Storage strategy & creative workflow

Context for all future tooling in this repo. Robin (DJ **Eidetic**) runs a hardware
techno studio: **Octatrack MKII** (clock master), **Digitakt MK1**, **TR-8S**, into
**Ableton** on a Mac (mini + MacBook Air M4). Target sound: hypnotic / dub / raw /
hard-groove techno (~130–150 BPM). Everything below is decided unless marked open.

## Storage / format

The Extreme SSD is currently **exFAT**. The drive is **Mac-only** (never needs Windows),
so exFAT is the wrong default. Limitations that matter here:

| Issue | Impact |
|---|---|
| **No journaling** | A bad eject / crash / power loss mid-write can corrupt files or the volume. |
| **No Time Machine** | macOS will not back up an exFAT volume at all. |
| **Slow on huge file counts** | `SAMPLES/` has tens of thousands of files; browse/scan/`ffprobe` sweeps are slower than APFS. |
| **Weak Spotlight indexing** | In-Finder search of the library is unreliable. |
| **No symlinks / exec bits / xattrs** | Breaks venvs, git hooks, Finder tags; spawns `._*` AppleDouble litter. |
| Not a problem | File-size limits (exFAT is fine for large audio); Ableton sessions run okay. |

**Target layout (decided):**
- **Master library + production projects + dev → APFS.** Journaled, Time Machine-able,
  fast, native venvs/git, Spotlight search. This is where creative work and code belong.
- **Device cards (Octatrack CF, Digitakt +Drive, TR-8S SD) → exFAT/FAT** — *required* by
  the hardware. These are built by `sample-tools` export, so they stay disposable/re-syncable.

**Migration path (do in order — destructive, so backup is the gate):**
1. **Back up the SSD first (TOP PRIORITY — there is currently NO backup).** The SSD is the
   only copy of the library + productions. Use a second physical drive (Carbon Copy Cloner
   or `rsync -a`) and/or cloud before touching anything risky.
2. Reformat the SSD to **APFS** (consider APFS Encrypted), restore the data.
3. Enable **Time Machine** for ongoing backups once it's APFS.
4. Until step 2: **always eject cleanly**; avoid heavy in-place edits of live Ableton sets
   off the unbacked exFAT volume.

> Once the SSD is APFS, this repo's venv can live beside the source on the SSD. While it's
> exFAT, the venv must stay on the Mac (`~/.venvs/sample-tools`) — and **each machine needs
> its own venv** (a venv is machine-local). On the Mac mini: `brew install ffmpeg python@3.12`,
> then `python3.12 -m venv ~/.venvs/sample-tools && pip install -e <repo>/sample-tools`.

## Creative workflow (what the tooling should serve)

Primary capture/production paths (confirmed):
- **Hardware jam → Ableton.** Record live jams (OT clock-master + DT + TR-8S) into Ableton,
  multitrack or master.
- **Resample in hardware.** Octatrack used as a live sampler/mangler — capture, mangle, reuse
  in the box during performance.
- **Arrange/finish in Ableton.** Recorded loops/stems arranged, mixed, finished in Ableton.

Vocals (vocal cuts + loops) enter mainly via Ableton and OT resampling rather than pre-chopped
sample packs — so they need to be **easy to find, audition, and drop in live**, not just sorted.

**The goal in one line:** make sampling, live recording, and techno production *dynamic and
easy to play* — the right sound reachable instantly, low-friction, so the setup amplifies
creativity instead of interrupting it.

What that implies for tooling:
- **Fast, well-labelled content.** Consistent naming + BPM/key tags (techno range ~120–150)
  so the Ableton browser and hardware banks are instantly filterable and auditionable.
- **Two consumers, one library.** Optimise for both Ableton drag-and-drop *and* curated,
  format-correct hardware card sets (already handled by `sample-tools`).
- **Close the resample loop.** Good moments from jams/resampling should flow back into the
  library as reusable, named loops/one-shots.

## Tooling roadmap (this repo)

| Tool | Status | Purpose |
|---|---|---|
| `sample-tools/` | ✅ built | Convert + sync curated samples to device specs (mono for DT). |
| `library-tools/` | ✅ built | Manifest-only review/indexing (`main_category`, `sample_type`, explicit BPM/key, tempo fit, proposed names), plus reversible dry-run classify and de-dupe tools. |
| `inventory/` | folded into `library-tools` for now | `sample-review` writes TSV indexes for curation without moving originals; future audio analysis can build on those manifests. |
| `inbox-sort/` | planned | Fast intake of new downloads from `SAMPLES/00_INBOX/` into roles + naming. |
| vocal/loop prep | idea | Trim silence, normalise, BPM/key-tag vocal cuts & loops → clean drops into Ableton + OT. |
| jam/stem intake | idea | Organise + label recorded Ableton jam stems so good moments become reusable library assets. |
| backup | idea | Scripted `rsync`/CCC backup (interim while exFAT; less critical once APFS + Time Machine). |

Open: whether to surface curated favourites into Ableton's User Library / Places for one-click
access (worth exploring once `inventory` exists).
