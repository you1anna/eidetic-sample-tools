# Technology and architecture

Eidetic Sample Tools connects sample discovery, listening decisions and hardware
preparation through a shared content identity. Its value comes from keeping those
steps connected: a sound can be found, auditioned, selected, copied and exported
with evidence of what happened at each stage.

For commands and operating steps, start with [Getting started](GETTING-STARTED.md)
and [Workflows](WORKFLOWS.md). The [safety model](SAFETY.md) defines the mutation
gates; this guide explains the implementation behind them.

## Three packages, one workflow

| Package | Responsibility | Runtime dependencies |
|---|---|---|
| [`library-tools`](../library-tools/README.md) | Inventory, filename review, organisation, provenance, search, acoustic features, curation and research. | Python 3.12+, NumPy and SoundFile; FFmpeg/FFprobe for decoding fallback and probes. Optional model and review extras are separate. |
| [`sample-tools`](../sample-tools/README.md) | Manifest resolution, crate validation, output naming, conversion and card-copy planning. | Python 3.12+ and FFmpeg/FFprobe. Its core declares no third-party Python dependencies. |
| [`ableton-tools`](../ableton-tools/README.md) | Read saved Live Sets and resolve their sample references. | Python 3.12+ standard library: gzip, XML, paths and TSV output. |

The packages expose individual command-line programs through their
`pyproject.toml` entry points. They exchange inspectable files: SQLite databases,
TSV manifests and labels, JSON review state and M3U8 audition playlists. The
exporter consumes a crate TSV rather than requiring a live connection to the
library database. Studio and device settings are versioned TOML files under
[`profiles/`](../profiles/).

## Content identity keeps the workflow connected

The [inventory](../library-tools/src/librarytools/inventory.py) separates an
**asset** from its **locations**. An asset's `sample_id` is the SHA-256 hash of the
file bytes; locations record where those bytes were observed, their library zone
and the scan that saw them. Renaming or making an exact copy keeps the identity.
Changing the file bytes, including re-encoding or editing embedded metadata,
creates a different identity.

SQLite stores scan history, assets and locations alongside origins, acoustic
features, tags, reviews, promotions and kit picks. This lets an exact copy inherit
known provenance and lets listening records refer to a sound independently of a
particular folder layout. Acoustic measurements are stored per content identity
so the same sample can be reused across searches.

The file hash has a specific purpose: it proves byte identity. Similar-sounding
encodings are not exact duplicates. Promotion and profile-aware crate export
recompute the source hash before copying or converting, so an old decision cannot
silently select changed bytes at the same path.

Key modules: [inventory](../library-tools/src/librarytools/inventory.py),
[feature storage](../library-tools/src/librarytools/features.py),
[curation](../library-tools/src/librarytools/curate.py) and
[promotion checks](../library-tools/src/librarytools/promotion_health.py).

## Two complementary ways to find a sound

### Search by intent and provenance

`sample-tag` recovers pack origin from surviving folders, recognised filename
tokens and identical copies with known provenance. It then evaluates the rules
in [`vocabulary.toml`](../library-tools/vocabulary.toml) to build searchable tags.
Rules can use origin, names and measured features. A vocabulary change can
regenerate tags across the library without editing individual audio files.

`sample-find` combines terms and filters for role, style, gear, character and
origin. Terms are ANDed by default; `--any` broadens the match. Default results
spread across filename-derived sound families to reduce repeated variants of one
hit. `--kit-id` records the returned selection, and `--preferred` can rank future
results by those recorded picks. Picks are a retrieval signal; promotion still
requires listening decisions.

### Search by measured sound

When many variants share the same pack and tags, `sample-find --like` can rank
them against an indexed reference sample. The reference can be a sample ID or an
unambiguous path fragment.

[Acoustic extraction](../library-tools/src/librarytools/audiofeatures.py) uses
SoundFile with an FFmpeg fallback, then NumPy signal processing. Measurements
include duration, peak and RMS level, crest factor, attack and tail, leading and
trailing silence, spectral centroid and flatness, frequency-band energy ratios,
onset density and zero-crossing rate.

[Similarity ranking](../library-tools/src/librarytools/find.py) uses min-max
normalised Euclidean distance over the available shared measurements. It is an
inspectable feature comparison. The CLAP models described below belong to the
separate packet-classification workflow and are not required for `--like`.

Search can write M3U8 playlists for audition or TSV crates for the exporter.
`--curated-only` restricts a selection to the `CURATED/` zone; the exporter checks
that each crate source resolves inside that zone and still matches its hash.

Key modules: [origin recovery](../library-tools/src/librarytools/origin.py),
[tag rules](../library-tools/src/librarytools/tagging.py),
[search](../library-tools/src/librarytools/find.py) and
[search CLI](../library-tools/src/librarytools/find_cli.py).

## Optional local AI for listening packets

`sample-curate classify-packet` suggests groups for an audition packet. It keeps
two questions separate:

- **Form:** Is this a one-shot, loop, phrase or long-form source? Acoustic rules
  use duration, onsets, periodicity and beat/bar evidence.
- **Content:** Does the audio resemble a rim, tom, percussion, full drums, vocals
  or material outside the current brief? Two CLAP audio-language models compare
  audio embeddings with written content prompts.

The current brief produces nine audition groups spanning percussion and vocal
material plus an out-of-brief group. This is a focused listening aid, with
experimental classification quality; it is not a general musical taxonomy.
Filename text has zero decision weight in the current ensemble.

### Model execution and reuse

The [model adapters](../library-tools/src/librarytools/classification/models.py)
pin `laion/clap-htsat-unfused` and `laion/larger_clap_music_and_speech` to specific
revisions. PyTorch and Hugging Face Transformers run inference on the local CPU;
librosa loads 48 kHz mono excerpts. Long sources use bounded excerpts from the
start, middle and end rather than requiring a whole-track model input.

The models run sequentially in short-lived worker processes. Bounded batches
limit the working set, and ending a worker releases its model memory. SQLite
caches audio embeddings by sample identity, model ID, model revision and excerpt
policy. Prompt embeddings have their own policy key, so prompt tuning can reuse
the existing audio embeddings.

First use downloads the pinned checkpoints. Audio decoding, embedding generation
and scoring happen locally. The base packages work without installing the heavy
`audio-classifier` extra; the older optional CNN-LSTM drum experiment uses a
different `classifier` extra and user-supplied weights.

### Human review controls publication

Model disagreement, weak scores and acoustic boundary cases enter an exception
queue. Each accepted group also contributes a blind sentinel: a sample heard
without showing the predicted answer. A failed sentinel opens the rest of its
group for review.

`sample-curate review-packet` serves a Flask page on `127.0.0.1` with playback,
form/content choices, notes, undo and resume. Review state is written atomically
and tied to a classification digest. Explicit `--carry-review` can retain human
decisions by sample identity during a tuning rerun.

Grouped playlists publish only when the queue is complete and the 24-sample
benchmark reaches at least 22 correct form matches and 19 joint content/group
matches. Those are acceptance thresholds for that reviewed packet, not a claim
of general model accuracy. Changing completed decisions or reclassifying a
packet withdraws stale publications until the current evidence passes again.

The final musical decision remains in `labels.tsv`: reject, keep or favourite.
Only favourites with a complete validated label set, canonical role and
descriptor can be promoted into `CURATED/`.

Key modules: [packet orchestration](../library-tools/src/librarytools/packet_classifier.py),
[ensemble](../library-tools/src/librarytools/classification/ensemble.py),
[workers](../library-tools/src/librarytools/classification/workers.py),
[embedding cache](../library-tools/src/librarytools/classification/cache.py),
[review state](../library-tools/src/librarytools/classification/review.py) and
[local UI](../library-tools/src/librarytools/classification/review_server.py).

## Device-aware copies and transfer plans

`sample-export` accepts legacy path/glob manifests or profile-aware curated crate
TSVs. A crate carries `sample_id`, `source_path`, `role`, `descriptor` and `reason`.
The curated workflow checks source location and hash, supported roles, project
or folder capacity, aggregate duration where applicable and compact output names.
The exact checks live in the [crate planner](../sample-tools/src/sampletools/export.py).

FFprobe reads media properties; FFmpeg creates PCM WAV copies with the selected
sample rate and channel policy. Conversion writes a temporary output and renames
it after success. Existing derived outputs are skipped unless `--force` is used.
The [export reference](../sample-tools/README.md) documents each device format and
the distinction between legacy manifests and curated crates.

`--list` resolves inputs, and `--dry-run` previews conversion. Running without
those flags writes the export. For Octatrack and TR-8S, explicit `--sync` copies
to mounted media; with `--crate`, the transfer includes only that crate's planned
files, including matching staged outputs that conversion skipped. Digitakt
exports are staged for Elektron Transfer.

The exporter checks software-visible constraints. Audible playback, assignment,
save and reload on the instrument remain a separate hardware smoke test in the
[workflow guide](WORKFLOWS.md#first-device-smoke-test).

## Ableton inspection without a Live session

Ableton `.als` Sets contain gzip-compressed XML. The
[reader](../ableton-tools/src/abletontools/read.py) uses Python's standard library
to inspect that saved structure directly. `als-index` reports tempo, track names
and counts, scene count and device names; `als-samples` resolves sample references
and reports present or missing media.

The library's catalogue-migration preflight also inspects saved Set references
before proposing path changes. These reports help identify dependencies; the
tools never edit a Set or relink its media.

## Development and extension points

- Tune searchable vocabulary in [`library-tools/vocabulary.toml`](../library-tools/vocabulary.toml).
  Tag rules are inspectable and can be previewed before replacing stored tags.
- Review device capabilities in [`profiles/devices/`](../profiles/devices/).
  Profiles mirror hardware constraints; changing one requires explicit review
  and does not by itself implement a new device's export or transfer behaviour.
- Inspect classification prompts, model pins and benchmark policy in
  [`classification/`](../library-tools/src/librarytools/classification/).
  Policy changes must pass the listening and publication gates again.
- Use TSV and JSON outputs to inspect evidence or connect another local workflow.
  Preserve content identities and human decisions when doing so.

Each package has pytest coverage. From the repository root, the personal
development environments run:

```bash
~/.venvs/library-tools/bin/python -m pytest library-tools -q
~/.venvs/sample-tools/bin/python -m pytest sample-tools -q
~/.venvs/ableton-tools/bin/python -m pytest ableton-tools -q
```

See [AGENTS.md](../AGENTS.md) for repository conventions and verification commands.
The [roadmap](ROADMAP.md) distinguishes implemented features from experiments and
planned MIDI generation, bounce analysis and stem separation. The dated
[status record](../STATUS.md) tracks evidence from the personal library; it is
separate from a general compatibility or performance guarantee.
