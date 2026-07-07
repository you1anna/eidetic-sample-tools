# Sample intelligence — progress audit

**Date:** 2026-07-07
**Status:** findings; direction decision pending Robin
**Repo:** `eidetic-music-tools`
**Reviewer:** Claude (Opus 4.8), evidence-backed against the shipped pilot output
**Scope reviewed:** `library-tools/src/librarytools/analyze.py` (728 LOC), the pilot
manifests under `library-tools/manifests/sample-intelligence-pilot/`, and the design
spec `2026-07-06-sample-intelligence-hardware-crates-design.md`.

## One-line verdict

The **scaffolding is on track and well-built**, but the **audio "intelligence" the
brief actually asked for does not exist yet** — the tool reads filenames and paths, not
sound. Nothing is broken (80 tests pass, read-only, non-destructive), so there is no
urgent *bug* to fix; the urgent issue is *directional*.

## What the brief asked for

> "a novel innovative way to sort and group these logically, with insight into what type
> of sound each is, and how it can be grouped with similar sounds … There needs to be
> some kind of processing or analysis to do this … happy for macmini m4 pro to do some
> of the work but ideally this shouldn't necessarily mean heavyweight processing."

Two explicit requirements: (1) **insight into what a sound is**, and (2) **grouping by
similar sound**. Both require reading audio content. Neither is implemented.

## Evidence (from the pilot's own output, 22,916 feature rows)

| Spec promised (Tier 1) | Pilot actually produced | How measured |
|---|---|---|
| Lightweight audio features: RMS, crest, brightness, transient/attack, tail, sub-energy, onset density, mono-safety | **None** — no audio content is read | `grep -rE "import (numpy\|librosa\|scipy\|soundfile)" src/` → no matches; `pyproject.toml` deps `= []` |
| Duration via `ffprobe` | **0 of 22,916** rows have a duration | pilot ran `--no-probe`; duration column 100% empty |
| Character tags from audio + path | **100% filename-derived**: 2,848 from path strings, 437 from filename suffix, 108 from BPM token; **0 acoustic** | counted from `tag_reasons` column |
| Tag coverage | **3,193 / 22,916 (14%)** samples got any character tag | counted from `character_tags` column |
| Within-role similarity clustering ("group with similar sounds") | **Absent** — `_diverse_rows` groups by filename/path-family *strings*, not sound | code read (`analyze.py:420-477`) |
| SQLite incremental cache | **Absent** — full re-scan every run | no `.sqlite`, only TSV writers |

**Net:** `sample-analyze` is the pre-existing `review.py` filename classifier, plus (a
genuinely useful) Octatrack-Set detector, plus deterministic crate sampling by filename
family. This is the same *class* of approach as the earlier "mad attempts" the brief was
frustrated by — filename guessing — now with more scaffolding around it. The last two
sessions ("crate tuning", "diversify crates") polished crate *diversity* on top of data
that carries no acoustic signal.

## What is genuinely good (keep it)

- **Octatrack-Set registry** (`detect_ot_sets`) solves a real, stated problem: *Caught on
  Tape 808+909* and *Cult of SP1200* stay intact and installable (`preserve-set`) instead
  of being flattened. This is the strongest part of the work.
- **Read-only safety discipline** — no moves/deletes/rewrites; artifacts gitignored.
- **Source model** (`curated-sample` / `vendor-pack-audio` / `octatrack-set-audio` /
  `octatrack-set-project` / `document`) is a sound foundation.
- **80 passing tests**, clean dataclass/CLI structure.

It is the correct chassis with no engine.

## Root cause

The pilot plan explicitly scoped phase 1 as "stdlib-only … optional `ffprobe` duration".
Tier 1 audio-feature extraction (the section the whole brief hinges on) was written into
the *design* but deferred out of the *build*, and then even the one real signal
(duration) was skipped at run time via `--no-probe`. Downstream, every tag and every
crate inherited zero acoustic information.

## Is anything urgent?

- **Bug-urgent:** No. Tests pass; the tool is read-only and non-destructive.
- **Direction-urgent:** Yes. Further tuning of filename-based crates yields no insight
  into *what a sound is*. The correction is to build the Tier-1 audio pass that was
  specced but skipped, then let real features drive tags and within-role grouping.

## Options for the next tier

See the companion plan `plans/2026-07-07-sample-intelligence-tier1-audio-features.md`.
Summary of the three viable engines:

- **Tier 0.5 — stdlib only, zero new deps.** ffmpeg decodes to low-SR mono PCM; compute
  time-domain features in pure Python (RMS envelope, attack/tail, zero-crossing rate as a
  brightness proxy, loop-ishness). Truly minimal, but no spectral features → weaker sound
  insight.
- **Tier 1 — numpy + soundfile (recommended).** Real per-file features: RMS/crest,
  spectral centroid (brightness), spectral flatness (noisy vs tonal), sub-energy ratio,
  attack/tail, onset density. Cached in SQLite keyed on (path, size, mtime) so re-runs are
  instant. Small deps, **no torch**. M4 Pro chews through ~22k short samples in minutes.
  Enables true within-role clustering (`KICKS/subby-short`, `KICKS/rumble-long`, …). This
  is the spec as written but unimplemented.
- **Tier 2 — audio embeddings (opt-in, later).** A small pretrained model (CLAP/PANNs)
  embeds each sample for semantic similarity and text queries ("dirty short 909 kicks",
  "more like this"). Best grouping, but pulls in `torch` (heavier one-time embed, cached).
  The brief said avoid heavyweight, so this sits on top of Tier 1, not instead of it.

**Recommendation:** build **Tier 1** now (delivers both brief requirements at low weight),
keep **Tier 2** as an opt-in follow-on once Tier-1 features prove out by ear.

## Decision required from Robin

1. Which engine (Tier 0.5 / Tier 1 / Tier 2)? Recommended: Tier 1.
2. Build inside `library-tools` (co-located with curation output) or the specced-but-empty
   `analysis-tools/` package? Recommended: stay in `library-tools`.
