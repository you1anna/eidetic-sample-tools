# AGENTS.md — eidetic-sample-tools

Entry point for Codex/ChatGPT, Claude Code, and any other agent working in this repo.

## Read first

1. `README.md` — what the product is and its safety model.
2. `docs/WORKFLOWS.md` — the canonical inspect → organise → curate → export sequence.
3. `docs/SAFETY.md` — preview-first / `--apply` / undo rules. Non-negotiable.
4. The relevant package `README.md` (`library-tools/`, `sample-tools/`, `ableton-tools/`).

## What this repo is

`Eidetic Sample Tools` — a **public**, personal-first CLI toolkit for hardware electronic
musicians. Three Python packages: `library-tools` (index/curate/dedupe a sample library),
`sample-tools` (validate + convert approved samples for Octatrack/Digitakt/TR-8S), and
`ableton-tools` (read-only `.als` introspection).

This repo is **not** the studio setup source of truth. Physical studio wiring, MIDI
sync, and session workflow live in the **private** `eidetic-studio` repo
(`~/Projects/eidetic-studio`). Do not add studio-wiring docs here — it is public.

## Verify a change

Each package has its own venv under `~/.venvs/<pkg>` (never install globally; target
Python 3.12 at `/opt/homebrew/bin/python3.12`). Run its tests:

```bash
~/.venvs/library-tools/bin/python -m pytest library-tools -q
~/.venvs/sample-tools/bin/python -m pytest sample-tools -q
~/.venvs/ableton-tools/bin/python -m pytest ableton-tools -q
```

## Sensitive / generated (do not commit)

- Sample library data lives at `/Volumes/Extreme SSD/Production/SAMPLES` — never copy it in.
- `external/` (vendored third-party clones) and `.spikes/` (throwaway experiments) are gitignored.
- Ableton projects: archive at `/Volumes/Extreme SSD/Production/ABLETON_PROJECTS`, active scratch at `~/Projects/Production`.

## Do not change without asking

- `profiles/` (studio + device TOML) — these mirror real hardware constraints.
- The safety defaults in `docs/SAFETY.md` and the preview/`--apply` gating in move/export code.

## Personal repository Git workflow

Work directly on `main` and push to the configured remote for Robin’s personal
repositories unless he explicitly asks otherwise. Do not create feature branches
or pull requests by default. If work is already on a branch, integrate the completed
work into `main` and push it rather than leaving it on that branch. Never force-push
or discard unrelated work to satisfy this preference.
