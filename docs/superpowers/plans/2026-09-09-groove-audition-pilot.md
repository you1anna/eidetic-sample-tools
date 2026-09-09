# Groove Audition Pilot Implementation Plan

> Follow-up: the default editor-first UI was rejected as too complex. The current
> entry point is a single-source chooser with Keep/Skip and a curation shortlist.
> This document records the optional experiment preserved at `/vocal-lab`; see
> [the current pilot guide](../../GROOVE-AUDITION-PILOT.md) for the supported flow.

**Goal:** Ship a bounded local experiment for choosing a loop and hearing editable
rap cuts against it, with repeatable renders and honest listening feedback.

**Architecture:** Explicit input candidates produce an independent audition session.
A pure audio renderer generates aligned WAVs; a small Flask service and Web Audio
page audition them and store feedback. Existing classification and curation stay
separate.

**Tech stack:** Python 3.12, existing NumPy/SoundFile/Flask extras, FFmpeg atempo,
plain browser JavaScript and Web Audio.

**Spec:** ../specs/2026-09-09-groove-audition-pilot-design.md

## Constraints

- Source audio and portable library state are read-only. No profile or safety-default changes.
- Real library files and generated sessions must stay outside the public repository.
- Tests use the package venv; no globally installed Python packages or model downloads.
- Candidate suitability, alignment by ear and stretch quality remain unverified until listening.

## 1. Audio renderer

- [x] Add `vibe_audio.py` and synthetic-audio tests before implementation.
- [x] Export `AudioError(ValueError)`, `probe_source(Path) -> dict`,
  `decode_source(Path) -> numpy.ndarray` (48 kHz stereo float32),
  `validate_recipe(dict, anchor_duration_s, vocal_duration_s) -> dict`,
  `render_audio(anchor_path, vocal_path, recipe, output_dir) -> dict`.
- [x] Recipe fields: bpm, bars (fixed 8), anchor_start_s, anchor_end_s,
  anchor_bars (1/2/4/8), vocal_start_s, vocal_end_s, vocal_fit_beats (0=natural),
  offset_beats, repeat_beats (0=once), anchor_gain_db, vocal_gain_db.
- [x] Validate finite numbers, source bounds, 60–180 BPM, 0.5–2 tempo ratios,
  positive cut lengths, gains -36–0 dB and a complete first vocal event inside
  the scene. Repeat only complete vocal events; require non-overlap.
- [x] Render native-frame cuts with atempo and short fades; repeat the anchor
  to eight bars and place the vocal on the target beat clock. Write equal-length
  48 kHz PCM WAV layers/mix with common peak attenuation. Return processing
  metadata including frame bounds, frame count, tempo ratios and FFmpeg version.
- [x] Verify real FFmpeg output: known duration/pitch, onset position, no clipping,
  unchanged sources, invalid bounds/NaN and unavailable/failed tools.

## 2. Session, API and command

- [x] Add `vibe.py`, `vibe_server.py`, `vibe_cli.py` and integration tests first.
- [x] `prepare_session(root, output_dir, anchors, vocals, bpm=140) -> dict`:
  validate candidates/destination, hash sources, generate browser source previews,
  and atomically write session.json in a new directory. Store waveform peaks.
- [x] `render_preview(session_dir, selection) -> dict`: selection has anchor_id,
  vocal_id and recipe; verify sources, hash engine/recipe into render_id, render
  and publish receipt with outputs, validate cache on every reuse.
- [x] `save_feedback(session_dir, render_id, decision, note) -> dict`: atomic
  append of experiment judgments against validated preview receipts; no promotion.
- [x] API: GET /api/state, POST /api/render, POST /api/feedback,
  GET /source/<id>, GET /audio/<render_id>/<anchor|vocal|mix>. Writes require
  X-Vibe-Token. Responses include receipt ID, audio URLs and recipe. Read source
  bytes and output files only through verified registered paths.
- [x] CLI: `sample-vibe prepare --root PATH --anchor PATH` (repeatable)
  `--vocal PATH` (repeatable) `--output-dir PATH [--bpm 140]`; and
  `sample-vibe serve --session-dir PATH [--port 0] [--open]`.
- [x] Test source/output mutation, invalid sessions/selections, path traversal,
  existing output, serialization, token errors, saved feedback and installed CLI.

## 3. Audition page

- [x] Add packaged `resources/vibe.html`, `vibe.js`, `vibe.css`; consume the
  API contract above. Show unranked candidates and a listening-needed status.
- [x] Provide waveform and numerical boundary controls, anchor bar count,
  natural/fitted vocal length, position/repeat interval and level controls.
- [x] Render on explicit request with busy/error states. Use one AudioContext
  and common scheduled start/loop length, mute via gain nodes, stop old sources
  on stop, render or edits; prevent stale render responses from replacing edits.
- [x] Persist feedback, show recent results and allow loading a previous recipe.
- [x] Validate real browser interaction and record the limits of audio verification.

## 4. Pilot and handoff

- [x] Prepare three plausible groove candidates and a few rap sources from the
  SSD by explicit paths; names supply initial hypotheses only. Keep outputs off-repo.
- [x] Record source hashes and real render/cache timing; no claim of heard quality.
- [x] Run package tests, independent code review and installed command/resource checks.
- [x] Document usage, experimental limitations and a five-minute Mac listening task.
- [x] Deliver a stable local launch command, explain iPhone localhost limitations,
  and identify listening as the next required user interaction.

## Verification result

Implemented in the working tree on 2026-09-09. Final library package run: 523 passed,
15 optional checks skipped. The installed wheel served its page, JavaScript, CSS
and a six-candidate real session. Headless Chrome checks passed at 1440×1100 and
390×844: render/decode, shared audio start/loop length, play/stop, mute, feedback
save/reload, recipe restoration, edit invalidation and delayed-response rejection;
no console errors in the final run. Independent review found no unresolved important
issues after the indirect-input and host-validation fixes.

The real pilot has three groove and three vocal sources, verified unchanged source
hashes, and zero listening judgments. Preparation and first/cached render timings
are in the local session evidence, not a general search benchmark. The QA server
was stopped. A local launcher and listening guide are present in the session.

**Pending human evaluation:** musical suitability, audible cut/stretch quality,
and whether the workflow saves effort. Vibe search and automated matching remain
unimplemented by design until this listening experiment informs the next increment.
