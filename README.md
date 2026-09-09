# Eidetic Sample Tools

**Find the sound. Build the collection. Play it.**

Bring the samples you already own into your next track or live set. Eidetic
Sample Tools connects musical search, acoustic analysis and careful curation
with validated exports for Octatrack, Digitakt and TR-8S.

Search by role, character or a reference sound. Audition a shortlist. Keep the
sounds that work, then prepare them for the device you play. Three local Python
packages handle the path from archive to performance.

## What you can do

- **Get beyond filenames.** Combine musical tags and pack provenance, or rank
  samples by acoustic similarity. Send results straight to an audition playlist.
- **Make a large library usable.** Recover sample origins, inspect duplicates and
  plan reversible organisation without losing the link to the original audio.
- **Build a collection by ear.** Record favourites and kit selections. Optional
  local AI groups listening candidates; your decisions determine what gets kept.
- **Prepare for hardware.** Validate curated crates, generate compact filenames
  and convert WAV copies with the right sample rate and channel layout.
- **Understand project dependencies.** Read saved Ableton Sets to find their
  tracks, devices and missing sample references without opening Live.

## How it works

![Workflow: index source audio, search by tags and acoustics, audition and label, curate hash-verified favourites, then validate and export for hardware.](docs/assets/workflow.png)

**Content identity connects every stage.** SHA-256 hashes and SQLite link a
sample's locations, features and listening history. Renaming or copying a file
preserves its identity; promotion and crate export recheck the bytes.

**Search has two engines.** Editable TOML rules turn names, origins and measured
features into tags. NumPy signal analysis powers similarity search across
attack, decay, spectrum and dynamics, with no model download required.

**AI supports the listening process.** Two revision-pinned CLAP models compare
audio with text prompts. Cached embeddings make reruns cheaper; a local review
page and benchmark gates control publication of grouped playlists. Audio
processing and inference run locally, with checkpoints downloaded on first use.

Read the [architecture guide](docs/TECHNOLOGY.md) for the algorithms and data model.

## Start here

[Install the tools](docs/GETTING-STARTED.md), then inspect a sample folder:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

This prints a summary without writing files or changing audio. Continue with the
[workflow guide](docs/WORKFLOWS.md) to search, audition and export.

| Package | Focus | Reference |
|---|---|---|
| `library-tools` | Inventory, search, analysis and curation | [Commands](library-tools/README.md) |
| `sample-tools` | Validated WAV export and card transfer | [Devices and formats](sample-tools/README.md) |
| `ableton-tools` | Read-only Live Set inspection | [Reports](ableton-tools/README.md) |

File moves preview by default and require `--apply`; applied moves retain undo
records. Curation and export create copies. Read the [safety model](docs/SAFETY.md)
before applying changes or syncing media.

For installations used over time or across Macs, follow the
[portable library lifecycle guide](docs/LIFECYCLE.md). Install and onboard each Mac
independently; an unavailable machine's history can remain pending. The shared
SSD carries the library database, decisions and recovery records in `.eidetic/`,
so a returning Mac can preserve its older history without replacing newer work.

## Development status

Actively developed. Core review, organisation, conversion and Ableton inspection
are established; search, curation and profile-based crates are beta. AI grouping
and near-duplicate detection remain experimental. Broader library compatibility
and hardware round-trip validation are still adoption gaps.

See the [release notes](CHANGELOG.md) for changes, the
[development guide](docs/DEVELOPMENT.md) for tests and packaging, and the
[roadmap](docs/ROADMAP.md) for priorities. [Decision records](decisions/) retain
research findings. No software licence has been selected.
