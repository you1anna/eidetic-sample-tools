# Ableton `.als` Introspection (`ableton-tools`) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans). Steps use `- [ ]` checkboxes.

**Goal:** A read-only `ableton-tools` package (`abletontools`) with `als-index` (one summary row per
Live Set: tempo, tracks, scenes, devices, length, mtime) and `als-samples` (resolve every
`SampleRef`, report present/missing/relinked media, list reusable-loop candidates).

**Architecture:** `src/abletontools/{read,index,samples,cli}.py`. `.als` = gzipped XML →
`gzip.open` + `xml.etree.ElementTree`. Pure extraction functions take a parsed tree; CLI walks a
root and formats TSV/JSON. **Never writes a `.als`.** Zero third-party deps (stdlib only).

**Tech Stack:** Python 3.12, stdlib (`gzip`, `xml.etree.ElementTree`, `pathlib`), pytest. Venv
`~/.venvs/ableton-tools`.

## Global Constraints
- Python 3.12; type hints; `pathlib`.
- **Read-only on `.als`**; outputs go to a chosen report dir only.
- Tolerant parse: a malformed/locked Set is reported and skipped, never fatal across a sweep.
- Default roots env-overridable: `ALS_ROOTS` (`:`-sep), default
  `/Users/macbookair/Music/Ableton:/Volumes/Extreme SSD/Production`.

---

### Task 1: `.als` reader — `read.py`
**Files:** Create `ableton-tools/src/abletontools/read.py`, `tests/test_read.py`.
**Interface:** `load_als(path) -> xml.etree.ElementTree.Element`; `iter_sets(root) -> Iterator[Path]`.

- [ ] **Step 1: Failing test** — build a fixture by gzipping a tiny Live-shaped XML string; assert
  `load_als` returns the root element; assert a non-gzip/truncated file raises `AlsParseError`
  (caught/reported by callers, not propagated through a sweep).
```python
# tests/test_read.py  (fixture helper)
import gzip
from pathlib import Path
from abletontools.read import load_als, AlsParseError

ALS_XML = b"""<?xml version="1.0"?><Ableton><LiveSet>
<Tracks><MidiTrack><Name><EffectiveName Value="Kick"/></Name></MidiTrack></Tracks>
<MasterTrack><DeviceChain><Mixer><Tempo><Manual Value="138"/></Tempo></Mixer></DeviceChain></MasterTrack>
</LiveSet></Ableton>"""

def _mk(p: Path) -> Path:
    p.write_bytes(gzip.compress(ALS_XML)); return p

def test_load_ok(tmp_path):
    root = load_als(_mk(tmp_path / "a.als"))
    assert root.tag == "Ableton"

def test_bad_file_raises_parse_error(tmp_path):
    (tmp_path / "b.als").write_bytes(b"not gzip")
    try:
        load_als(tmp_path / "b.als"); assert False
    except AlsParseError:
        pass
```
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — `gzip.open(path,'rb')` → `ET.parse`; wrap `OSError`/`ET.ParseError`
  in `AlsParseError`. `iter_sets` = `root.rglob("*.als")` skipping `Backup/` dirs and `.` files.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(als): gzip+xml reader, tolerant`

---

### Task 2: Set summary — `index.py`
**Files:** Create `index.py`, extend `tests/test_index.py`.
**Interface:** `SetInfo` dataclass (path, tempo, tracks, scenes, devices, mtime); `set_summary(root_el, path) -> SetInfo`; `to_tsv_row`/`to_json`.

- [ ] **Step 1: Failing test** — from the fixture tree: tempo `138.0`; track names include `"Kick"`;
  device list extracted from `DeviceChain` children class names.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — XPath-ish walks with `ElementTree.iter()`:
  - tempo: `.//Tempo/Manual` `Value` attr → float.
  - tracks: `.//MidiTrack`, `.//AudioTrack` → `.//Name/EffectiveName` `Value`.
  - scenes: count `.//Scenes/Scene`.
  - devices: class names (tag) of `.//DeviceChain//Devices/*`.
  Handle missing nodes → `None`/empty, never raise.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(als): per-Set summary extraction`

---

### Task 3: Sample refs — `samples.py`
**Files:** Create `samples.py`, `tests/test_samples.py`.
**Interface:** `sample_refs(root_el) -> list[SampleRef]` (raw path + resolved); `classify(refs) -> {present,missing}`.

- [ ] **Step 1: Failing test** — fixture XML with a `SampleRef`/`FileRef` pointing at (a) a real
  temp file → "present"; (b) a non-existent path → "missing".
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — extract `.//SampleRef//FileRef`; Live stores path in
  `Path`/`RelativePath`/`Name` elements depending on version — read all, prefer absolute `Path`,
  fall back to relative resolved against the Set's dir. `Path.exists()` → present/missing.
- [ ] **Step 4: Run → pass** — [ ] **Step 5: Commit** — `feat(als): SampleRef extraction + present/missing`

---

### Task 4: CLI + packaging
**Files:** Create `cli.py`, `__init__.py`, `pyproject.toml`, `README.md`, `tests/test_cli.py`.
**Console scripts:** `als-index = "abletontools.cli:index_main"`, `als-samples = "abletontools.cli:samples_main"`.

- [ ] **Step 1: Failing test** — `index_main(["--root", <fixture dir>, "--out", <tmp>])` writes a TSV
  with one row; `samples_main` reports the missing/present counts.
- [ ] **Step 2: Run → fail**
- [ ] **Step 3: Implement** — argparse; walk `iter_sets`, wrap each in try/except `AlsParseError`
  (log + skip), emit TSV + optional `--json`. Default roots from `ALS_ROOTS`.
- [ ] **Step 4: pyproject** — `dependencies = []`, `dev = ["pytest>=8"]`, both console scripts,
  `packages.find where=["src"]`.
- [ ] **Step 5: venv + run suite**
```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/ableton-tools
~/.venvs/ableton-tools/bin/pip install -e "/Users/macmini/Projects/eidetic-music-tools/ableton-tools[dev]"
~/.venvs/ableton-tools/bin/pytest /Users/macmini/Projects/eidetic-music-tools/ableton-tools -v
```
- [ ] **Step 6: Real-world smoke** — run `als-index` over `/Users/macbookair/Music/Ableton` (or the
  mounted `Production/Ableton_Projects`), eyeball rows; this is `verification-before-completion`.
- [ ] **Step 7: Commit** — `feat(als): als-index + als-samples CLIs + packaging`

---

## Self-Review
- Reader / index / samples / CLI each test-first. ✓
- Read-only on `.als` throughout (no write path exists). ✓
- Tolerant of version/format differences and malformed files. ✓
- Zero third-party deps; isolated venv. ✓
- Machine-of-record note (Ableton on MacBook Air) honored via default roots. ✓
