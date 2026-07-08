# library-tools

Light, safety-first tools that review and tidy the bulk of the SSD sample
library. Review is **manifest-only**; tidy tools default to **dry-run** and
**never delete** — they only move files, write a plan manifest, and (on
`--apply`) an undo manifest.

- `sample-review` — proposes role folders and hardware-friendly filenames in a
  TSV manifest for human review. It indexes category, loop/one-shot type, BPM,
  key, and tempo fit across `PACKS/`, `_REVIEW/`, and top-level incoming vendor
  folders. It skips `CURATED/` and staging/export folders, and never moves or
  renames originals.
- `sample-analyze` — writes a read-only sample-intelligence pilot: Octatrack Set
  registry, source registry, feature/tag TSV, device crate suggestions, and a
  short report.
- `sample-sort` — the apply step for `sample-review`'s classification: moves
  confidently-classified files **flat** into their role folder
  (`<ROLE>/<proposed_name>`), using the same name/BPM/key analysis. Dry-run by
  default; `--apply` moves and writes an undo manifest; `--include-review` also
  gathers low-confidence files into `_REVIEW/`. Flat-name collisions get a `-N`
  suffix so nothing is skipped. Move-only, never overwrites.
- `sample-classify` — older coarse sorter: sorts `_PACKS/`, `DRUM-KITS/`,
  `00_INBOX/` into sound-type buckets `LOOPS/ ONE-SHOTS/ PADS-DRONES/ OTHER/`,
  keeping one level of pack grouping (`<bucket>/<pack>/...`). Superseded by
  `sample-sort` for role-based organisation; kept for the loop/one-shot split.
- `sample-dedupe` — finds byte-identical duplicates and moves the extras to
  `_TO-DELETE/dupes/` for a later human sign-off.

## Install (per-machine venv)

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/library-tools[dev]"
```

## Use

```bash
ls() { ~/.venvs/library-tools/bin/sample-sort "$@"; }
lc() { ~/.venvs/library-tools/bin/sample-classify "$@"; }
ld() { ~/.venvs/library-tools/bin/sample-dedupe "$@"; }
lr() { ~/.venvs/library-tools/bin/sample-review "$@"; }

lr --no-probe --summary
lr --no-probe --output manifests/review.tsv
lr --no-probe --output manifests/review.tsv --index-dir manifests/index
ls                        # dry-run: per-role counts + plan manifest, nothing moved
ls --apply                # move classified files into <ROLE>/, write undo manifest
ls --include-review --apply   # also gather low-confidence files into _REVIEW/
ld                 # dry-run: how many dupes, ~GB reclaimable
ld --apply         # move dupes to _TO-DELETE/dupes/, write undo manifest
~/.venvs/library-tools/bin/sample-analyze --pilot --no-probe
```

Run sort (or the older classify) **before** dedupe so dedupe sees the final layout.

## Low-token manual workflow

Use this section when you want to make progress yourself before asking AI to
reason over the library. The key idea: generate small summaries and inspect
focused TSV slices locally instead of pasting huge manifests into chat.

### 1. Refresh the manifest index

```bash
cd "/Volumes/Extreme SSD/eidetic-music-tools/library-tools"
lr() { ~/.venvs/library-tools/bin/sample-review "$@"; }

lr --no-probe --summary
lr --no-probe --output manifests/review-latest.tsv --index-dir manifests/index-latest
```

This writes review data only; it does **not** move, rename, convert, or delete
samples. Re-run it after you add/remove packs.

### Sample intelligence pilot

`sample-analyze` is the next read-only layer after `sample-review`. It registers
Octatrack Sets as intact sources, indexes audio/doc/project files by source kind,
derives first-pass character tags with reason strings, and writes small suggested
crate manifests for Digitakt, TR-8S, Octatrack, and Ableton.

```bash
~/.venvs/library-tools/bin/sample-analyze --pilot
```

Generated artifacts land under `manifests/sample-intelligence-pilot/`:

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

#### High-precision KICKS gate

`kick-audit-latest.tsv` buckets every `CURATED/KICKS` row as `likely_kick`,
`review`, or `reject_as_kick` from the cached acoustic features (duration,
attack/tail, sub/low/high ratios, centroid, flatness, onset density, zcr) and the
existing role-conflict signals. It optimises for precision: a file is
`likely_kick` only when the evidence strongly supports it; unusual-but-plausible
kicks stay in `review`.

- `reject_as_kick` rows (clap/snare, hat/cymbal, loops, long impacts, and
  clean-named but noisy one-shots) are **excluded** from KICKS representatives and
  device-crate picks — they stay visible in the manifests but never get presented
  as kicks.
- `likely_kick` and `review` rows remain eligible for the audition packet;
  `review` rows still need a manual ear-check before you trust them as KICKS.

This is manifest-only: it never moves or renames files, and a fresh ear-check is
still required before any physical reclassification.

The command is manifest-only: it does not move, delete, rewrite, convert, or copy
sample files. By default it now decodes samples read-only, writes Tier-1 acoustic
features to a SQLite cache at `manifests/sample-intelligence.sqlite`, and uses
those features for inspectable character tags and within-role cluster/audition
groups. Use `--no-probe` only when you want the old fast filename/path-only pass.

What this is useful for:

- Confirming Octatrack-native packs are seen as intact Sets, not flattened
  folders.
- Producing small, device-shaped audition lists that spread across measured
  sound clusters instead of broad alphabetical dumps.
- Inspecting acoustic reasons such as `sub_ratio=0.72`, `tail_ms=120`, and
  `centroid_hz=4500` before trusting a tag.
- Surfacing obvious rule mistakes in the path/tag heuristics before any export
  or physical library move.
- Flagging suspicious `CURATED/<role>` rows for review/quarantine when the role
  folder conflicts with filename/path clues or one-shot roles contain long/loop
  material.

What it does **not** prove yet:

- That the chosen sounds are musically good.
- That a Digitakt/TR-8S bank is performance-ready.
- That heuristic labels such as `subby-short` or `metallic-tight` are semantic
  truth. They are grounded in simple acoustic features now, but still need ear
  checks. Tier-2 embeddings / text search remain future work.

Treat the crates as shortlist manifests for ear-checking. Promote only
human-auditioned favourites into stable export manifests.

### 2. Inspect the useful slices yourself

Open these TSVs in Numbers, LibreOffice, VS Code, or a text editor:

- `manifests/index-latest/high-confidence/KICKS.tsv`
- `manifests/index-latest/high-confidence/BASS.tsv`
- `manifests/index-latest/high-confidence/DRUM-LOOPS.tsv`
- `manifests/index-latest/tempo/techno-core.tsv`
- `manifests/index-latest/tempo/techno-adjacent.tsv`
- `manifests/index-latest/tempo/house-lower.tsv`
- `manifests/index-latest/review-needed.tsv`

Good human-managed checks:

- Sort by `main_category`, `sample_type`, `bpm`, `key`, and `tempo_fit`.
- Skim `review-needed.tsv` for obvious missing keywords or pack patterns.
- Check `house-lower.tsv` manually; lower-BPM house material may still be useful
  for pitching, chopping, dub texture, or resampling.
- Check `warnings` for `digitakt-name>24`, but leave hardware-bank curation until
  the library index is cleaner.
- Pick 10-30 representative bad rows when asking AI to improve rules. Do not send
  the whole manifest.

### 3. Cheap terminal summaries

These commands help you get signal without token burn:

```bash
wc -l manifests/index-latest/*.tsv manifests/index-latest/tempo/*.tsv
sed -n '1,25p' manifests/index-latest/review-needed.tsv
rg -n "house-lower|too-fast|unknown" manifests/review-latest.tsv
find "/Volumes/Extreme SSD/Production/SAMPLES" -name '._*' | wc -l
```

Use the counts and a handful of example rows as the AI prompt. That is usually
enough context to improve rules without spending tokens on thousands of rows.

### 4. Safe dry-runs only

These are useful checks and do not mutate samples:

```bash
lc --no-probe
ld
```

Avoid `lc --apply` or `ld --apply` until the manifest review looks sane and you
have a backup. `ld` can be run to estimate duplicate candidates, but actual
staging should wait until the category/index pass has settled.

Run review before any apply step when improving the library taxonomy. It keeps
musical axes separate: `main_category` (kicks, bass, vocals, etc.),
`sample_type` (loop, one-shot, texture, unknown), explicit `bpm`/`key`,
`tempo_fit`, proposed hardware-friendly names, and warnings such as names longer
than the Digitakt's 24-character comfort limit.

Tempo fit is advisory, not a delete decision: `techno-core` = 130-150 BPM,
`techno-adjacent` = 124-129, `house-lower` = below 124, `too-fast` = above 150,
and `unknown` = no explicit BPM. Lower-BPM house material stays indexed because
it may still be useful for pitching, chopping, resampling, or dub/hypnotic
texture work.

`--index-dir` writes split TSV indexes for later tooling:

```text
high-confidence/<CATEGORY>.tsv
tempo/techno-core.tsv
tempo/techno-adjacent.tsv
tempo/house-lower.tsv
tempo/too-fast.tsv
tempo/unknown.tsv
review-needed.tsv
```

Review extracts BPM only from explicit tags (`132 BPM`, `132bpm`, `[132]`) or
standalone numbers in paths already identified as loops/grooves. That keeps drum
machine names like `707`, `808`, `909`, `303`, and `SH101` from becoming bogus
tempo data. Key extraction is similarly conservative: obvious `Am`, `A minor`,
`C#`, etc. are indexed; unknown keys stay blank rather than guessed.

## Classification rules

Precedence (cheapest signal first), matched against the whole lowercased path:
loop keyword (`loop`, `lp`, `groove`, `bpm`, `NNNbpm`) → pad keyword
(`pad`, `drone`, `atmos`, `texture`, `swell`, `ambient`) → one-shot keyword
(`hit`, `shot`, `stab`, `oneshot`, `single`) → duration (< 1.5 s = one-shot,
else loop) → `OTHER`. Tune the keyword sets and threshold in `config.py`.

## Manifests & undo

Every run writes `manifests/<tool>-<timestamp>.tsv` (the plan). An `--apply` also
writes `manifests/undo-<tool>-<timestamp>.tsv` with `dest<TAB>src` lines — reverse
those moves to roll back. `manifests/` is gitignored.

## Safety

The SSD is APFS and backed up as of 2026-07-07, but the tools stay conservative:
move-only, never overwrite (a colliding destination is skipped and logged), default to
dry-run, and stage rather than delete.
