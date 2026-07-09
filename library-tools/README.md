# library-tools

Lightweight tools to review and tidy the sample library on the Extreme SSD.

**Safety first:** review tools are manifest-only. Tidy tools default to dry-run
and never delete — they only move files, write a plan manifest, and (with
`--apply`) an undo manifest.

## Tools

| Command | What it does |
|---|---|
| `sample-review` | Indexes the library and proposes role folders and hardware-friendly filenames in a TSV manifest. Covers category, loop/one-shot type, BPM, key, and tempo fit across `PACKS/`, `_REVIEW/`, and incoming vendor folders. Skips `CURATED/` and staging/export folders. Never moves or renames originals. |
| `sample-analyze` | Read-only sample intelligence: Octatrack Set registry, source registry, feature/tag TSV, device crate suggestions, and a short report. Add `--classifier` for experimental drum-role suggestions (review only — does not authorise moves). |
| `sample-sort` | Applies `sample-review` classifications: moves confidently classified files flat into their role folder (`<ROLE>/<proposed_name>`). Dry-run by default. `--apply` moves files and writes an undo manifest. `--include-review` gathers low-confidence files into `_REVIEW/`. Name collisions get a `-N` suffix. Move-only, never overwrites. |
| `sample-classify` | Older coarse sorter: sorts `_PACKS/`, `DRUM-KITS/`, `00_INBOX/` into sound-type buckets (`LOOPS/`, `ONE-SHOTS/`, `PADS-DRONES/`, `OTHER/`), keeping one level of pack grouping. Superseded by `sample-sort` for role-based organisation; still useful for the loop/one-shot split. |
| `sample-dedupe` | Finds byte-identical duplicates and moves extras to `_TO-DELETE/dupes/` for later human sign-off. |
| `sample-near-dupes` | Manifest-only near-duplicate pilot from cached `sample-analyze` acoustic features. After short-hit audition proved unreliable, it only emits long, high-certainty loop pairs by default. Stages only reviewed TSV rows marked `decision=remove`. |
| `sample-intake` | Detects whole vendor packs at the library root or in `00_INBOX/`, normalises names, and moves them into `PACKS/`. Dry-run by default, reversible. |
| `sample-role-cleanup` | Turns a classifier audit into per-route audition packets (`checklist.md`, M3U, labels). Human labels each calibration row before any move plan is generated. Read-only until apply. |

Run sort (or the older classify) **before** dedupe so dedupe sees the final layout.

## Install

Per-machine venv (Python 3.12):

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/library-tools[dev]"
```

For the drum-role classifier, install with the `classifier` extra:

```bash
~/.venvs/library-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/library-tools[classifier,dev]"
```

## Quick start

Shell aliases (optional):

```bash
ls() { ~/.venvs/library-tools/bin/sample-sort "$@"; }
lc() { ~/.venvs/library-tools/bin/sample-classify "$@"; }
ld() { ~/.venvs/library-tools/bin/sample-dedupe "$@"; }
ln() { ~/.venvs/library-tools/bin/sample-near-dupes "$@"; }
lr() { ~/.venvs/library-tools/bin/sample-review "$@"; }
```

Common commands:

```bash
lr --no-probe --summary
lr --no-probe --output manifests/review.tsv
lr --no-probe --output manifests/review.tsv --index-dir manifests/index

ls                        # dry-run: per-role counts + plan manifest
ls --apply                # move classified files into <ROLE>/
ls --include-review --apply   # also gather low-confidence files into _REVIEW/

ld                 # dry-run: duplicate count and reclaimable space
ld --apply         # move byte-identical dupes to _TO-DELETE/dupes/

ln --limit-groups 10      # near-dupe pilot batch, manifest-only
ln --family kick-909      # near-dupe one-family pilot

~/.venvs/library-tools/bin/sample-analyze --pilot --no-probe
~/.venvs/library-tools/bin/sample-analyze --classifier
```

## Manual curation workflow

Use this when you want to make progress yourself before asking AI to improve
classification rules. The idea: generate small summaries and inspect focused TSV
slices locally, rather than pasting huge manifests into chat.

### 1. Refresh the manifest index

```bash
cd "/Users/macmini/Projects/eidetic-music-tools/library-tools"
lr() { ~/.venvs/library-tools/bin/sample-review "$@"; }

lr --no-probe --summary
lr --no-probe --output manifests/review-latest.tsv --index-dir manifests/index-latest
```

This writes review data only. It does **not** move, rename, convert, or delete
samples. Re-run after you add or remove packs.

### 2. Inspect useful slices

Open these TSVs in Numbers, LibreOffice, VS Code, or a text editor:

- `manifests/index-latest/high-confidence/KICKS.tsv`
- `manifests/index-latest/high-confidence/BASS.tsv`
- `manifests/index-latest/high-confidence/DRUM-LOOPS.tsv`
- `manifests/index-latest/tempo/techno-core.tsv`
- `manifests/index-latest/tempo/techno-adjacent.tsv`
- `manifests/index-latest/tempo/house-lower.tsv`
- `manifests/index-latest/review-needed.tsv`

**Checks to do by hand:**

- Sort by `main_category`, `sample_type`, `bpm`, `key`, and `tempo_fit`.
- Skim `review-needed.tsv` for missing keywords or pack patterns.
- Review `house-lower.tsv` manually — lower-BPM house material may still be
  useful for pitching, chopping, dub texture, or resampling.
- Check `warnings` for `digitakt-name>24`, but leave hardware-bank curation until
  the library index is cleaner.
- When asking AI to improve rules, pick 10–30 representative problem rows. Do
  not send the whole manifest.

### 3. Quick terminal summaries

```bash
wc -l manifests/index-latest/*.tsv manifests/index-latest/tempo/*.tsv
sed -n '1,25p' manifests/index-latest/review-needed.tsv
rg -n "house-lower|too-fast|unknown" manifests/review-latest.tsv
find "/Volumes/Extreme SSD/Production/SAMPLES" -name '._*' | wc -l
```

Counts plus a handful of example rows are usually enough context to improve
rules.

### 4. Safe dry-runs only

These check the library without changing it:

```bash
lc --no-probe
ld
```

Avoid `lc --apply` or `ld --apply` until the manifest review looks right and you
have a backup. `ld` can estimate duplicate candidates, but staging should wait
until the category/index pass has settled.

### Review output explained

Run review before any apply step when improving library taxonomy. It keeps
musical axes separate:

| Field | Meaning |
|---|---|
| `main_category` | Kicks, bass, vocals, and so on |
| `sample_type` | Loop, one-shot, texture, unknown |
| `bpm` / `key` | Explicit tags only — no guessing |
| `tempo_fit` | Advisory bucket, not a delete decision |
| `proposed_name` | Hardware-friendly filename |
| `warnings` | e.g. names longer than Digitakt's 24-character limit |

**Tempo fit buckets:** `techno-core` = 130–150 BPM · `techno-adjacent` = 124–129
· `house-lower` = below 124 · `too-fast` = above 150 · `unknown` = no explicit
BPM. Lower-BPM house material stays indexed because it may still be useful.

**`--index-dir` output:**

```text
high-confidence/<CATEGORY>.tsv
tempo/techno-core.tsv
tempo/techno-adjacent.tsv
tempo/house-lower.tsv
tempo/too-fast.tsv
tempo/unknown.tsv
review-needed.tsv
```

BPM is extracted only from explicit tags (`132 BPM`, `132bpm`, `[132]`) or
standalone numbers in paths already identified as loops/grooves. That keeps drum
machine names like `707`, `808`, `909`, `303`, and `SH101` from becoming bogus
tempo data. Key extraction is similarly conservative.

## Sample intelligence pilot

`sample-analyze` is the read-only layer after `sample-review`. It registers
Octatrack Sets as intact sources, indexes audio/doc/project files by source kind,
derives first-pass character tags with reason strings, and writes suggested crate
manifests for Digitakt, TR-8S, Octatrack, and Ableton.

```bash
~/.venvs/library-tools/bin/sample-analyze --pilot
```

Artifacts land under `manifests/sample-intelligence-pilot/`:

```text
ot-sets-latest.tsv
source-registry-latest.tsv
sample-features-latest.tsv
curated-role-conflicts-latest.tsv
kick-audit-latest.tsv
clusters-latest.tsv
crates/<device>/*.txt
reports/pilot.md
```

By default it decodes samples read-only, writes Tier-1 acoustic features to a
SQLite cache at `manifests/sample-intelligence.sqlite`, and uses those features
for inspectable character tags and within-role cluster groups. Use `--no-probe`
for a fast filename/path-only pass when you do not need acoustic evidence.

**What it is useful for:**

- Confirming Octatrack-native packs are seen as intact Sets, not flattened folders.
- Producing small, device-shaped audition lists spread across measured sound
  clusters rather than alphabetical dumps.
- Inspecting acoustic reasons (`sub_ratio=0.72`, `tail_ms=120`, `centroid_hz=4500`)
  before trusting a tag.
- Surfacing obvious rule mistakes before any export or physical library move.
- Flagging suspicious `CURATED/<role>` rows when the folder conflicts with
  filename or path clues.

**What it does not prove:**

- That the chosen sounds are musically good.
- That a Digitakt or TR-8S bank is performance-ready.
- That heuristic labels (`subby-short`, `metallic-tight`) are semantically true.
  They are grounded in simple acoustic features and still need ear checks.

Treat crates as shortlist manifests for ear-checking. Promote only
human-auditioned favourites into stable export manifests.

### Human-gated role cleanup

`sample-role-cleanup prepare` freezes a classifier audit and writes
deterministic role-to-role audition packets. It is read-only: it does not move
samples.

```bash
sample-role-cleanup prepare \
  --audit manifests/sample-intelligence-pilot/role-audit-latest.tsv \
  --root "/Volumes/Extreme SSD/Production/SAMPLES" \
  --output-dir manifests/role-cleanup-20260709
```

Each route contains `checklist.md`, `audition.m3u8`, `labels.tsv`, and
`candidates.tsv`. Robin marks calibration rows in `labels.tsv` as `move`,
`keep`, or `unsure`. No move plan is created until every calibration row for
that route is `move`.

### High-precision KICKS gate

`kick-audit-latest.tsv` buckets every `CURATED/KICKS` row as `likely_kick`,
`review`, or `reject_as_kick` from cached acoustic features and existing
role-conflict signals. It optimises for precision: a file is `likely_kick` only
when evidence strongly supports it.

- `likely_kick` — only KICKS candidates allowed into representatives and
  device-crate picks.
- `review` — visible for manual follow-up; not presented as kicks until promoted.
- `reject_as_kick` — claps, hats, loops, long impacts, and similar; kept out of
  KICKS selection.

Manifest-only: never moves or renames files. Run the pilot without `--no-probe`
when you need trustworthy KICKS representatives; no-probe runs lack enough
acoustic evidence to promote KICKS rows to `likely_kick`.

### Drum-role classifier (experimental)

`sample-analyze --classifier` runs a pretrained drum-role model and writes
`role-audit-latest.tsv`. Use it to **surface review candidates only** — it does
not authorise moves. Calibration on 2026-07-09 failed (0/10 proposed
`KICKS → CLAP-SNARE` moves were correct on ear check). Human audition and
`sample-role-cleanup` are the path for actual re-filing.

See [`STATUS.md`](../STATUS.md) and
[`decisions/2026-07-09-drum-role-classifier-downgraded.md`](../decisions/2026-07-09-drum-role-classifier-downgraded.md).

```bash
~/.venvs/library-tools/bin/sample-analyze --classifier
```

## Near-duplicate pilot

Use `sample-near-dupes` after a full `sample-analyze --pilot` run. Detection
mode does not move files — it writes a review TSV plus a small Markdown/M3U
audition packet. Short one-shots are ignored (first audition proved unreliable).
The default detector requires long loops (`duration_s >= 3.0`) and high acoustic
certainty (`score >= 0.99`).

```bash
~/.venvs/library-tools/bin/sample-near-dupes --family kick-909
~/.venvs/library-tools/bin/sample-near-dupes --limit-groups 10
```

Outputs under `manifests/near-dupes-pilot/`:

```text
near-dupes-latest.tsv          # edit decision column; only `remove` stages
audition/near-dupes.md         # human checklist
audition/near-dupes.m3u        # keep/candidate pairs for listening
```

To stage approved candidates: edit `near-dupes-latest.tsv`, set `decision=remove`
only on auditioned rows, dry-run first, then apply:

```bash
~/.venvs/library-tools/bin/sample-near-dupes --apply-manifest manifests/near-dupes-pilot/near-dupes-latest.tsv
~/.venvs/library-tools/bin/sample-near-dupes --apply-manifest manifests/near-dupes-pilot/near-dupes-latest.tsv --apply
```

Approved candidates move to `_TO-DELETE/near-dupes/`. Nothing is deleted or
overwritten. An undo manifest is written.

## Classification rules

Precedence (cheapest signal first), matched against the whole lowercased path:

1. Loop keyword (`loop`, `lp`, `groove`, `bpm`, `NNNbpm`)
2. Pad keyword (`pad`, `drone`, `atmos`, `texture`, `swell`, `ambient`)
3. One-shot keyword (`hit`, `shot`, `stab`, `oneshot`, `single`)
4. Duration (< 1.5 s = one-shot, else loop)
5. `OTHER`

Tune keyword sets and the duration threshold in `config.py`.

## Manifests and undo

Every run writes `manifests/<tool>-<timestamp>.tsv` (the plan). An `--apply` also
writes `manifests/undo-<tool>-<timestamp>.tsv` with `dest<TAB>src` lines — reverse
those moves to roll back. `manifests/` is gitignored.

## Safety

The SSD is APFS and backed up (2026-07-07), but the tools stay conservative:

- Move-only — never overwrite (colliding destinations are skipped and logged)
- Dry-run by default
- Stage rather than delete
