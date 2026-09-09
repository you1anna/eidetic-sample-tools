# Groove and rap audition pilot

> Follow-up: the default editor-first UI was rejected as too complex. The current
> entry point is a single-source chooser with Keep/Skip and a curation shortlist.
> This document records the optional experiment preserved at `/vocal-lab`; see
> [the current pilot guide](../../GROOVE-AUDITION-PILOT.md) for the supported flow.

The first increment tests whether hearing and editing candidates together is useful
before investing in automatic vibe ranking. The agreed brief is hypnotic tribal
underground techno, initially 140 BPM, with short rap chops and occasional phrases.
The listener chooses a groove foundation. Audio stays local; reference tracks guide
future evaluation rather than supplying source audio for this pilot.

## Deliverable

Add an experimental `sample-vibe` command to library-tools. `prepare` takes explicit
anchor and vocal paths under a source root and creates a new audition directory.
`serve` opens a localhost page. Source files and all existing library state remain
unchanged. A session does not require a library database or classifier installation.
Candidate lists are supplied explicitly and labelled as unranked; they are not
represented as model-selected, musically compatible or approved.

The page chooses anchor/vocal candidates, displays waveforms, edits source start/end
times, fits an anchor region to a chosen number of bars, optionally fits the vocal
region to a beat length, and places/repeats that vocal in an eight-bar scene. Tempo
defaults to 140 BPM. The scene uses 4/4. Tempo fitting uses installed FFmpeg atempo;
its perceptual quality requires listening. A natural-speed vocal is the default.
Anchor bar count is a duration-derived proposal, explicitly requiring an ear check.

Render aligned anchor, vocal and mixed WAV previews on demand. Browser playback
uses one Web Audio clock for the aligned layers, with mute controls and common
transport. Editing invalidates the current audition until a new render is ready.
Save `works`, `does_not_work`, or `unsure` feedback, a note and the exact rendered
recipe. The page can reload previous feedback and recipes. This records experiment
feedback only; it cannot create favourites, promote sources or emit export crates.

## Integrity and limits

Each source has a byte hash, path, native sample rate and duration. A preview receipt
records source hashes, native-frame cut bounds, recipe, FFmpeg version, tempo ratios,
output hashes and common attenuation. Render into a temporary directory and publish
only after verifying unchanged sources and completed outputs. Reuse a render only
when its recipe, engine and output hashes match. Source mutation is an explicit error.
Preparation refuses an existing destination or a destination inside the source root.
Sessions use at most 12 candidates per role, each no longer than 120 seconds, to keep
this pilot bounded. No whole-library scan, ML downloads, separation, transcription,
automatic beat-grid claims, export integration or continuous service is included.

Only registered session audio is served; paths are never accepted from browser
requests. Bind to 127.0.0.1, token-protect writes and serialize render/feedback writes.
Audio/source response paths are contained and verified; malformed, nonfinite,
out-of-range recipes fail without producing an accepted preview. Failed render work
does not replace previous previews. Feedback is atomic and tied to a render ID.

## Verification and human evaluation

Use synthetic click trains and tonal fixtures to verify tempo-fitting duration,
approximate pitch preservation, exact scene frame length, vocal placement, fades,
headroom, original hashes and cache validation. Test malformed inputs, source and
output tampering, API token requirements, path containment and feedback persistence.
Run library-tools regression tests and an installed CLI smoke check; inspect the
page in a real browser and exercise render, playback, mute and save/reload.

Measure preparation and cold/warm render times separately. These numbers describe
the pilot only and cannot establish whole-library search performance. Musical value
is pending the listener's session: at least one useful groove/vocal combination,
notes on poor cuts or stretching, and whether the workflow saves audition effort.
No listening result or classification improvement can be asserted by automated tests.

The user is currently on an iPhone remote session. Localhost refers to the Mac;
provide a reproducible launch command and a short Mac listening checklist. Do not
assume that remote Codex exposes the page or audio to the phone.
