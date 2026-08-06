# Local Audio Ensemble and Exception Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the monolithic single-CLAP prototype with a cached dual-CLAP ensemble and a secure exception-only browser review for the current 63-file packet.

**Architecture:** A typed `librarytools.classification` package separates acoustics, model adapters, embedding cache, ensemble policy, packet persistence and review. Heavy checkpoints run sequentially in short-lived CPU workers and persist float16 embeddings in SQLite. Strong consensus is automatic; exceptions and category sentinels are resolved through a localhost UI before guarded playlist publication.

**Tech Stack:** Python 3.12, SQLite, NumPy, librosa, PyTorch, Hugging Face Transformers/CLAP, Flask 3.x, vanilla JavaScript, pytest.

## Global Constraints

- Work only in the existing `codex/category-audition-playlists` linked worktree.
- Do not modify source audio or private studio facts in this public repository.
- Preserve the public schemas of `labels.tsv` and `classification.tsv`.
- Keep the core package light; Flask and ML dependencies remain optional extras.
- Pin both model revisions and include every cache/policy version in the candidate digest.
- Keep peak resident memory below 16 GB by running one model worker at a time.
- Roll out only to `tribal-140-01-audition`; defer full-library classification and extra models.
- Use test-driven development for every production change and run the complete library-tools suite.

---

### Task 1: Freeze behaviour and split domain/persistence debt

**Files:**
- Create: `library-tools/src/librarytools/classification/`
- Modify: `library-tools/src/librarytools/packet_classifier.py`
- Test: `library-tools/tests/test_classification_domain.py`, existing classifier and curate tests

**Interfaces:**
- Produce typed `AcousticEvidence`, `ModelVote`, `CandidateClassification`, `ReviewDecision`, `GateResult` and versioned packet readers/writers.
- Preserve the current imports from `librarytools.packet_classifier` through compatibility re-exports.

- [ ] Add characterization tests for existing TSV schemas, group mapping, gate scoring, benchmark refresh, digest invalidation and transactional publication; run them and confirm the intended failures for new typed interfaces.
- [ ] Create the package and move domain constants/dataclasses, then persistence and benchmark helpers, one red-green cycle at a time.
- [ ] Replace loose benchmark dictionaries with typed records at module boundaries while preserving exact on-disk schemas.
- [ ] Consolidate atomic JSON/TSV writing and remove duplicated benchmark read/refresh logic.
- [ ] Keep `packet_classifier.py` as a compatibility facade and thin orchestration entry point.
- [ ] Run focused tests and the complete suite; commit `refactor(library-tools): split packet classifier boundaries`.

### Task 2: Add versioned embedding cache

**Files:**
- Modify: `library-tools/src/librarytools/inventory.py`
- Create: cache module under `librarytools/classification/`
- Test: `library-tools/tests/test_embedding_cache.py`

**Interfaces:**
- `EmbeddingKey(sample_id, model_id, model_revision, excerpt_policy)`
- `EmbeddingCache.get(key) -> numpy.ndarray | None`
- `EmbeddingCache.put(key, vector) -> None`

- [ ] Write failing tests for an additive schema migration, float16 round-trip, dimension validation, exact revision/excerpt invalidation and corrupt-row rejection.
- [ ] Add the transactional SQLite table with a composite primary key and UTC creation timestamp.
- [ ] Implement typed float16 serialization and strict dimensional validation.
- [ ] Verify old inventory databases migrate without changing existing rows.
- [ ] Run focused and full tests; commit `feat(library-tools): cache versioned audio embeddings`.

### Task 3: Isolate and run the two pinned CLAP adapters

**Files:**
- Create: model adapter and worker modules under `librarytools/classification/`
- Modify: classifier orchestration and optional dependencies
- Test: `library-tools/tests/test_model_workers.py`

**Interfaces:**
- `ModelSpec(model_id, revision, embedding_dimensions=512)`
- `EmbeddingWorker.run(spec, samples, cache, batch_size=8, threads=8) -> WorkerReport`
- `ClapScorer.score(embedding, prompt_embeddings) -> ModelVote`

- [ ] Write failing fake-runtime tests for cache-first operation, batches of eight, per-batch commits, worker failure recovery and strictly sequential model execution.
- [ ] Extract the current CLAP feature/prompt logic behind an adapter and keep real-model imports lazy.
- [ ] Implement the short-lived subprocess worker and structured report without placing vectors on stdout.
- [ ] Pin the current and music/speech model IDs and full revisions; record resolved revisions in packet metadata.
- [ ] Add the second checkpoint without adding PANNs, Essentia, Qwen or Ollama.
- [ ] Run fake-model tests, both real-model smoke tests and the full suite; commit `feat(library-tools): add sequential dual-clap inference`.

### Task 4: Implement independent form and conservative consensus

**Files:**
- Create: acoustic and ensemble policy modules under `librarytools/classification/`
- Modify: classifier orchestration
- Test: `library-tools/tests/test_ensemble_policy.py`

**Interfaces:**
- `classify_form(evidence) -> AxisDecision`
- `resolve_content(votes) -> AxisDecision`
- `build_candidate(sample, evidence, votes) -> CandidateClassification`

- [ ] Write failing tests for all approved numeric form/content thresholds and for filename evidence having zero decision weight.
- [ ] Add onset count and bar-fit error to acoustic evidence without changing cached source identity.
- [ ] Implement independent form best guesses plus explicit review reasons.
- [ ] Implement two-model content agreement using minimum top score 0.45 and margin 0.08.
- [ ] Flag disagreement, weak margin, out-of-brief conflict and implausible form/content combinations.
- [ ] Re-run the known substring, loop, percussion, vocal, long-source and out-of-brief regressions.
- [ ] Run focused and full tests; commit `feat(library-tools): resolve packet classes by conservative consensus`.

### Task 5: Add audit, review queue and sentinel escalation

**Files:**
- Create: packet/audit persistence and review-state modules under `librarytools/classification/`
- Modify: packet metadata handling
- Test: `library-tools/tests/test_packet_review_state.py`

**Interfaces:**
- `classification-audit.jsonl` schema v1 with acoustic evidence, per-model scores, final candidate and review reasons.
- `review-state.json` schema v1 bound to `classification_digest`.
- `ReviewQueue.build(candidates)`, `apply_decision(...)`, `gate() -> GateResult`.

- [ ] Write failing tests for deterministic one-per-group sentinels, exception ordering, digest binding, resume, undo and stale-state rejection.
- [ ] Implement canonical JSON serialization and SHA-256 candidate digests.
- [ ] Build the queue from every exception plus one blind sentinel per populated accepted group.
- [ ] Reopen a whole group when its sentinel contradicts consensus.
- [ ] Regenerate `benchmark-labels.tsv` from review state without requiring direct edits.
- [ ] Make incomplete or stale state fail closed while preserving the last published digest.
- [ ] Run focused and full tests; commit `feat(library-tools): gate packet publication on exception review`.

### Task 6: Build the secure local review UI

**Files:**
- Create: review server/templates under `librarytools/classification/`
- Modify: `library-tools/src/librarytools/curate_cli.py`, optional dependencies and README
- Test: `library-tools/tests/test_review_server.py`

**Interfaces:**
- `sample-curate review-packet --labels PATH [--open] [--port 0]`
- Local routes for queue state, token-protected decisions/undo and sample-ID audio streaming.

- [ ] Write failing Flask-client tests for localhost binding policy, random write token, sample-ID resolution, byte ranges, traversal rejection, decision validation, undo and resume.
- [ ] Add `review-ui = ["flask>=3.1,<4"]` without changing core installation.
- [ ] Implement the server-rendered page and vanilla JavaScript with audio controls, keyboard shortcuts, progress, blind sentinels and visible exception evidence.
- [ ] Persist every decision atomically; never expose arbitrary filesystem paths to request parameters.
- [ ] Keep playlist publication outside the server and behind `sample-curate playlists`.
- [ ] Run focused and full tests; commit `feat(library-tools): add local exception review`.

### Task 7: Qualify, roll out and document

**Files:**
- Modify: public workflow/reference docs and private studio masterplan after successful gate
- Generated local packet artefacts only under `tribal-140-01-audition`
- Test: full suite plus real-model/runtime integration

- [ ] Run cold and cached 63-file classification while recording wall time, peak resident memory, cache hits and exact model revisions.
- [ ] Fail the rollout if cold time is at least five minutes, cached time is at least ten seconds or peak memory is at least 16 GB.
- [ ] Launch the exception review UI and complete the required exception/sentinel queue with Robin; do not fabricate human decisions.
- [ ] Run the gate, archive rejected name-derived playlists once and generate the nine category playlists only after a pass.
- [ ] Audit 63 unique assignments, absolute playable paths, low-confidence ordering and candidate/published digest equality.
- [ ] Run compile checks, all library-tools tests and both pinned-model integrations.
- [ ] Update public docs, then update the private device masterplan with final artefact links and run its mandatory `scripts/sync.sh`.
- [ ] Request independent code review, address findings with TDD, re-run full verification and commit the final changes.
