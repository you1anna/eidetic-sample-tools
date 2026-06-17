# library-tools

Two light, **reversible** tools that tidy the bulk of the SSD sample library.
Both default to **dry-run** and **never delete** — they only move files, write a
plan manifest, and (on `--apply`) an undo manifest.

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

lc                 # dry-run: counts table + plan manifest, nothing moved
lc --no-probe      # faster dry-run, keyword signals only (skip duration probe)
lc --apply         # move files into buckets, write undo manifest
ld                 # dry-run: how many dupes, ~GB reclaimable
ld --apply         # move dupes to _TO-DELETE/dupes/, write undo manifest
```

Run classify **before** dedupe so dedupe sees the final layout.

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
