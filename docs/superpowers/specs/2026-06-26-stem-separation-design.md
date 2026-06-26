# Stem separation (`stem-tools`) — design

_Date: 2026-06-26. Status: approved, ready for implementation. Build last (heaviest install)._

## Problem

Per the workflow doc, vocals and many usable parts enter the studio **via resampling, not
pre-chopped packs** — "easy to find, audition, and drop in live." There's currently no way to pull
a clean vocal, drum, or bass stem out of a bounce or a reference track so it can be resampled in the
Octatrack or dropped into Live. Source separation closes that gap.

## Target model: wrap `demucs` → routed stems

```
input.wav → demucs (htdemucs) → {drums, bass, vocals, other}.wav
          → optional auto-route vocals → CURATED/VOCALS/ (named via library-tools naming)
```

A thin, well-tested wrapper around `demucs` — the tool owns **argument/plan/routing logic and
naming**, not the ML. The model run itself is shelled out and treated as a black box.

## Scope (this session)

**In scope:**
1. `stem-split <file>`: invoke `demucs` for a chosen input, into a chosen output dir.
2. Plan/report which stems will be produced and where (dry-run by default).
3. Optional `--route-vocals` to move the `vocals` stem into `CURATED/VOCALS/` with a convention
   name, reusing `librarytools` naming + `moves.safe_move` (never overwrite, undo-logged).
4. CLI + console script + its own venv (isolates the heavy `torch`/`demucs` install).

**Out of scope (later / never):**
- Training/fine-tuning models; choosing exotic model variants beyond a sensible default.
- Realtime/streaming separation.
- Batch-separating the whole library (opt-in, per-file or small-set; this is expensive).

## Safety guarantees

- **Reads input, writes new stem files**; never overwrites (`-N` suffix); the optional vocal route
  uses `moves.safe_move` + undo log. No deletions. Not gated by the SSD backup (but heavy on CPU/
  GPU — run deliberately).
- `demucs` + `torch` live only in `~/.venvs/stem-tools`; never a dependency of any other tool.

## New tool: `stem-tools/` (package `stemtools`)

| Module | Responsibility |
|---|---|
| `split.py` | `build_cmd(src, out_dir, model) -> list[str]`; `run(cmd)`; `expected_outputs(src, out_dir, model) -> dict[str,Path]`. |
| `route.py` | `route_vocals(stems, vocals_dest) -> Move` reusing `librarytools.moves` + naming. |
| `cli.py` | `stem-split` main + console script (dry-run default, `--apply`, `--route-vocals`). |

**Default:** model `htdemucs`; output under a `_STEMS/` working dir (env-overridable).

## Tests (`tests/`)

- `test_split.py`: `build_cmd` produces the correct `demucs` argv for given input/model/out;
  `expected_outputs` maps the four stem names to the right paths. **The model is mocked** — CI must
  not download weights or run inference.
- `test_route.py`: `route_vocals` targets `CURATED/VOCALS/<convention-name>`, never overwrites,
  records an undo line; dry-run moves nothing.

## Operator / skill path

Claude Code, local on a Mac with the venv installed (first run downloads model weights).
Implementation: `writing-plans` → `test-driven-development` (command construction + routing are
pure/mocked) → `verification-before-completion` (one real `stem-split` on a short bounce; confirm
four stems land and a routed vocal appears correctly named).
