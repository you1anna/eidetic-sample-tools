# Project status

Last updated: 2026-07-09. A one-page summary of where things stand. Detailed
records live in [`decisions/`](decisions/).

## The goal

Turn the sample library on the Extreme SSD
(`/Volumes/Extreme SSD/Production/SAMPLES/`) into a **trusted, clean library**,
then export the right material — in the right format — onto hardware (Octatrack
first, then Digitakt and TR-8S).

"Trusted" means each file is in the folder that matches what it actually is: a
kick in `KICKS/`, a clap in `CLAP-SNARE/`, and so on. **Human audition is the
final gate** — no automated tool authorises moves on its own.

## What works today

### sample-tools

Converts and syncs curated samples to each device's spec (16-bit / 44.1 kHz WAV,
mono for Digitakt). Manifest-driven. Ready to use.

### library-tools

The review and curation toolkit. Reads the library and writes TSV manifests. Can
dry-run classify, de-dupe, sort, and intake whole vendor packs.

**Important:** these tools are manifest-first. They do not move, rename, or
delete samples unless you explicitly run an apply step after human review.

### Human-gated role cleanup

`sample-role-cleanup` turns a classifier audit into per-route audition packets.
You listen, label each calibration row (`move`, `keep`, or `unsure`), and only
then generate a move plan. No route moves until every calibration row is `move`.

## Drum-role classifier — experimental only

A pretrained CNN-BiLSTM model (`sample-analyze --classifier`) can suggest drum
role mismatches. It was adopted on 2026-07-09, then **downgraded the same day**
after calibration failed: 10 files the model called clap/snare were all kicks on
ear check (0/10 correct).

**Current rule:** the classifier may produce review candidates. It must not
authorise moves, exclusions, hardware crates, or wider library organisation.

Full records:

- Adopted: [`decisions/2026-07-09-drum-role-classifier-adopted.md`](decisions/2026-07-09-drum-role-classifier-adopted.md)
- Downgraded (active): [`decisions/2026-07-09-drum-role-classifier-downgraded.md`](decisions/2026-07-09-drum-role-classifier-downgraded.md)

### What the development scan showed (not sufficient for batch moves)

Early validation on filename-labelled packs looked strong:

- 12/12 true kicks kept, 0/36 obvious contaminants leaked
- Full `KICKS/` scan: 1,882 kept, 613 flagged with suggested destinations

That test used easy canonical kicks and obvious contaminants. It did not
establish recall on processed or atypical kicks. The `trust ≥ 0.80` band was an
uncalibrated softmax threshold, not measured real-world accuracy.

### Saved full-library audit

The 2026-07-09 run wrote **13,584 rows** to
`library-tools/manifests/sample-intelligence-pilot/role-audit-latest.tsv`
(10,951 drum rows, 2,633 non-drum soft checks). It flagged **280**
high-confidence drum-role mismatches. **Do not batch-move from these flags** —
calibrate each route by ear first.

The `KICKS → CLAP-SNARE` route (62 candidates) is **rejected** after
calibration: do not move any of those files.

## Constraints to remember

### Model licensing

Upstream weights (`faraway1nspace/DrumClassifer-CNN-LSTM`) have **no license**.
Code is a clean-room reimplementation. Weights are user-supplied on this machine
only at `library-tools/models/drum-cnn-lstm.model` (gitignored — never commit).

### Optional heavy dependencies

`torch` and `librosa` live behind the `classifier` extra. The default venv may
not include them — install explicitly for classifier work.

### Manifest-only by default

Audits and cleanup preparation do not move files. Re-filing requires a separate
reviewed apply step.

## What is not done yet

1. **Calibrated role cleanup.** The audit is saved; routes need ear-checked
   calibration before any moves.

2. **No samples re-filed** from classifier suggestions.

3. **No Octatrack export** from a validated clean pool.

## Next steps (in order)

1. Run `sample-role-cleanup prepare` against the saved audit to generate
   audition packets per route.

2. Calibrate each route by ear. Plan and apply only routes where every
   calibration sample is correct. Dry-run first; every move is reversible.

3. Build the **Octatrack export** from the validated clean pool.

4. Decide whether to label a ~100-sample benchmark (25 per drum role) to score
   this model or licensed alternatives before integrating another classifier.

## Quick reference

| Item | Location or command |
|---|---|
| Sample library | `/Volumes/Extreme SSD/Production/SAMPLES/` |
| CURATED roles | BASS, CLAP-SNARE, DRONE-ATMOS, DRUM-KITS, DRUM-LOOPS, FX-RISE-IMPACT, HATS-CYM, KICKS, MIDI, PERC, SYNTH-STAB-CHORD, VOCALS |
| Python venvs | `~/.venvs/` (per tool). Target Python 3.12. |
| Classifier audit | `sample-analyze --classifier` → `role-audit-latest.tsv` (candidates only) |
| Role cleanup | `sample-role-cleanup prepare` → per-route audition packets |
