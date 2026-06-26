# Stem Separation (`stem-tools`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans). Steps use `- [ ]` checkboxes. **Build last — heaviest install (torch).**

**Goal:** A new `stem-tools` package (`stemtools`, console script `stem-split`) that wraps `demucs`
to split a bounce or reference track into drums/bass/vocals/other, with an optional `--route-vocals`
that files the vocal stem into `CURATED/VOCALS/` via the existing `librarytools` move/naming
primitives. The package owns argv/plan/routing logic and naming; the model is a black box.

**Architecture:** `src/stemtools/{split,route,cli}.py`. `split.build_cmd` constructs the `demucs`
argv; `split.expected_outputs` maps the four stem names to paths; `route.route_vocals` reuses
`librarytools.moves.safe_move`. **The model is never run in tests** — `build_cmd`/`expected_outputs`/
routing are pure and fully testable; inference is mocked.

**Tech Stack:** Python 3.12, `demucs` (pulls `torch`), pytest. Isolated venv `~/.venvs/stem-tools`;
`librarytools` installed alongside (editable) for the routing helpers.

## Global Constraints
- Python 3.12; type hints; `pathlib`.
- **Reads input, writes new stems**; never overwrites (`-N`); optional vocal route is undo-logged
  via `moves.safe_move`. No deletions. Not gated by backup (but CPU/GPU-heavy — run deliberately).
- Dry-run by default; `--apply` to run the model; `--route-vocals` opt-in.
- `demucs`/`torch` live only in this venv; never a dependency of any other tool.
- Default model `htdemucs`; output under `STEM_OUT` (default `<input parent>/_STEMS`).

---

### Task 1: Command construction + output mapping — `split.py`
**Files:** Create `stem-tools/src/stemtools/split.py`, `tests/test_split.py`.
**Interface:** `build_cmd(src, out_dir, model="htdemucs") -> list[str]`;
`expected_outputs(src, out_dir, model="htdemucs") -> dict[str, Path]` (keys: drums/bass/vocals/other);
`run(cmd) -> None`.

- [ ] **Step 1: Failing test** (model mocked — no inference)
```python
# tests/test_split.py
from pathlib import Path
from stemtools.split import build_cmd, expected_outputs

def test_build_cmd_shape(tmp_path: Path):
    cmd = build_cmd(tmp_path / "mix.wav", tmp_path / "out", model="htdemucs")
    assert cmd[0] == "demucs"
    assert "-n" in cmd and "htdemucs" in cmd
    assert str(tmp_path / "mix.wav") in cmd

def test_expected_outputs_keys(tmp_path: Path):
    outs = expected_outputs(tmp_path / "mix.wav", tmp_path / "out")
    assert set(outs) == {"drums", "bass", "vocals", "other"}
    # demucs writes <out>/<model>/<trackname>/<stem>.wav
    assert outs["vocals"].name == "vocals.wav"
    assert "mix" in str(outs["vocals"])
```
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — `build_cmd` → `["demucs", "-n", model, "-o", str(out_dir), str(src)]`;
  `expected_outputs` mirrors demucs' `<out>/<model>/<track-stem>/<name>.wav` layout; `run` shells
  out via `subprocess.run(check=True)` (not exercised in CI).
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(stems): demucs cmd + output mapping`

---

### Task 2: Vocal routing — `route.py`
**Files:** Create `route.py`, `tests/test_route.py`.
**Interface:** `route_vocals(stems: dict[str,Path], vocals_dest_dir: Path, *, name: str | None = None) -> moves.Move`.

- [ ] **Step 1: Failing test** — given a stems dict with an existing `vocals.wav`, plan a `Move` into
  `CURATED/VOCALS/<convention-name>.wav`; never overwrite (collision → `-N`); dry-run moves nothing.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — reuse `librarytools.moves.Move`/`safe_move` and the naming convention
  helper; default name derived from the source track (lowercased, hyphenated).
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(stems): route vocals into CURATED/VOCALS`

---

### Task 3: `stem-split` CLI + packaging
**Files:** Create `cli.py`, `__init__.py`, `pyproject.toml`, `README.md`, `tests/test_cli.py`.
**Console script:** `stem-split = "stemtools.cli:main"`.

- [ ] **Step 1: Failing test** — `main(["--root", <tmp>, "mix.wav"])` (no `--apply`) prints the plan
  (cmd + expected outputs) and runs nothing; with `run`/`subprocess` mocked, `--apply` invokes the
  command once.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — argparse: positional input, `--out`, `--model`, `--apply`,
  `--route-vocals`; dry-run prints `build_cmd` + `expected_outputs`; `--apply` calls `run` then
  (if `--route-vocals`) `route_vocals` once outputs exist.
- [ ] **Step 4: pyproject** — `dependencies = ["demucs"]` plus an editable/local dep note for
  `librarytools`; `dev=["pytest>=8"]`; console script; `packages.find where=["src"]`.
- [ ] **Step 5: venv + suite (tests mock the model)**
```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/stem-tools
~/.venvs/stem-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/library-tools"
~/.venvs/stem-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/stem-tools[dev]"
~/.venvs/stem-tools/bin/pytest /Users/macmini/Projects/eidetic-music-tools/stem-tools -v
```
- [ ] **Step 6: Real-world smoke** — one `stem-split --apply` on a short bounce (first run downloads
  weights); confirm four stems land and a `--route-vocals` run files the vocal correctly named.
- [ ] **Step 7: Commit** — `feat(stems): stem-split CLI + packaging`

---

## Self-Review
- Command/mapping/routing/CLI each test-first; **model never run in CI** (mocked). ✓
- Reads input, writes new stems; vocal route never overwrites, undo-logged. ✓
- `torch`/`demucs` isolated in their own venv; no other tool depends on them. ✓
- Reuses `librarytools` move/naming primitives rather than reimplementing. ✓
