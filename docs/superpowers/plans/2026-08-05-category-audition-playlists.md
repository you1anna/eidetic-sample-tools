# Category Audition Playlists Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every curation packet directly auditionable by category while retaining one combined playlist and repairing the existing 63-row `tribal-140-01` packet without changing its selection.

**Architecture:** `labels.tsv` remains the packet authority. A focused writer in `librarytools.curate` reads those rows, rewrites the combined playlist, creates one role playlist plus a Markdown index, and is called both automatically by `prepare_packet` and explicitly through `sample-curate playlists` after manual trims.

**Tech Stack:** Python 3.12, standard-library `csv`, `json`, `pathlib` and `shutil`, pytest, M3U8 text files, Markdown documentation.

## Global Constraints

- Never copy, move, convert, rename or edit source audio.
- Preserve the current `labels.tsv` schema and keep it as the only feedback record.
- Preserve label-sheet order within the combined and category playlists.
- Keep `audition.m3u8` for backwards compatibility and add `#EXTM3U` to every generated playlist.
- Generate lowercase, hyphenated category filenames from trusted `suggested_role` values.
- Regeneration replaces only derived playlist artifacts and must remove stale category playlists.
- Repair `tribal-140-01` from its existing 63-row label sheet; never rerun candidate selection.
- Do not write to `CURATED/`, `_EXPORT/` or removable media.

---

### Task 1: Category playlist writer

**Files:**
- Modify: `library-tools/src/librarytools/curate.py:177-216`
- Modify: `library-tools/tests/test_curate.py:81-99`

**Interfaces:**
- Produces: `write_audition_playlists(root: Path, labels_path: Path) -> dict[str, Path]`
- Consumes: existing `read_labels(path: Path) -> list[LabelRow]`, `TRUSTED_ROLES`, and each row's `current_path` and `suggested_role`.

- [ ] **Step 1: Write failing tests for category output and exact membership**

Add a test that creates `KICK` and `PERC` files, prepares a two-role packet, and asserts:

```python
count = prepare_packet(root, db, out, quotas={"KICK": 2, "PERC": 2}, multiplier=1)

assert count == 4
assert (out / "audition.m3u8").read_text().splitlines()[0] == "#EXTM3U"
assert (out / "playlists" / "kick.m3u8").is_file()
assert (out / "playlists" / "perc.m3u8").is_file()

rows = list(csv.DictReader((out / "labels.tsv").open(), delimiter="\t"))
expected = {
    role: [str(root / row["current_path"]) for row in rows if row["suggested_role"] == role]
    for role in {"KICK", "PERC"}
}
assert (out / "playlists" / "kick.m3u8").read_text().splitlines()[1:] == expected["KICK"]
assert (out / "playlists" / "perc.m3u8").read_text().splitlines()[1:] == expected["PERC"]
```

Also assert that concatenating the category playlist entries produces the same set as the combined playlist entries, with no duplicate entries.

- [ ] **Step 2: Run the focused test and confirm the old generator fails**

Run:

```bash
~/.venvs/library-tools/bin/python -m pytest \
  library-tools/tests/test_curate.py::test_prepare_packet_writes_category_playlists -q
```

Expected: FAIL because `playlists/kick.m3u8` and `playlists/perc.m3u8` do not exist and the combined playlist has no `#EXTM3U` header.

- [ ] **Step 3: Implement the minimal playlist writer**

Add this interface in `curate.py` and call it at the end of `prepare_packet` after `packet-meta.json` is written:

```python
def write_audition_playlists(root: Path, labels_path: Path) -> dict[str, Path]:
    rows = read_labels(labels_path)
    root = root.resolve()
    grouped: dict[str, list[Path]] = {}
    combined: list[Path] = []
    for row in rows:
        if row.suggested_role not in TRUSTED_ROLES:
            raise CurationError(f"unsupported suggested_role: {row.suggested_role or '<empty>'}")
        source = (root / row.current_path).resolve()
        if not source.is_relative_to(root):
            raise CurationError(f"sample path escapes root: {row.current_path}")
        combined.append(source)
        grouped.setdefault(row.suggested_role, []).append(source)
    # Rewrite audition.m3u8, replace the generated playlists directory,
    # write one <role.lower()>.m3u8 per group, and write playlists/README.md.
    return generated_paths
```

Use a small private `_write_m3u8(path: Path, sources: list[Path]) -> None` helper so the combined and category formats cannot diverge. It must write `#EXTM3U\n` for an empty playlist and `#EXTM3U\n<absolute paths>\n` otherwise.

The generated index must use deterministic alphabetical role order and this table shape:

```markdown
# Audition playlists

Listen category by category, then record every decision in `../labels.tsv`.

| Category | Files | Playlist |
|---|---:|---|
| `KICK` | 2 | [kick.m3u8](kick.m3u8) |

[Complete packet](../audition.m3u8) contains all categories in label-sheet order.
```

- [ ] **Step 4: Run the focused playlist tests**

Run:

```bash
~/.venvs/library-tools/bin/python -m pytest \
  library-tools/tests/test_curate.py::test_prepare_packet_writes_identity_labels_and_playlist \
  library-tools/tests/test_curate.py::test_prepare_packet_writes_category_playlists -q
```

Expected: both PASS.

- [ ] **Step 5: Commit the category writer**

```bash
git add library-tools/src/librarytools/curate.py library-tools/tests/test_curate.py
git commit -m "feat(library-tools): split audition playlists by category"
```

---

### Task 2: Safe playlist regeneration command

**Files:**
- Modify: `library-tools/src/librarytools/curate.py`
- Modify: `library-tools/src/librarytools/curate_cli.py:10-75`
- Modify: `library-tools/tests/test_curate.py`

**Interfaces:**
- Consumes: `write_audition_playlists(root: Path, labels_path: Path) -> dict[str, Path]` from Task 1.
- Produces: `regenerate_packet_playlists(labels_path: Path) -> dict[str, Path]` and CLI `sample-curate playlists --labels PATH`.

- [ ] **Step 1: Write failing regeneration and metadata tests**

Add tests that:

1. Prepare a two-role packet, rewrite `labels.tsv` with only the `KICK` row, call `regenerate_packet_playlists`, and assert `perc.m3u8` was removed, `kick.m3u8` contains one item, and the combined playlist contains one item.
2. Create `labels.tsv` without `packet-meta.json`, call the function, and assert `CurationError` contains `packet-meta.json`.
3. Write malformed JSON and JSON without a non-empty string `root`, then assert each call raises `CurationError` with `invalid packet metadata`.
4. Call `curate_cli.main(["playlists", "--labels", str(labels)])` on a valid packet and assert return code 0 and output contains `category playlists:`.

- [ ] **Step 2: Run the regeneration tests and confirm they fail**

Run:

```bash
~/.venvs/library-tools/bin/python -m pytest library-tools/tests/test_curate.py -k 'regenerate or playlists_cli' -q
```

Expected: FAIL because `regenerate_packet_playlists` and the `playlists` CLI subcommand do not exist.

- [ ] **Step 3: Implement metadata-driven regeneration**

Add:

```python
def regenerate_packet_playlists(labels_path: Path) -> dict[str, Path]:
    metadata_path = labels_path.parent / "packet-meta.json"
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CurationError(f"cannot read packet-meta.json: {exc}") from exc
    root = metadata.get("root")
    if not isinstance(root, str) or not root.strip():
        raise CurationError("invalid packet metadata: root must be a non-empty path")
    return write_audition_playlists(Path(root), labels_path)
```

Normalise the two metadata error messages if necessary so missing files are distinguishable while malformed JSON and missing `root` both clearly identify invalid packet metadata.

In `curate_cli.py`, add the parser:

```python
playlists = sub.add_parser("playlists")
playlists.add_argument("--labels", type=Path, required=True)
```

Handle this command before opening `LibraryDatabase`, because regeneration depends only on retained packet evidence:

```python
if args.command == "playlists":
    paths = regenerate_packet_playlists(args.labels)
    categories = len([name for name in paths if name not in {"combined", "index"}])
    print(f"category playlists: {categories} -> {args.labels.parent / 'playlists'}")
    return 0
```

- [ ] **Step 4: Run all curation tests**

Run:

```bash
~/.venvs/library-tools/bin/python -m pytest library-tools/tests/test_curate.py -q
```

Expected: all PASS.

- [ ] **Step 5: Commit the regeneration command**

```bash
git add library-tools/src/librarytools/curate.py \
  library-tools/src/librarytools/curate_cli.py library-tools/tests/test_curate.py
git commit -m "feat(library-tools): regenerate trimmed packet playlists"
```

---

### Task 3: Document category-first auditioning

**Files:**
- Modify: `docs/WORKFLOWS.md:199-220`
- Modify: `library-tools/README.md:218-234`
- Modify: `library-tools/manifests/tribal-140-01-audition/README.md:58-90`

**Interfaces:**
- Consumes: `sample-curate playlists --labels PATH` from Task 2.
- Produces: one documented process that starts at `playlists/README.md` and regenerates after any manual trim.

- [ ] **Step 1: Update the canonical workflow**

Change `docs/WORKFLOWS.md` to state that `prepare` writes a combined playlist, category playlists and
one label sheet. Direct the listener to `playlists/README.md`. Add the regeneration command immediately
after the trimming guidance:

```bash
sample-curate playlists --labels manifests/foundation-v1-review/labels.tsv
```

State that it rewrites derived playlists from the current label rows and never changes audio or decisions.

- [ ] **Step 2: Update the command reference**

Change the `prepare` row to `Writes category-scoped audition playlists, a combined playlist and labels.`
Add:

```markdown
| `playlists` | `--labels` | Regenerates combined and category playlists from a packet's current labels. |
```

- [ ] **Step 3: Update the active packet instructions**

Replace `Audition audition.m3u8` with a six-row linked category table carrying counts
`PERC=20`, `TOM=16`, `RIM=8`, `VOCAL-LOOP=8`, `DRUM-LOOP=7`, `VOCAL=4`. Describe
`audition.m3u8` as the optional combined pass and retain the existing feedback instructions.

- [ ] **Step 4: Check documentation consistency**

Run:

```bash
rg -n "audition\.m3u8|playlists/README|sample-curate playlists" \
  docs/WORKFLOWS.md library-tools/README.md \
  library-tools/manifests/tribal-140-01-audition/README.md
git diff --check
```

Expected: category-first instructions in all three files, no whitespace errors.

- [ ] **Step 5: Commit public workflow documentation**

```bash
git add docs/WORKFLOWS.md library-tools/README.md \
  library-tools/manifests/tribal-140-01-audition/README.md
git commit -m "docs: make sample auditioning category-first"
```

---

### Task 4: Rebuild and verify the live packet

**Files:**
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/README.md`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/drum-loop.m3u8`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/perc.m3u8`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/rim.m3u8`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/tom.m3u8`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/vocal-loop.m3u8`
- Create: `library-tools/manifests/tribal-140-01-audition/playlists/vocal.m3u8`
- Modify: `library-tools/manifests/tribal-140-01-audition/audition.m3u8`

**Interfaces:**
- Consumes: installed editable `sample-curate` and the existing 63-row `labels.tsv` plus `packet-meta.json`.
- Produces: the actual category playlists Robin will audition.

- [ ] **Step 1: Regenerate from retained labels**

Run from the repository root:

```bash
~/.venvs/library-tools/bin/sample-curate playlists \
  --labels library-tools/manifests/tribal-140-01-audition/labels.tsv
```

Expected: `category playlists: 6` and no change to `labels.tsv`.

- [ ] **Step 2: Verify counts independently**

Run:

```bash
for playlist in library-tools/manifests/tribal-140-01-audition/playlists/*.m3u8; do
  awk '!/^#/ && NF {count++} END {print FILENAME, count + 0}' "$playlist"
done
awk '!/^#/ && NF {count++} END {print FILENAME, count + 0}' \
  library-tools/manifests/tribal-140-01-audition/audition.m3u8
```

Expected: `perc=20`, `tom=16`, `rim=8`, `vocal-loop=8`, `drum-loop=7`, `vocal=4`, combined `63`.

- [ ] **Step 3: Verify membership against labels**

Run a read-only Python assertion that parses `labels.tsv`, compares every role playlist to the
absolute paths expected for that role, and asserts the combined playlist equals all label rows in order.

- [ ] **Step 4: Commit generated packet artifacts**

```bash
git add library-tools/manifests/tribal-140-01-audition/audition.m3u8 \
  library-tools/manifests/tribal-140-01-audition/playlists
git commit -m "data: split tribal 140 audition packet by category"
```

---

### Task 5: Update the private studio masterplan and complete verification

**Files:**
- Modify: `/Users/macmini/Projects/eidetic-studio/guides/sample-device-masterplan.md`
- Verify: all files changed by Tasks 1-4.

**Interfaces:**
- Consumes: the implemented category playlist process and live packet links.
- Produces: the private forward plan that now requires category-first auditioning and regeneration after trims.

- [ ] **Step 1: Update and version the masterplan**

Bump the guide from v1.2 to v1.3 and date it 2026-08-05. In Phase 2, replace the single-playlist
instruction with: open `playlists/README.md`, audition one role at a time, record decisions in the
single `labels.tsv`, and run `sample-curate playlists --labels <packet>/labels.tsv` after any trim.
Add a revision-history row describing the category-playlist correction. Do not change architecture,
channel maps or committed MIDI decisions.

- [ ] **Step 2: Run the complete library-tools test suite**

Run:

```bash
~/.venvs/library-tools/bin/python -m pytest library-tools -q
```

Expected: all tests PASS.

- [ ] **Step 3: Run repository integrity checks**

Run `git diff --check` and `git status --short` in both repositories. Confirm `CURATED/` and
`_EXPORT/` still contain no audio and confirm `labels.tsv` still has 63 data rows with blank decisions.

- [ ] **Step 4: Sync the private studio repository**

Run exactly:

```bash
scripts/sync.sh "make sample auditioning category-first"
```

Expected: the script stages, commits and pushes the v1.3 masterplan.

- [ ] **Step 5: Commit any final sample-tools verification adjustment**

If verification required no changes, skip this step. Otherwise stage only the verified sample-tools
files and commit with a message describing the exact adjustment; rerun the affected test before committing.
