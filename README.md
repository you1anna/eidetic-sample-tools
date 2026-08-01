# Eidetic Sample Tools

Eidetic Sample Tools helps hardware-based electronic musicians organise large
sample libraries, curate trusted collections by ear, and prepare samples for
performance hardware.

It is a personal-first command-line toolkit: built for one working studio today,
but designed so the useful parts can become portable over time.

## What it does

The repository contains three working Python packages:

- **Library tools** index, review, organise, de-duplicate, analyse and curate a
  sample library, and search it by style, type and origin.
- **Sample export** validates and converts approved samples for Octatrack MKII,
  Digitakt MKI and TR-8S.
- **Ableton tools** provide read-only `.als` Set indexing and sample-reference
  reporting. They never edit a Live Set.

The tools support a simple operating model: keep source packs intact, organise a
broad catalogue, promote a small collection by ear, then build device-specific
copies from that trusted collection.

## Why it is safe

The library is more valuable than the software. The tools therefore favour
preview, evidence and recovery:

- Review and analysis commands do not change source audio.
- Commands that can move files default to a preview and require `--apply`.
- Move operations write manifests and undo records.
- Content hashes keep review history attached to the audio when paths change.
- Automated labels remain suggestions. Listening is the final approval step.
- Export writes converted copies; it does not convert source files in place.

Read the full [safety model](docs/SAFETY.md) before applying a move or syncing a
card.

## What works today

| Maturity | Capability |
|---|---|
| **Stable** | Review and index a library; plan reversible sorting, intake and exact de-duplication; convert approved samples for supported hardware; read-only Ableton Set indexing and sample-reference reporting. |
| **Beta** | Portable studio and device profiles; content-hash inventory; pack-origin recovery and tag search; catalogue migration; human-gated curation; profile-aware crate export. These are implemented, but the confidence-organisation work remains unmerged and Foundation v1 is not complete. |
| **Experimental** | Acoustic features, drum-role suggestions, benchmark tooling and conservative near-duplicate research. These produce evidence for review, not autonomous decisions. |
| **Planned** | MIDI generation, bounce analysis and stem separation. Specifications are kept in Git beside the working code. |

The maturity labels describe this project, not a public support guarantee. See
the [roadmap](docs/ROADMAP.md) for their exact meaning.

## Supported hardware

| Device | Export format | Transfer route |
|---|---|---|
| Octatrack MKII | 16-bit WAV, 44.1 kHz, source channel layout preserved | CompactFlash card |
| Digitakt MKI | 16-bit WAV, 48 kHz, mono | Elektron Transfer |
| TR-8S | 16-bit WAV, 48 kHz, mono by default | SD card |

Profiles live in [`profiles/devices/`](profiles/devices/). The current studio
profile is [`profiles/studios/eidetic-studio.toml`](profiles/studios/eidetic-studio.toml).

## Try a safe first run

After installing the library tools, point the review command at a sample
directory:

```bash
sample-review --root /path/to/SAMPLES --no-probe --summary
```

Replace `/path/to/SAMPLES` with your library. This reads filenames and prints a
summary. It does not move, rename, convert or delete audio.

Follow the [getting started guide](docs/GETTING-STARTED.md) for prerequisites,
installation and a first TSV index.

## Documentation

- [Getting started](docs/GETTING-STARTED.md) — install and run a safe review.
- [Workflows](docs/WORKFLOWS.md) — inspect, organise, curate and export.
- [Safety model](docs/SAFETY.md) — understand previews, apply steps and recovery.
- [Library command reference](library-tools/README.md) — every library command.
- [Sample export reference](sample-tools/README.md) — conversion and device transfer.
- [Ableton tools reference](ableton-tools/README.md) — read-only Set and sample-reference inspection.
- [Roadmap](docs/ROADMAP.md) — personal priorities and the path towards a product.

## Research and beta work

Research stays in plain sight:

- [`STATUS.md`](STATUS.md) records the current operational position.
- [`decisions/`](decisions/) records approaches that were adopted, rejected or
  downgraded.
- [`docs/superpowers/specs/`](docs/superpowers/specs/) contains design and audit
  documents.
- [`docs/superpowers/plans/`](docs/superpowers/plans/) contains implementation
  plans.

Failed experiments remain useful evidence. In particular, the current drum-role
classifier is review-only after its first ear calibration failed.

## Project status

The working CLIs and portable profile foundation are implemented, including
read-only Ableton inspection. A 2026-07-18 post-run audit and 2026-07-23
reconciliation verified 18 authorised catalogue moves, but its
confidence-organisation code is not merged and that evidence is not complete
curation or hardware export. The reconciliation also found protected PACKS and
Foundation-label integrity discrepancies that require human recovery review
before promotion or export. See the dated [project status](STATUS.md) for the
recovery sequence and next safe actions.

## Licence

No software licence has been selected. The source is visible for personal
development and review; visibility alone does not grant permission to copy,
modify or redistribute it.
