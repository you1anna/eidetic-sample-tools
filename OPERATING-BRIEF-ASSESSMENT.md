# Operating Brief Assessment — 2026-06-25

Robin produced an "Eidetic Studio — Claude Code Operating Brief" (a tiered automation plan for
the Mac mini studio: bounce analysis, sample-prep, Ableton MCP scaffolding, an Extensions SDK
Set auditor, MIDI material generation) and asked for it to be assessed against what already
exists in this repo. This doc captures that assessment so a future session — especially one
running locally on the Mac mini with the SSD attached — doesn't re-derive it or rebuild work
that's already done.

The assessment was done from a sandboxed remote session with **no access to the SSD, Ableton,
or any studio hardware** — it's a desk review of the brief against this repo's code, tests, and
docs, plus `command-center`'s cross-repo tracking. It is not a hands-on verification.

## Bottom line

The brief is well-calibrated but was written without visibility into this repo. Its **Tier A2
("build these first") is not a build item — it's already built, tested, and in use.** The real
next build is Tier A1 (bounce/mastering analysis), and there's one concrete factual correction
to make before the Digitakt is used again.

## Tier-by-tier reality check

| Brief tier | Brief's framing | Actual state in `eidetic-music-tools` |
|---|---|---|
| **A2** sample-prep pipeline | "High confidence, build these first" | **Already done.** `sample-tools` (ffmpeg, per-device specs, `--dry-run`/`--list`/`--force`/`--sync`, never overwrites, stages to `_EXPORT/`) + `library-tools` (`sample-review`/`sort`/`dedupe`/`intake`, manifest+undo, 64 tests green) cover this almost exactly as specced, down to the same dry-run-by-default philosophy. Two-zone `CURATED/` + `PACKS/` model shipped 2026-06-21. |
| **A3** docs/git versioning | "Cheap, safe, do first" | Already true for this repo — README, `docs/STORAGE-AND-WORKFLOW.md`, design specs under `docs/superpowers/`, full git history, tests. Nothing to set up here. |
| **A1** bounce/mastering analysis | "Already specced... strongest fit" | **Genuinely missing.** No `librosa`/`soundfile`/`pyloudnorm` anywhere — `sample-tools/requirements.txt` lists them only as "future work" (BPM detection / inventory). This is the real next build, not a refinement. |
| **B1** Ableton MCP scaffolder | Medium confidence | Nothing exists yet. No MCP config, no rack/macro convention captured anywhere in-repo. |
| **B2** Extensions SDK Set auditor | Medium confidence | Nothing exists yet. |
| **C1** MIDI material generation | Experimental, opt-in | Nothing exists yet (and per the brief's own framing, nothing should be a dependency). |

**Practical sequencing implication:** don't point a fresh Claude Code session at "build A2" —
point it at `sample-tools/README.md` and `library-tools/README.md` and start at A1 instead.

## Correction: Digitakt sample rate is very likely 48kHz, not 44.1kHz

The brief flags the Digitakt's exact sample format as its #1 "least confident" item (original
§6.1) and says not to batch-convert until confirmed. That instinct was right — and the direction
of the error is the opposite of what the repo currently assumes.

`sample-tools/src/sampletools/config.py:55-67` hardcodes the Digitakt device spec at
**44.1kHz**, 16-bit, mono — the same rate as the Octatrack — with no caveat. `manifests/digitakt.txt`
already has real packs queued against that assumption (Goldbaby 909, SP-1200, VETH percussion),
though there's no evidence in `command-center/sessions.md` that a real Digitakt export has
actually been run yet (the 2026-06-19/21 session notes are about library reorg, not device
export), so nothing has necessarily shipped at the wrong rate — but the next run could.

Web research (multiple independent sources, not yet primary-source-confirmed — the official PDF
manual returned HTTP 403 on fetch) converges on: **the Digitakt's native/fixed sample format is
16-bit, 48kHz, mono**, and Elektron Transfer / the device resamples anything else to 48kHz on
import. That's the opposite rate from the Octatrack (44.1kHz, confirmed-correct per the brief).

- [Digitakt samples 44.1khz vs 48khz – Elektronauts](https://www.elektronauts.com/t/digitakt-samples-44-1-khz-vs-48-khz/44763)
- [Change the sample rate from 48 to 44.1 in Digitakt? – Elektronauts](https://www.elektronauts.com/t/change-the-sample-rate-from-48-to-44-1-in-digitakt/206963)
- [Digitakt User Manual (Elektron, ENG OS1.51)](https://www.elektron.se/wp-content/uploads/2024/09/Digitakt_User_Manual_ENG_OS1.51_231108.pdf)
- [24-bit to 16? – Digitakt – Elektronauts](https://www.elektronauts.com/t/24-bit-to-16/42887)

**Action before any further Digitakt export:** verify on Robin's actual unit (check a factory
sample's properties, or check the manual locally), then if confirmed, change one line —
`rate=44100` → `rate=48000` for the `digitakt` entry in `config.py`. Do not batch-export
Digitakt content for real until this is settled either way.

## Cross-repo discrepancies surfaced (not visible from inside this repo alone)

1. **Machine-of-record conflict.** The brief assumes the Mac mini is the studio machine.
   `command-center/infrastructure.md` and `music.md` currently say the opposite — Ableton's
   canonical home is listed as the **MacBook Air** (`~/Music/Ableton`), with the Mac mini cast as
   "always-on worker + local-model host," not the performance machine. This repo's own
   `docs/STORAGE-AND-WORKFLOW.md` hedges with "into Ableton on a Mac (mini + MacBook Air M4)."
   Those `command-center` docs are ~3 weeks stale (last reviewed 2026-06-05/07) against a brief
   dated 2026-06-25, so the brief is probably the freshest source — but it's worth a one-line fix
   in `command-center/music.md` once confirmed, since this is exactly the kind of drift its
   `make doctor` check exists to catch.
2. **The wiring/routing knowledge base isn't in this repo or `command-center`.**
   `command-center/projects.md` and `sources.md` point to a separate, local-only project,
   `studio-macbookair` (`/Users/macbookair/Projects/studio-macbookair`, "compiles Samson S-Patch
   Plus patchbay wiring plans, docs, and SVGs"), last reviewed 2026-06-07. That's almost certainly
   the brief's companion "Knowledge Base" document. It wasn't accessible from this session
   (out of GitHub scope, local-only path) so the brief's hybrid capture map / mixer routing
   couldn't be cross-checked against it — worth reconciling locally, since it predates the brief
   by about three weeks.
3. **Backup is still the literal, unresolved blocker.** Both the brief and
   `docs/STORAGE-AND-WORKFLOW.md` agree backing up the SSD is top priority before any exFAT→APFS
   reformat. `command-center`'s last consumed note (2026-06-19) shows destructive moves were
   *already* being deferred specifically because there's no backup yet. This blocks more than
   Tier A2 — it's also a precondition for Tier B2 (an auditor that's allowed to touch a Live Set)
   and for trusting any batch conversion at all. It belongs ahead of A1 in practice, even though
   the brief's sequencing only implies it.

## Other notes

- The brief's A2 concern about "non-standard WAV chunks that the OT silently rejects" already
  looks mitigated: `sample-tools/src/sampletools/convert.py` forces ffmpeg's plain `-f wav`
  muxer with `pcm_s16le`, which produces a vanilla RIFF/WAVE file — about as clean as WAV output
  gets. Not hardware-tested from this session, but not a likely failure mode either.
- A1's output and A2's pipeline are not separate efforts and the brief doesn't connect this dot
  explicitly: a good bounce, once analyzed and confirmed, should re-enter the sample library and
  flow through the *already-built* `sample-tools` export path back onto hardware. Build A1 as a
  feeder into A2, not a parallel track.
- `command-center/decisions/2026-06-21-notebooklm-evaluation.md` already establishes Robin's
  precedent for declining to build automation against unofficial/reverse-engineered integrations.
  The same instinct applies directly to Tier B1's "treat community Ableton MCP servers as
  untrusted code" guidance — it's consistent with, not new relative to, how this system already
  handles that class of risk.

## Recommended order of actual work

1. Confirm the Digitakt sample rate on real hardware (one file, not a batch) — unblocks the rest.
2. Back up the SSD — unblocks everything destructive, including what `sample-tools` /
   `library-tools` already do.
3. Build Tier A1 (LUFS / spectral / mono-compatibility analysis) as a new module, designed to
   feed good output back into the existing `sample-tools` pipeline rather than stand alone.
4. Reconcile the Mac-mini-vs-MacBook-Air doc drift in `command-center` while in there.
5. Tiers B1/B2/C1 stay deferred exactly as the brief tiers them.
