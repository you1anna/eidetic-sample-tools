# Technology and architecture

Discovery, listening and export share a content identity. Each stage produces
inspectable data so the commands can work independently.

[Workflow diagram](../README.md#how-it-works) · [Command workflow](WORKFLOWS.md) ·
[Safety model](SAFETY.md)

## Three packages, explicit boundaries

| Package | Responsibility | Stack |
|---|---|---|
| [`library-tools`](../library-tools/README.md) | Inventory, provenance, search, analysis and curation | Python 3.12+, SQLite, NumPy, SoundFile; optional PyTorch and Flask |
| [`sample-tools`](../sample-tools/README.md) | Resolve crates, validate constraints, convert and stage audio | Python 3.12+, FFmpeg and FFprobe |
| [`ableton-tools`](../ableton-tools/README.md) | Inspect saved Sets and resolve sample references | Python 3.12+ standard-library gzip and XML parsing |

- **Entry points:** each package declares its CLI commands in `pyproject.toml`.
- **Exchange formats:** SQLite data, TSV manifests and labels, JSON review state,
  and M3U8 playlists.
- **Configuration:** TOML holds tag vocabulary, collection targets and device settings.
- **Export boundary:** a crate needs neither `library-tools` nor a database. When
  portable state is present, the exporter validates it and joins its writer protocol.

## Portable state and upgrades

Release 0.2 binds the database to a library UUID under `SAMPLES/.eidetic/`.

### Across machines

- The SSD carries the active database and `.eidetic/runs/` evidence; Python
  environments and models stay on each Mac.
- Each Mac can onboard independently. Usable current state is separate from
  incomplete historical coverage.
- Later databases and human files are captured with content fingerprints in
  state-relative archives. Active SSD decisions stay intact.
- Secondary history remains visible for reconciliation; it never silently
  becomes active approval.

### During writes and upgrades

- Schema 5 records staged scans, feature versions, tag provenance and decision history.
- Historical schemas need explicit, validated migrations and verified backups.
  Opening a database cannot upgrade or relabel it.
- Single-writer locks and durable journals coordinate filesystem and SQLite changes.
- Classifier subprocesses inherit the held lock for embedding-cache writes;
  review sessions keep it until the server exits.
- Read-only diagnostics use settled evidence without creating sidecars.

See the [lifecycle guide](LIFECYCLE.md) for adoption and recovery.

## Identity survives a folder change

The [inventory](../library-tools/src/librarytools/inventory.py) separates a sample
from its locations.

- **Identity:** `sample_id` is the SHA-256 hash of file bytes. Exact copies share
  an identity; re-encoding or changing embedded metadata creates a new one.
- **Locations:** paths, library zones and scans point to that identity.
- **History:** SQLite attaches provenance, features, tags, reviews, promotions and
  kit picks to the bytes. Measurements can be reused across paths.
- **Search:** duplicate collapsing prefers curated locations; crates preserve
  canonical roles and approved descriptions. Promotion and undo update locations.
- **Approval:** generated search crates record active promotion and favourite
  evidence for the exact curated copy. Missing evidence requires review, even for
  files already in `CURATED/` before onboarding.
- **Verification:** promotion preflights the whole selection; promotion and export
  recheck bytes before copying or converting.

A matching hash establishes byte identity. Perceptual similarity is a separate
search problem.

## Search by intent or by sound

### Musical tags

- [Origin recovery](../library-tools/src/librarytools/origin.py) combines surviving
  pack folders, recognised filename tokens and identical copies with known origins.
- [`vocabulary.toml`](../library-tools/vocabulary.toml) maps origins, names and
  measurements to role, style, gear and character tags. Rules can retag without
  modifying audio.
- `sample-find` combines terms with AND; `--any` uses OR.
- Default results spread across filename-derived families to reduce repeated variants.
- `--kit-id` records selections; `--preferred` ranks by those picks.

### Acoustic similarity

For `--like`, [feature extraction](../library-tools/src/librarytools/audiofeatures.py)
decodes with SoundFile and an FFmpeg fallback, then measures:

| Feature group | Measurements |
|---|---|
| Envelope | Attack, tail, duration, leading/trailing silence |
| Dynamics | Peak, RMS, crest factor |
| Spectrum and rhythm | Centroid, flatness, band energy, zero-crossing rate, onset density |

[Ranking](../library-tools/src/librarytools/find.py) uses min-max normalised
Euclidean distance over measurements shared with the reference. No learned
embedding model is required. Results can become playlists or, after promotion,
export crates.

## Optional local AI for listening packets

The classifier separates **form** from **content**:

- **Form:** onset, periodicity, duration and beat rules distinguish one-shots,
  loops and longer sources.
- **Content:** two CLAP audio-language models compare audio embeddings with prompts.
- **Filename influence:** zero decision weight in this ensemble.
- **Scope:** nine groups cover percussion, drum loops, vocal material and
  out-of-brief audio. This remains experimental.

### Model execution and caching

- [Adapters](../library-tools/src/librarytools/classification/models.py) pin
  `laion/clap-htsat-unfused` and `laion/larger_clap_music_and_speech` to explicit revisions.
- PyTorch and Transformers run on CPU; librosa loads 48 kHz mono excerpts from
  bounded positions in longer files.
- Models run sequentially in short-lived workers, releasing memory between runs.
- SQLite caches audio embeddings by sample identity, model, revision and excerpt policy.
- Separate prompt-policy keys let prompt changes reuse audio embeddings.
- Checkpoints download on first use; audio processing and inference stay local.

### Review controls playlist publication

1. Disagreements, weak scores and acoustic boundary cases enter a review queue.
2. Each accepted group contributes a blind sentinel. A failed sentinel opens
   the rest of that group for review.
3. A [local Flask interface](../library-tools/src/librarytools/classification/review_server.py)
   provides playback, decisions, notes, undo and resume on `127.0.0.1`.
4. Atomic JSON state ties decisions to a classification digest. Changed decisions
   withdraw stale publications.
5. Grouped playlists require completed review and a passing 24-row benchmark:
   at least **22 form** and **19 joint content/group** matches.

Those are packet acceptance thresholds, not general accuracy claims.

**Musical approval is separate:** `labels.tsv` must contain validated favourites
with a canonical role and descriptor before promotion.
[Collection roles and quotas](../library-tools/src/librarytools/curation_policy.py)
let a small kit use its own targets without changing hardware profiles.

## Hardware export as a build step

### Validate the input

- A crate records `sample_id`, `source_path`, `role`, `descriptor` and `reason`.
- Generated crates add versioned metadata bound to the TSV hash. Export rejects
  explicit review-required metadata.
- Legacy standalone five-column crates remain compatible as separately reviewed
  inputs; legacy path/glob manifests use a separate planning path.
- The [planner](../sample-tools/src/sampletools/export.py) checks current hashes,
  paths inside `CURATED/`, accepted roles, compact names, and device count or
  duration limits from the resolved configuration.

### Convert and transfer

- FFprobe reads media properties. FFmpeg writes PCM WAV copies to temporary
  files, then renames them after successful conversion.
- Reuse requires matching source, settings, runtime and output hashes in a
  versioned receipt. Rebuilding stale outputs requires `--force`.
- With `--crate`, card sync copies only that crate's planned files, including
  existing staged conversions.
- Digitakt uses Elektron Transfer; Octatrack and TR-8S support mounted-media copying.

See the [export reference](../sample-tools/README.md) for formats and limits.
Playback, assignment and save/reload still need an
[instrument test](WORKFLOWS.md#first-device-smoke-test).

## Saved Ableton Sets as structured data

The [reader](../ableton-tools/src/abletontools/read.py) parses gzip-compressed XML
without running Live.

- **Reports:** tempo, tracks, scenes, devices and sample references.
- **Read-only boundary:** no Set edits or media relinking.
- **Migration preflight:** checks saved Sets for `CURATED` references;
  this is not a complete dependency analysis.
- **Evidence:** report metadata records input hashes, roots, failures and completeness.
  Regeneration archives earlier reports under `.history/`.
- **Incomplete observations:** a missing root or failed parse cannot establish
  that a sample has no project dependencies.

[Verification conventions](../AGENTS.md) · [Roadmap](ROADMAP.md)
