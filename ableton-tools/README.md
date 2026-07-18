# ableton-tools

Read-only introspection for Ableton Live Sets (`.als`, gzip-compressed XML). Never writes or edits
a Set — see `docs/superpowers/specs/2026-06-26-ableton-als-introspection-design.md` for the design.

## Commands

- `als-index --root <dir> --out <dir>` — walk a projects root, emit `als-index.tsv`: one row per
  Set (path, tempo, track count, track names, scene count, devices, mtime).
- `als-samples --root <dir> --out <dir>` — resolve every `SampleRef` in every Set under a root,
  report present/missing media to `als-samples.tsv`.

Both commands accept `--root` for a single directory, or fall back to the `ALS_ROOTS`
environment variable (colon-separated list of roots), defaulting to
`/Users/macbookair/Music/Ableton:/Volumes/Extreme SSD/Production`.

## Install

```bash
/opt/homebrew/bin/python3.12 -m venv ~/.venvs/ableton-tools
~/.venvs/ableton-tools/bin/pip install -e ".[dev]"
```

## Test

```bash
~/.venvs/ableton-tools/bin/pytest -v
```
