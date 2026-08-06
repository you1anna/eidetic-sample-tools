# Local audio ensemble and exception review

**Date:** 2026-08-06
**Status:** Approved for implementation

## Problem

The current packet classifier proved that local audio inference is feasible, but it concentrates
domain policy, DSP, CLAP runtime, calibration, TSV persistence, benchmark generation and playlist
publication in one 869-line module. Its single semantic model also leaves too many content labels
uncertain, while the ear benchmark requires Robin to edit TSV rows manually.

The replacement must remove that debt before adding capability. It must run locally on the studio
Mac mini M4 Pro with an effective 23 GB unified-memory budget, preserve source audio, and never
mistake model confidence for musical approval.

## Outcome

`sample-curate` will use two pinned CLAP checkpoints as independent content voters while keeping
form classification acoustic and independent. Strong agreement is resolved automatically. Model
disagreements, weak acoustic boundaries and one blind sentinel per populated category are presented
in a localhost review page that writes the existing audit artefacts for Robin.

The current 63-file `tribal-140-01` packet is the only rollout target. The nine category playlists
remain unpublished until every exception is resolved, every sentinel passes, source identities are
current and the candidate digest matches packet metadata.

## Architecture

The classifier becomes a `librarytools.classification` package with explicit boundaries:

- `domain` owns taxonomy, typed evidence, votes, resolutions and gate results;
- `acoustics` measures independent form evidence and contains no semantic policy;
- `models` adapts pinned audio-language checkpoints behind one embedding interface;
- `cache` stores reusable embeddings by sample identity and exact model/excerpt versions;
- `ensemble` turns acoustic evidence and model votes into candidates and review reasons;
- `packets` owns schemas, atomic persistence, digests and publication state; and
- `review` serves the local UI and applies validated human corrections.

The heavy model runtime executes in a short-lived worker process. Only one model is resident at a
time. It uses inference mode, eight CPU threads and batches of at most eight samples. Embeddings are
stored as 512-dimensional float16 vectors in SQLite and committed per batch, so prompt changes and
interrupted runs do not repeat inference. CPU is the first-rollout backend; MPS remains unqualified.

The model revisions are fixed:

- `laion/clap-htsat-unfused@8fa0f1c6d0433df6e97c127f64b2a1d6c0dcda8a`
- `laion/larger_clap_music_and_speech@195c3a3e68faebb3e2088b9a79e79b43ddbda76b`

PANNs, Qwen/Ollama, Essentia, YAMNet and custom training are not part of this rollout.

## Classification policy

Filename tokens are explanatory evidence only and receive no automatic weight.

Form is auto-resolved only when acoustic evidence clears a conservative rule:

- `LONG_FORM`: duration at least 90 seconds;
- `ONE_SHOT`: duration at most 1 second, no more than two onsets and periodicity below 0.25; or
- `LOOP`: at least four onsets, periodicity at least 0.40, beat confidence at least 0.30 and
  inferred bar-length error at most 5 per cent.

All other boundaries retain a best guess but enter review.

Content is auto-resolved only when both CLAP models choose the same class, each top score is at
least 0.45 and each top-to-second margin is at least 0.08. Disagreement, weak margins,
in-brief/out-of-brief conflicts and structurally implausible form/content pairs enter review.

Every populated auto-accepted audition group contributes one deterministic blind sentinel. If a
sentinel contradicts consensus, all auto-accepted samples in that group are reopened for review.

## Review and persistence

`sample-curate review-packet --labels <packet>/labels.tsv --open` starts a Flask 3.x server bound
only to `127.0.0.1`. It uses a random write token, resolves audio by validated sample ID and supports
HTTP byte ranges without copying audio. The page provides playback, keyboard shortcuts, one-click
form/content choices, notes, undo, progress and resume.

`classification.tsv` and `labels.tsv` retain their existing public schemas. Structured evidence is
written to `classification-audit.jsonl`; resumable choices go to `review-state.json`; the existing
benchmark sheet is regenerated for audit rather than edited manually. Every write is atomic.

Packet metadata schema v3 binds candidate and published state to a canonical digest over source
hashes, feature schema, model revisions, excerpt and prompt policy, classifications and human
resolutions. A failed rerun cannot authorise or invalidate an unrelated published run.

## Safety and acceptance

Classification and review never copy, move, rename, convert or modify source audio. Publication
fails closed on missing dependencies, changed hashes, corrupt cache data, invalid review state,
unresolved exceptions, failed sentinels or digest mismatch. The rejected name-derived playlists are
archived exactly once immediately before the first successful replacement.

The 63-file rollout must demonstrate peak resident memory below 16 GB, a cold run below five
minutes and fully cached rescoring below ten seconds. All playlist paths must be absolute and
playable, every sample must have exactly one group, all regression and integration tests must pass,
and the final branch must receive independent review before integration.
