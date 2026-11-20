# Two-Zone Sample Library + Pack Intake — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `SAMPLES/` into a `CURATED/` zone (role folders) and a `PACKS/` zone (whole vendor packs with normalized names), add a `sample-intake` tool that routes stray packs into `PACKS/`, and sweep duplicates — all with zero deletions.

**Architecture:** Extend the existing `librarytools` Python package. A new `intake.py` module (peer to `sort.py`) handles folder-level pack moves with name normalization, reusing `moves.py`'s never-overwrite/undo-logged primitives. Existing file-level tools (`sort`, `review`, `dedupe`) are made `CURATED/`-aware. The actual library restructure is executed as reversible operational steps through the same `moves.safe_move` primitive.

**Tech Stack:** Python 3.12, `librarytools` (editable-installed in a Mac venv under `~/.venvs/`), pytest, ffmpeg (unused here). Library root overridable via `SAMPLES_ROOT` env var.

## Global Constraints

- Python 3.12; type hints on all function signatures; prefer `pathlib`.
- **Zero deletions.** All mutations go through `librarytools.moves.safe_move` (checks `dest.exists()` first, never overwrites) and write an undo manifest (`dest \t src`).
- All CLIs **dry-run by default**; `--apply` is explicit. Show the dry-run plan before any apply.
- Manifests are timestamped TSVs in `library-tools/manifests/` (gitignored) via `config.manifest_path(prefix)`.
- Slug/name collisions resolved with `-N` suffix (never skip into a clobber).
- Library root: `config.SAMPLES_ROOT` (default `/Volumes/Extreme SSD/Production/SAMPLES`), overridable via `SAMPLES_ROOT`.
- Naming convention (hardware-friendly): lowercase, `-` separators, no spaces.
- Run all `pytest` and editable installs from the **Mac venv**, not on the exFAT SSD.

---

### Task 1: `normalize_pack_name` — the naming/clarity core

**Files:**
- Create: `library-tools/src/librarytools/intake.py`
- Test: `library-tools/tests/test_intake.py`

**Interfaces:**
- Produces: `normalize_pack_name(raw: str) -> str` — pure; lowercases, strips publisher, format and release-ID tags, converts `.`/space/`_` to `-`, collapses repeats, trims separators.

- [ ] **Step 1: Write the failing test**

```python
# library-tools/tests/test_intake.py
from __future__ import annotations

from pathlib import Path

from librarytools import intake


def test_normalize_strips_format_and_noise_tags():
    raw = "Example.Samples.Deep.Techno.MULTiFORMAT-WAV"
    assert intake.normalize_pack_name(raw) == "example-deep-techno"


def test_normalize_spaces_to_hyphens_lowercase():
    assert intake.normalize_pack_name("Filterheadz Hardgroove Techno") == "filterheadz-hardgroove-techno"


def test_normalize_collapses_repeats_and_trims():
    assert intake.normalize_pack_name("__Foo..Bar--Baz__") == "foo-bar-baz"


def test_normalize_drops_release_id_wrapper_token():
    # release IDs like abc-1234 / trailing numeric IDs are noise
    assert intake.normalize_pack_name("SomePack-abc-1234") == "somepack"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_intake.py -v`
Expected: FAIL with `ModuleNotFoundError`/`AttributeError: module 'librarytools.intake' has no attribute 'normalize_pack_name'`

- [ ] **Step 3: Write minimal implementation**

```python
# library-tools/src/librarytools/intake.py
"""Folder-level intake: route stray vendor packs into PACKS/ with clean names.

Whole packs stay whole — only the top folder is moved and renamed. Reuses
librarytools.moves for never-overwrite, undo-logged, dry-run-by-default moves.
"""

from __future__ import annotations

import re

# Publisher tags, format markers and other noise tokens dropped from pack names.
_NOISE_TOKENS: frozenset[str] = frozenset(
    {
        "multiformat", "multi", "wav", "flac", "aiff", "aif", "scd", "mp3",
        "samples", "sample", "decibel", "decibel.", "pack",
    }
)
# Release-ID shapes like "abc-1234" or a bare trailing number.
_RELEASE_ID = re.compile(r"^[a-z]{2,4}-\d{3,6}$|^\d{3,6}$")


def normalize_pack_name(raw: str) -> str:
    """Lowercase, drop format, publisher and release-ID noise, hyphenate, collapse, trim."""
    lowered = raw.lower()
    # Split on any run of separators (., space, _, -).
    tokens = [t for t in re.split(r"[.\s_-]+", lowered) if t]
    kept = [t for t in tokens if t not in _NOISE_TOKENS and not _RELEASE_ID.match(t)]
    slug = "-".join(kept)
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_intake.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add library-tools/src/librarytools/intake.py library-tools/tests/test_intake.py
git commit -m "feat(intake): normalize_pack_name — clean pack folder slugs"
```

---

### Task 2: intake plan builder — stray-pack detection + move planning

**Files:**
- Modify: `library-tools/src/librarytools/intake.py`
- Modify: `library-tools/src/librarytools/config.py` (add `PACKS_ROOT`, `CURATED_ROOT`)
- Test: `library-tools/tests/test_intake.py`

**Interfaces:**
- Consumes: `config.SAMPLES_ROOT`, `config.SOURCE_EXTS`, `moves.Move`, `review.ROLE_FOLDERS`, `config.DEDUPE_EXCLUDE`, `normalize_pack_name`.
- Produces:
  - `config.CURATED_ROOT: Path`, `config.PACKS_ROOT: Path`
  - `intake.KNOWN_TOP: frozenset[str]` — top-level names that are NOT stray packs.
  - `intake.is_pack_folder(path: Path) -> bool` — dir containing at least one audio file (recursively).
  - `intake.build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]` — one `Move` per stray pack folder → `PACKS/<unique-slug>`, `tag="pack|<original-name>"`.

- [ ] **Step 1: Add config roots**

```python
# library-tools/src/librarytools/config.py  (add near SAMPLES_ROOT)
CURATED_ROOT: Path = SAMPLES_ROOT / "CURATED"
PACKS_ROOT: Path = SAMPLES_ROOT / "PACKS"
```

- [ ] **Step 2: Write the failing tests**

```python
# append to library-tools/tests/test_intake.py
from librarytools import config


def _mk(root: Path, rel: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("audio")
    return p


def test_stray_pack_folder_is_planned_to_PACKS(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Example.Samples.Deep.Techno.MULTiFORMAT-WAV/Kicks/Kick 01.wav")

    plan = intake.build_plan(root=root)

    assert len(plan) == 1
    move = plan[0]
    assert move.src == root / "Example.Samples.Deep.Techno.MULTiFORMAT-WAV"
    assert move.dest == root / "PACKS" / "example-deep-techno"
    assert move.tag.startswith("pack|")


def test_known_top_level_dirs_are_not_strays(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "KICKS/already.wav")        # role folder (legacy top-level)
    _mk(root, "CURATED/KICKS/a.wav")      # curated zone
    _mk(root, "PACKS/existing/b.wav")     # packs zone
    _mk(root, "_QUARANTINE/c.wav")        # staging

    assert intake.build_plan(root=root) == []


def test_loose_audio_file_at_top_is_not_a_pack(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "00_INBOX/loose.wav")       # loose file, left for curation

    assert intake.build_plan(root=root) == []


def test_slug_collision_gets_suffix(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    (root / "PACKS" / "filterheadz-hardgroove-techno").mkdir(parents=True)
    _mk(root, "Filterheadz Hardgroove Techno/a.wav")

    plan = intake.build_plan(root=root)

    assert plan[0].dest == root / "PACKS" / "filterheadz-hardgroove-techno-2"
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_intake.py -v`
Expected: FAIL — `is_pack_folder`/`build_plan` not defined.

- [ ] **Step 4: Implement detection + planning**

```python
# append to library-tools/src/librarytools/intake.py
from pathlib import Path

from . import config, moves, review

# Top-level names that are structure, not stray packs.
KNOWN_TOP: frozenset[str] = (
    frozenset(review.ROLE_FOLDERS)        # legacy top-level role folders + _REVIEW
    | frozenset(config.DEDUPE_EXCLUDE)    # _EXPORT, _TO-DELETE, _QUARANTINE
    | {"MIDI", "00_INBOX", "_PACKS", "CURATED", "PACKS"}
)


def is_pack_folder(path: Path) -> bool:
    """True if path is a directory containing at least one audio file (recursive)."""
    if not path.is_dir():
        return False
    for p in path.rglob("*"):
        if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in config.SOURCE_EXTS:
            return True
    return False


def _unique_dest(dest: Path, claimed: set[Path]) -> Path:
    """dest, or a -N variant if it exists on disk or is already claimed this run."""
    if dest not in claimed and not dest.exists():
        return dest
    n = 2
    while True:
        cand = dest.with_name(f"{dest.name}-{n}")
        if cand not in claimed and not cand.exists():
            return cand
        n += 1


def build_plan(root: Path = config.SAMPLES_ROOT) -> list[moves.Move]:
    """Plan a move for every stray top-level pack folder into PACKS/<slug>."""
    plan: list[moves.Move] = []
    claimed: set[Path] = set()
    packs_root = root / "PACKS"
    for entry in sorted(root.iterdir()):
        if entry.name in KNOWN_TOP or entry.name.startswith("."):
            continue
        if not is_pack_folder(entry):
            continue
        slug = normalize_pack_name(entry.name) or "pack"
        dest = _unique_dest(packs_root / slug, claimed)
        claimed.add(dest)
        plan.append(moves.Move(entry, dest, f"pack|{entry.name}"))
    return plan
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_intake.py -v`
Expected: PASS (8 tests)

- [ ] **Step 6: Commit**

```bash
git add library-tools/src/librarytools/intake.py library-tools/src/librarytools/config.py library-tools/tests/test_intake.py
git commit -m "feat(intake): stray-pack detection + PACKS/ move planner"
```

---

### Task 3: intake CLI + `sample-intake` entry point + PACKS manifest

**Files:**
- Modify: `library-tools/src/librarytools/intake.py`
- Modify: `library-tools/pyproject.toml` (register script)
- Test: `library-tools/tests/test_intake.py`

**Interfaces:**
- Consumes: `intake.build_plan`, `moves.write_plan`, `moves.apply_plan`, `config.manifest_path`, `config.PACKS_ROOT`.
- Produces:
  - `intake.record_manifest(plan: list[moves.Move], packs_root: Path) -> None` — append `slug \t original \t YYYY-MM-DD` lines to `<packs_root>/_manifest.tsv`.
  - `intake.main(argv: list[str] | None = None) -> int` — `--apply` (default dry-run), `--root`.
  - Console script `sample-intake = "librarytools.intake:main"`.

- [ ] **Step 1: Write the failing test**

```python
# append to library-tools/tests/test_intake.py
def test_apply_moves_pack_and_records_manifest(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Filterheadz Hardgroove Techno/a.wav")

    rc = intake.main(["--apply", "--root", str(root)])

    assert rc == 0
    dest = root / "PACKS" / "filterheadz-hardgroove-techno"
    assert (dest / "a.wav").is_file()                       # pack moved whole
    assert not (root / "Filterheadz Hardgroove Techno").exists()
    manifest = (root / "PACKS" / "_manifest.tsv").read_text()
    assert "filterheadz-hardgroove-techno\tFilterheadz Hardgroove Techno\t" in manifest


def test_dry_run_moves_nothing(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _mk(root, "Some Pack/a.wav")

    rc = intake.main(["--root", str(root)])   # no --apply

    assert rc == 0
    assert (root / "Some Pack" / "a.wav").is_file()         # untouched
    assert not (root / "PACKS").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_intake.py -v`
Expected: FAIL — `main`/`record_manifest` not defined.

- [ ] **Step 3: Implement CLI + manifest**

```python
# append to library-tools/src/librarytools/intake.py
import argparse
import sys
from datetime import date


def record_manifest(plan: list[moves.Move], packs_root: Path) -> None:
    """Append slug<TAB>original<TAB>date for each planned pack (for traceability)."""
    if not plan:
        return
    packs_root.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    with (packs_root / "_manifest.tsv").open("a", encoding="utf-8") as fh:
        for m in plan:
            original = m.tag.split("|", 1)[1]
            fh.write(f"{m.dest.name}\t{original}\t{today}\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="sample-intake",
        description="Route stray vendor packs into PACKS/ with clean names (dry-run by default).",
    )
    ap.add_argument("--apply", action="store_true", help="perform the moves (default: dry-run)")
    ap.add_argument("--root", type=Path, default=config.SAMPLES_ROOT, help="library root")
    args = ap.parse_args(argv)

    if not args.root.is_dir():
        print(f"root not found: {args.root}", file=sys.stderr)
        return 2

    plan = build_plan(root=args.root)
    manifest = config.manifest_path("intake")
    moves.write_plan(manifest, plan)
    print(f"[{'APPLY' if args.apply else 'DRY-RUN'}] intake {args.root}")
    print(f"  stray packs: {len(plan)}")
    for m in plan:
        print(f"    {m.tag.split('|', 1)[1]}  ->  PACKS/{m.dest.name}")
    print(f"  plan written: {manifest}")

    if not args.apply:
        print("  (dry-run — re-run with --apply to move packs)")
        return 0

    undo = config.manifest_path("undo-intake")
    counts = moves.apply_plan(plan, undo)
    record_manifest(plan, args.root / "PACKS")
    print(f"  moved: {counts['moved']}; skipped(exists): {counts['exists']}; missing: {counts['missing']}")
    print(f"  undo written: {undo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Register the console script**

In `library-tools/pyproject.toml`, under `[project.scripts]`, add the line (keep alphabetical with the existing `sample-*` entries):

```toml
sample-intake = "librarytools.intake:main"
```

- [ ] **Step 5: Reinstall + run tests**

Run (in the Mac venv): `pip install -e library-tools && pytest tests/test_intake.py -v`
Expected: PASS (10 tests); `which sample-intake` resolves.

- [ ] **Step 6: Commit**

```bash
git add library-tools/src/librarytools/intake.py library-tools/pyproject.toml library-tools/tests/test_intake.py
git commit -m "feat(intake): sample-intake CLI + PACKS/_manifest.tsv traceability"
```

---

### Task 4: Make existing tools `CURATED/`-aware; exclude `PACKS/` from dedupe

**Files:**
- Modify: `library-tools/src/librarytools/sort.py` (dest under `CURATED/`; skip `CURATED`/`PACKS` as sources)
- Modify: `library-tools/src/librarytools/config.py` (`DEDUPE_EXCLUDE` += `PACKS`, `CURATED`-sources)
- Modify: `library-tools/tests/test_sort.py` (update expected destinations)

**Interfaces:**
- Consumes: `config.CURATED_ROOT` (from Task 2).
- Produces: `sort.build_plan` now targets `CURATED/<ROLE>/<name>`; `sort.NON_SOURCE_DIRS` includes `CURATED`, `PACKS`; `config.DEDUPE_EXCLUDE` includes `PACKS`.

- [ ] **Step 1: Update the failing tests first**

In `library-tools/tests/test_sort.py`, change the destination expectation:

```python
    # Flat under the CURATED zone now, not the bare role folder.
    assert move.dest.parent == root / "CURATED" / "KICKS"
```

And add a guard test:

```python
def test_curated_and_packs_are_not_sources(tmp_path: Path):
    root = tmp_path / "SAMPLES"
    _make(root, "CURATED/KICKS/already.wav")
    _make(root, "PACKS/vendor/loop.wav")
    assert sort.build_plan(root=root) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_sort.py -v`
Expected: FAIL — dest is `root/"KICKS"`, and PACKS/CURATED currently walked as sources.

- [ ] **Step 3: Make sort CURATED-aware**

In `library-tools/src/librarytools/sort.py`:

Add `CURATED`/`PACKS` to the non-source set:

```python
NON_SOURCE_DIRS: frozenset[str] = (
    frozenset(review.ROLE_FOLDERS)
    | frozenset(config.DEDUPE_EXCLUDE)
    | {"MIDI", "CURATED", "PACKS"}
)
```

Change the destination in `build_plan` from:

```python
        dest = _unique_dest(root / result.role / name, claimed)
```

to:

```python
        dest = _unique_dest(root / "CURATED" / result.role / name, claimed)
```

- [ ] **Step 4: Exclude PACKS from dedupe**

In `library-tools/src/librarytools/config.py`:

```python
DEDUPE_EXCLUDE: tuple[str, ...] = ("_EXPORT", "_TO-DELETE", "_QUARANTINE", "PACKS")
```

- [ ] **Step 5: Run the full suite**

Run: `pytest -v`
Expected: PASS (all existing tests + intake). If `test_dedupe.py` asserts on a baseline exclude tuple, update that expectation to include `PACKS`.

- [ ] **Step 6: Commit**

```bash
git add library-tools/src/librarytools/sort.py library-tools/src/librarytools/config.py library-tools/tests/test_sort.py
git commit -m "refactor(library): CURATED/PACKS-aware sort + dedupe excludes PACKS"
```

---

### Task 5: Execute the restructure (reversible, operational)

**Files:** none (filesystem operation on `SAMPLES/`). Uses `librarytools.moves.safe_move`.

This moves the 12 role folders into `CURATED/` and renames `_PACKS/` → `PACKS/`. Every move is reversible; an undo manifest is written. **Verify the dry-run printout before running the apply block.**

- [ ] **Step 1: Snapshot the current top level**

Run: `ls -1 "$SAMPLES_ROOT"` (or the default path). Record it.

- [ ] **Step 2: Dry-run — print the planned moves (no changes)**

```python
# python - (Mac venv)  — DRY RUN
from pathlib import Path
from librarytools import config, review
root = config.SAMPLES_ROOT
roles = [r for r in review.ROLE_FOLDERS if r != "_REVIEW"] + ["MIDI", "DRUM-KITS"]
roles = sorted(set(roles))
for r in roles:
    src = root / r
    if src.is_dir():
        print(f"{src}  ->  {root/'CURATED'/r}")
if (root/"_PACKS").is_dir():
    print(f"{root/'_PACKS'}  ->  {root/'PACKS'}")
```

Expected: a list of `KICKS`, `PERC`, `HATS-CYM`, `CLAP-SNARE`, `DRUM-LOOPS`, `DRUM-KITS`, `BASS`, `SYNTH-STAB-CHORD`, `DRONE-ATMOS`, `FX-RISE-IMPACT`, `VOCALS`, `MIDI` → `CURATED/...`, plus `_PACKS → PACKS`. **Confirm none target an existing dir.**

- [ ] **Step 3: Apply — move role folders + rename _PACKS (reversible)**

```python
# python - (Mac venv)  — APPLY
from datetime import datetime
from pathlib import Path
from librarytools import config, review, moves
root = config.SAMPLES_ROOT
(root / "CURATED").mkdir(exist_ok=True)
roles = sorted(set([r for r in review.ROLE_FOLDERS if r != "_REVIEW"] + ["MIDI", "DRUM-KITS"]))
plan = [moves.Move(root/r, root/"CURATED"/r, f"role|{r}") for r in roles if (root/r).is_dir()]
if (root/"_PACKS").is_dir():
    plan.append(moves.Move(root/"_PACKS", root/"PACKS", "rename|_PACKS"))
undo = config.manifest_path("undo-restructure")
counts = moves.apply_plan(plan, undo)
print("counts:", counts)
print("undo:", undo)
```

Expected: `counts['moved']` equals the number of planned items, `exists`/`missing` are `0`. (`safe_move` skips rather than clobbers, so any non-zero `exists` means stop and inspect.)

- [ ] **Step 4: Verify the new top level**

Run: `ls -1 "$SAMPLES_ROOT"` and `ls -1 "$SAMPLES_ROOT/CURATED"`
Expected top level: `CURATED PACKS 00_INBOX _EXPORT _REVIEW _QUARANTINE _TO-DELETE README.md` (plus the 2 stray packs, handled next). `CURATED/` holds the 12 role folders. Re-run `pytest -v` to confirm tools still pass against fixtures (they use tmp trees, so this is a sanity check on imports).

- [ ] **Step 5: Commit (tooling repo only — the library isn't in git, so note the undo manifest path)**

```bash
git add library-tools/manifests/.gitkeep 2>/dev/null; true
git commit --allow-empty -m "chore(restructure): moved role folders -> CURATED/, _PACKS -> PACKS (undo manifest recorded)"
```

---

### Task 6: Intake the stray packs into `PACKS/`

**Files:** none (runs `sample-intake`).

- [ ] **Step 1: Dry-run intake**

Run: `sample-intake`
Expected: lists `Example.Samples.Deep.Techno.MULTiFORMAT-WAV -> PACKS/example-deep-techno` and `Filterheadz Hardgroove Techno -> PACKS/filterheadz-hardgroove-techno` (plus any other strays). **Review the slugs.**

- [ ] **Step 2: Apply intake**

Run: `sample-intake --apply`
Expected: `moved: N; skipped(exists): 0; missing: 0`; undo manifest path printed.

- [ ] **Step 3: Verify**

Run: `ls -1 "$SAMPLES_ROOT/PACKS"` and `cat "$SAMPLES_ROOT/PACKS/_manifest.tsv"`
Expected: normalized pack folders present; manifest maps each slug to its original name. Top level no longer has stray pack folders.

---

### Task 7: Duplicate sweep (staged, sign-off to delete)

**Files:** none (runs `sample-dedupe`).

- [ ] **Step 1: Dry-run dedupe**

Run: `sample-dedupe`
Expected: prints count of byte-identical dupes it would stage to `_TO-DELETE/` (scanning `CURATED/` + `00_INBOX/`; `PACKS/`, `_EXPORT/`, `_TO-DELETE/`, `_QUARANTINE/` excluded). **Review the manifest TSV.**

- [ ] **Step 2: Apply — stage dupes (move, not delete)**

Run: `sample-dedupe --apply`
Expected: dupes moved into `_TO-DELETE/`; undo manifest written. Nothing deleted.

- [ ] **Step 3: Human sign-off**

Eyeball `_TO-DELETE/`. Only after explicit approval, delete its contents:

Run (after sign-off): `du -sh "$SAMPLES_ROOT/_TO-DELETE"` then, on approval, `rm -rf "$SAMPLES_ROOT/_TO-DELETE/"*`
Expected: this is the only deletion in the whole workflow, and it is human-gated.

---

### Task 8: Docs — record the two-zone model and intake workflow

**Files:**
- Modify: `SAMPLES/README.md` (the library's own README at `$SAMPLES_ROOT/README.md`)
- Modify: `README.md` (repo root — `inbox-sort` status)

- [ ] **Step 1: Rewrite `SAMPLES/README.md`**

Update the Structure section to the two-zone model (`CURATED/` = role folders renamed-by-convention; `PACKS/` = whole vendor packs, normalized names, kept intact; staging dirs unchanged). Keep the naming convention and device-export sections as-is. Document the intake workflow: new downloads → `00_INBOX/` or dropped at top level → `sample-intake` routes whole packs to `PACKS/`; promote good finds into `CURATED/` via `sample-sort`. State the no-deletion / dedupe-staging policy. Set `_Last reorganised: 2026-06-21._`.

- [ ] **Step 2: Update repo `README.md`**

Change the `inbox-sort/` row from `planned` to folded into `library-tools` as `sample-intake` (built), matching the existing table style.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: two-zone library model + sample-intake workflow"
```

(`SAMPLES/README.md` lives on the SSD outside the git repo; it is updated in place, not committed.)

---

## Self-Review

**Spec coverage:**
- Target structure → Tasks 5 (role folders → CURATED, _PACKS → PACKS), 6 (strays → PACKS). ✓
- Two-zone separation → Tasks 4 (tooling), 5, 6. ✓
- `sample-intake` tool (normalize, stray detection, whole-move, manifest, dry-run, collisions) → Tasks 1–3. ✓
- Tooling glue (CURATED roots, sort/review awareness, dedupe excludes PACKS) → Tasks 2, 4. ✓
- Safety / zero deletions → Global Constraints + `moves.safe_move` reuse throughout; only Task 7 step 3 deletes, human-gated. ✓
- Duplicate sweep (CURATED+INBOX only, staged) → Task 7. ✓
- Docs → Task 8. ✓
- Deferred items (role-folder content audit, _REVIEW curation, internal flattening) → explicitly out of scope, not tasked. ✓

**Placeholder scan:** No TBD/TODO; every code step shows complete code; commands have expected output. ✓

**Type consistency:** `normalize_pack_name(str)->str`, `is_pack_folder(Path)->bool`, `build_plan(root)->list[moves.Move]`, `record_manifest(plan, packs_root)->None`, `main(argv)->int` consistent across Tasks 1–3. `config.CURATED_ROOT`/`PACKS_ROOT` defined in Task 2, consumed in Task 4. `moves.Move(src, dest, tag)` matches `moves.py`. ✓

**Note on `review.ROLE_FOLDERS`:** Task 5 derives the role list from `review.ROLE_FOLDERS` (excluding `_REVIEW`) plus `MIDI`/`DRUM-KITS` to be safe if they aren't already in that tuple; the dry-run (Step 2) prints the exact set for confirmation before any move.
