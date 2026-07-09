# Operating brief assessment

Date: 2026-06-25 (desk review). Updated notes: 2026-07-09.

Robin produced an **Eidetic Studio — Claude Code Operating Brief**: a tiered automation
plan for the Mac mini studio covering bounce analysis, sample prep, Ableton MCP
scaffolding, an Extensions SDK Set auditor, and MIDI generation. This document
records how that brief compares to what already exists in this repo.

**Purpose:** stop a future session — especially one on the Mac mini with the SSD
attached — from re-deriving this assessment or rebuilding work that is already done.

**Scope:** desk review only. The original assessment had no access to the SSD,
Ableton, or studio hardware. It compared the brief against this repo's code,
tests, and docs, plus `command-center` cross-repo tracking. It is not a
hands-on verification.

For current project status, see **[`STATUS.md`](STATUS.md)**.

## Bottom line

The brief is well calibrated but was written without visibility into this repo.

- **Tier A2 ("build these first") is already built**, tested, and in use.
- **Tier A1 (bounce/mastering analysis) is the real next build.**
- **Verify the Digitakt sample rate** before any large Digitakt export (see below).

Do not point a fresh session at "build A2". Start from
[`sample-tools/README.md`](sample-tools/README.md) and
[`library-tools/README.md`](library-tools/README.md), then move to A1.

## Tier-by-tier reality check

| Brief tier | Brief said | Actual state |
|---|---|---|
| **A2** sample-prep | High confidence — build first | **Done.** `sample-tools` (ffmpeg, per-device specs, `--dry-run` / `--list` / `--force` / `--sync`, never overwrites, stages to `_EXPORT/`) plus `library-tools` (`sample-review`, sort, dedupe, intake, manifest + undo) match the brief almost exactly, including dry-run-by-default. Two-zone `CURATED/` + `PACKS/` model shipped 2026-06-21. |
| **A3** docs / git | Cheap, safe, do first | **Done.** README, `docs/STORAGE-AND-WORKFLOW.md`, design specs under `docs/superpowers/`, git history, tests. Nothing to set up. |
| **A1** bounce analysis | Already specced — strongest fit | **Not built.** No `librosa` / `soundfile` / `pyloudnorm` in use. `sample-tools/requirements.txt` lists them only as future work. This is the real next module. |
| **B1** Ableton MCP | Medium confidence | **Not started.** No MCP config, no rack/macro convention in-repo. |
| **B2** Extensions SDK auditor | Medium confidence | **Not started.** |
| **C1** MIDI generation | Experimental, opt-in | **Not started** (and should not block anything else, per the brief). |

## Digitakt sample rate: verify before export

The brief flagged the Digitakt's exact format as its least confident item — correctly.
The repo currently assumes **44.1 kHz**, same as the Octatrack.

`sample-tools/src/sampletools/config.py` hardcodes Digitakt at **44.1 kHz**, 16-bit,
mono. `manifests/digitakt.txt` has real packs queued against that assumption. No
evidence of a real Digitakt export having run yet, so nothing may have shipped at
the wrong rate — but the next run could.

Community sources (not yet confirmed against Robin's unit) converge on **16-bit,
48 kHz, mono** as the Digitakt's native format, with Elektron Transfer resampling
imports to 48 kHz. That is the opposite rate from the Octatrack (44.1 kHz,
confirmed correct).

References:

- [Digitakt samples 44.1 kHz vs 48 kHz – Elektronauts](https://www.elektronauts.com/t/digitakt-samples-44-1-khz-vs-48-khz/44763)
- [Change the sample rate from 48 to 44.1 in Digitakt? – Elektronauts](https://www.elektronauts.com/t/change-the-sample-rate-from-48-to-44-1-in-digitakt/206963)
- [Digitakt User Manual (Elektron, ENG OS1.51)](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf)

**Before any Digitakt batch export:** check one factory sample on the actual unit
(or the manual locally). If confirmed 48 kHz, change `rate=44100` → `rate=48000`
for the `digitakt` entry in `config.py`.

## Cross-repo notes

These surfaced during the desk review and may still need reconciliation in
`command-center`:

1. **Machine-of-record.** The brief assumes the Mac mini is the studio machine.
   `command-center/infrastructure.md` and `music.md` listed the MacBook Air as
   Ableton's canonical home. This repo's `docs/STORAGE-AND-WORKFLOW.md` hedges
   with "mini + MacBook Air M4". Worth a one-line fix in `command-center` once
   confirmed.

2. **Wiring / routing knowledge base.** `command-center` points to a local-only
   `studio-macbookair` project for patchbay wiring. That likely matches the brief's
   companion Knowledge Base document. Could not be cross-checked from this repo.

3. **Backup (resolved 2026-07-07).** At assessment time, backup was the blocker
   before destructive moves or APFS migration. Robin confirmed the SSD is backed up.
   Ongoing backup checks remain maintenance, not a blocker.

## Other notes

- **Non-standard WAV chunks (Octatrack):** likely mitigated. `sample-tools` uses
  ffmpeg's plain `-f wav` muxer with `pcm_s16le` — vanilla RIFF/WAVE output. Not
  hardware-tested from the desk review, but a low-risk failure mode.

- **A1 should feed A2, not run in parallel.** A good bounce, once analysed, should
  re-enter the sample library and flow through the existing `sample-tools` export
  path onto hardware.

- **Unofficial integrations:** `command-center` already records declining automation
  against unofficial or reverse-engineered integrations. Same instinct applies to
  Tier B1's "treat community Ableton MCP servers as untrusted code."

## Recommended order of work (updated)

| Priority | Task | Status |
|---|---|---|
| 1 | Confirm Digitakt sample rate on hardware (one file) | Open |
| 2 | Back up the SSD | **Done** (2026-07-07) |
| 3 | Build Tier A1 (LUFS, spectral, mono compatibility) as a feeder into `sample-tools` | Open |
| 4 | Reconcile Mac-mini vs MacBook-Air doc drift in `command-center` | Open |
| 5 | Tiers B1 / B2 / C1 | Deferred per brief |

### Addendum: drum-role classifier (2026-07-09)

A pretrained drum classifier was integrated, briefly adopted, then **downgraded**
after calibration failed (0/10 proposed `KICKS → CLAP-SNARE` moves were correct on
ear check). It remains **experimental** — review candidates only, not authorised
moves. See [`decisions/2026-07-09-drum-role-classifier-downgraded.md`](decisions/2026-07-09-drum-role-classifier-downgraded.md).

Human audition and calibrated route cleanup (`sample-role-cleanup`) are the path
forward for role-folder correctness.
