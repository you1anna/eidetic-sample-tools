# Ableton `.als` introspection (`ableton-tools`) — design

_Date: 2026-06-26. Status: approved, ready for implementation._

## Problem

Ableton project files accumulate with no index. `Production/Ableton_Projects/` already shows the
symptom — chaotic, near-duplicate names (`blacked_mac_1.wav.asd`, `speeditUPPPP.wav.asd`,
`speedituuuuuppppp.wav.asd`) — and good loops/stems from past jams are buried inside Sets that
nobody can search. The resample loop the studio workflow depends on never closes, because there's
no way to ask "which Sets exist, at what tempo/key, using which samples, and where are the reusable
parts?" without opening each one in Live.

## Target model: read-only parse of `.als` (gzipped XML)

A `.als` file is gzip-compressed XML. This tool **reads** it (never writes a Set) and emits indexes:

```
*.als → gunzip → XML → extract {tempo, key?, tracks, scenes, devices, SampleRef paths} → TSV/JSON
```

Two commands:
- **`als-index`** — walk a projects root, emit one row per Set: path, tempo, time-sig, track count,
  scene count, named tracks, device list, length hint, mtime.
- **`als-samples`** — for one Set or a tree, resolve every `SampleRef` to an absolute path and
  report **present / missing / relinked** media; optionally list short audio clips that are
  candidates to promote into the sample library (closing the resample loop).

## Scope (this session)

**In scope:**
1. Robust `.als` reader: gunzip + `xml.etree.ElementTree` parse, tolerant of version differences
   and malformed files (skip-and-report, never crash a whole sweep).
2. `als-index`: tempo (`Tempo`/`Manual` value), tracks (`MidiTrack`/`AudioTrack` names), scenes,
   devices (`Devices` children class names), basic length, mtime → TSV + JSON.
3. `als-samples`: extract `SampleRef` → `FileRef` paths, classify present/missing, summarise.
4. CLI + console scripts + venv (zero third-party deps).

**Out of scope (later / never):**
- **Never writes/edits `.als`** (no relinking, no "collect and save" mutation) — read-only.
- Decoding device parameters / automation curves.
- A GUI; this emits text/TSV that downstream tools (or the sample library) consume.

## Safety guarantees

- **Read-only.** Opens files for reading only; emits reports to a chosen output dir. Cannot harm a
  project or the (unbacked) SSD. Not gated by the backup.
- Malformed/locked files are logged and skipped, never fatal.

## New tool: `ableton-tools/` (package `abletontools`)

| Module | Responsibility |
|---|---|
| `read.py` | `load_als(path) -> ElementTree` (gunzip+parse); `iter_sets(root) -> Iterator[Path]`. |
| `index.py` | `set_summary(tree, path) -> SetInfo` dataclass; TSV/JSON emit. |
| `samples.py` | `sample_refs(tree) -> list[SampleRef]`; resolve + present/missing classify. |
| `cli.py` | `als-index` and `als-samples` mains + console scripts. |

**Default roots (env-overridable):** `/Users/macbookair/Music/Ableton` and
`/Volumes/Extreme SSD/Production` (mirrors `config.py` env pattern).

**Open item — machine of record.** Per `command-center/infrastructure.md`, Ableton's canonical home
is the **MacBook Air** (`/Users/macbookair/Music/Ableton`), with the Mac mini as worker. This tool
defaults to that path and runs wherever the projects are mounted; reconcile the mini-vs-Air doc
drift (flagged in the 2026-06-25 assessment) when convenient — not a blocker here.

## Tests (`tests/`)

- `test_read.py`: build a fixture `.als` by gzipping a small hand-written Live-shaped XML; assert
  load succeeds; assert a truncated/non-gzip file is reported, not raised.
- `test_index.py`: tempo extraction, track-name extraction, device listing from the fixture.
- `test_samples.py`: `SampleRef` path extraction; a ref to a non-existent file → "missing"; a ref
  to a temp file that exists → "present".

## Operator / skill path

Claude Code, local where the Ableton projects mount. Implementation: `writing-plans` →
`test-driven-development` (parsing is pure given a fixture tree) → `verification-before-completion`
(run `als-index` over the real `Ableton_Projects/` and sanity-check the rows).
