# library-tools

Light, safety-first tools that review and tidy the bulk of the SSD sample
library. Review is **manifest-only**; tidy tools default to **dry-run** and
**never delete** — they only move files, write a plan manifest, and (on
`--apply`) an undo manifest.

- `sample-review` — proposes role folders and hardware-friendly filenames in a
  TSV manifest for human review. It indexes category, loop/one-shot type, BPM,
  key, and tempo fit. It never moves or renames originals.
- `sample-classify` — sorts `_PACKS/`, `DRUM-KITS/`, `00_INBOX/` into sound-type
  buckets: `LOOPS/ ONE-SHOTS/ PADS-DRONES/ OTHER/`, keeping one level of pack
  grouping (`<bucket>/<pack>/...`). Curated role folders are left untouched.
- `sample-dedupe` — finds byte-identical duplicates and moves the extras to
  `_TO-DELETE/dupes/` for a later human sign-off.

## Install (venv on the Mac, never on the exFAT SSD)

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/library-tools
~/.venvs/library-tools/bin/pip install -e "/Volumes/Extreme SSD/eidetic-music-tools/library-tools[dev]"
```

## Use

```bash
lc() { ~/.venvs/library-tools/bin/sample-classify "$@"; }
ld() { ~/.venvs/library-tools/bin/sample-dedupe "$@"; }
lr() { ~/.venvs/library-tools/bin/sample-review "$@"; }

lr --no-probe --summary
lr --no-probe --output manifests/review.tsv
lr --no-probe --output manifests/review.tsv --index-dir manifests/index
lc                 # dry-run: counts table + plan manifest, nothing moved
lc --no-probe      # faster dry-run, keyword signals only (skip duration probe)
lc --apply         # move files into buckets, write undo manifest
ld                 # dry-run: how many dupes, ~GB reclaimable
ld --apply         # move dupes to _TO-DELETE/dupes/, write undo manifest
```

Run classify **before** dedupe so dedupe sees the final layout.

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

The SSD is exFAT with no backup. These tools move-only, never overwrite (a colliding
destination is skipped and logged), default to dry-run, and stage rather than delete.
