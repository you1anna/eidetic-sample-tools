# Technology and architecture

Eidetic Sample Tools is a local pipeline with three independently installable
Python packages. Files and versioned records connect the stages; there is no
central service coordinating the whole workflow.

[User guides](README.md) · [Commands in sequence](WORKFLOWS.md) ·
[State and data contracts](STATE-AND-CONTRACTS.md) · [Development](DEVELOPMENT.md)

## System overview

![System architecture: sample audio passes through library discovery, human curation and device conversion; saved Ableton Sets produce independent reports. Portable library state underpins the sample workflow.](images/architecture.svg)

The diagram shows the search, listening and export path. Saved collection plans
are a separate implemented branch: they freeze candidates and export history,
but do not yet feed the listening interface automatically.

## Package boundaries

| Package | Owns | Runtime and dependencies | Detailed design |
|---|---|---|---|
| `library-tools` | Inventory, metadata, search, collection plans, listening, approval and organisation | Python 3.12; SQLite, NumPy and SoundFile; Flask for browser review; PyTorch/Transformers for local AI | [Library architecture](../library-tools/ARCHITECTURE.md) |
| `sample-tools` | Crate validation, conversion, export receipts and card-copy evidence | Python 3.12 standard library plus FFmpeg/FFprobe executables | [Export architecture](../sample-tools/ARCHITECTURE.md) |
| `ableton-tools` | Saved Set traversal, XML extraction and report history | Python 3.12 standard library | [Ableton architecture](../ableton-tools/ARCHITECTURE.md) |

CLI entry points are declared in each package's `pyproject.toml`. Device and
studio TOML profiles, tag vocabulary and browser assets are bundled with the
packages that use them. Installed-wheel checks exercise the commands outside the
checkout so missing resources cannot hide behind editable installs.

The exporter consumes a crate without importing `library-tools` or requiring its
database. When portable library state is present, it validates compatible state
and participates in the same writer lock. Ableton inspection has no dependency
on either sample package or a running Live process.

## What crosses each boundary

| From → to | Evidence carried forward | What still needs to happen |
|---|---|---|
| Inventory → search or planner | Content identity, current locations, metadata and complete-scan identity | Select useful candidates. |
| Planner → saved revision | Frozen matching population, history coverage, seed, pins and unreviewed choices | A listening handoff; currently a separate step. |
| Audition → curation packet | Kept original identities and paths | Explicit favourite approval, roles and descriptors. |
| Curation → export | Approved copies and a five-column crate; generated crates add approval metadata | Revalidate source bytes and device constraints. |
| Export → card | Verified converted bytes and a copy journal | Instrument playback, assignment and save/reload. |
| Ableton scan → library review | Saved references, input hashes and completeness metadata | Interpret dependencies in the context of available project roots. |

See [State and data contracts](STATE-AND-CONTRACTS.md) for formats, ownership,
path rebinding, locks and interruption handling.

## Local AI for listening packets

Local AI is central to the intended musical-brief workflow. The current model
pipeline groups supplied candidates using acoustic form checks and two pinned
CLAP models. It includes cached embeddings and human review of uncertain results.
It does not yet retrieve a musically coherent set from all indexed audio.

There are currently three distinct selection mechanisms: metadata filtering,
measured acoustic similarity and model-based packet grouping. They have different
inputs and costs; a metadata planner's seeded ordering is not an AI score.
The [library architecture](../library-tools/ARCHITECTURE.md#local-ai-and-review)
explains these mechanisms and their boundaries. [AI setup](AI-SETUP.md) covers
installation and resource controls.

## Where work and waiting occur

| Stage | Main cost | What can be reused |
|---|---|---|
| Inventory | File traversal and reading bytes for content hashes | Unchanged-file hash observations. |
| Audio analysis and AI | Decoding, acoustic measurements, model loading and inference | Versioned features, audio embeddings and prompt embeddings. |
| Collection planning | Reading metadata, sorting candidates, validating and writing a full snapshot | A saved population permits offline regeneration. |
| Listening and approval | Human attention and decisions about musical fit | Saved shortlist and review decisions. |
| Export and transfer | Hash reads, FFmpeg conversion, storage writes and copy verification | Outputs whose receipts still match; matching files already on the card. |
| Ableton reports | Reading/decompressing Sets, XML parsing and checking reference paths | Earlier reports provide history, but each command scans again. |

The [trial](SET-GENERATION-TRIAL.md) separates measured stage timings from estimates.
The [planner benchmark](DEVELOPMENT.md#compare-collection-planner-performance) isolates
metadata planning; it cannot predict model, conversion or listening time.

## Design trade-offs

- **Independent commands:** each stage is inspectable and can be rerun, while
  the user or an assistant still coordinates the end-to-end session.
- **Content identity:** exact copies share history even after moving folders;
  edited tags or re-encoded audio produce a different identity.
- **Local state and inference:** library state travels with its drive; each Mac
  maintains its own Python environment and model files. This is a sequential
  drive-handoff design, not concurrent database synchronisation between machines.
- **Explicit evidence:** a saved candidate, a favourite, a converted file and a
  played instrument sound represent different decisions and checks.
- **Bounded progress:** current scale limitations include full plan snapshots,
  manually supplied audition candidates, model worker timeouts and per-file
  transfer journals. Per-device free-space budgets remain unimplemented.

[Current status](../STATUS.md) records the next bounded work; dated assessments
and experiments remain evidence rather than guarantees about current behaviour.
