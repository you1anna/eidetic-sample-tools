# AGENTS.md — eidetic-sample-tools

Entry point for Codex/ChatGPT, Claude Code, and any other agent working in this repo.

## Read first

1. `README.md` — what the product is and its safety model.
2. `docs/WORKFLOWS.md` — the canonical inspect → organise → curate → export sequence.
3. `docs/SAFETY.md` — preview-first / `--apply` / undo rules. Non-negotiable.
4. The relevant package `README.md` (`library-tools/`, `sample-tools/`, `ableton-tools/`, `live-tools/`).

## What this repo is

`Eidetic Sample Tools` — a **public**, personal-first CLI toolkit for hardware electronic
musicians. Four independently installable Python packages: `library-tools` (index/curate/dedupe a sample library),
`sample-tools` (validate + convert approved samples for Octatrack/Digitakt/TR-8S), and
`ableton-tools` (read-only `.als` introspection), plus the optional experimental
`live-tools` bridge for inspecting and applying guarded edits to a running Live Set.

This repo is **not** the studio setup source of truth. Physical studio wiring, MIDI
sync, and session workflow live in the **private** `eidetic-studio` repo
(`~/Projects/eidetic-studio`). Do not add studio-wiring docs here — it is public.

## Verify a change

Use the existing local Python 3.12 environment; never install globally. The helper
finds a ready environment and forces imports from this checkout:

```bash
python3 scripts/dev_check.py doctor
python3 scripts/dev_check.py test -- library-tools/tests/test_collection_plan.py -q
python3 scripts/dev_check.py test
```

Use `--python /path/to/venv/bin/python` before the subcommand to override discovery.
Run focused checks during edits, then the relevant final suite once. Packaging
changes also need the separate installed-wheel check; a source test run cannot
establish wheel correctness. Commands and the repeatable scale benchmark are in
[docs/DEVELOPMENT.md](docs/DEVELOPMENT.md).

## Resume a bounded increment

Read [STATUS.md](STATUS.md) and the linked feature guide before reconstructing
history. Dated assessments describe their original checkout; check current code
before treating a listed gap as still open. Preserve unresolved user choices in
the checkpoint, and ask when they affect the next increment. Report completed
behaviour, actual verification and the next bounded step without copying private
run artifacts into this repository.

## Documentation structure

This is Robin's required standard for future documentation, established in the
September 10 README refresh. Follow the [design standard](docs/README-DESIGN.md)
when adding features or changing existing documentation.

Root and package READMEs explain functionality and value in plain language for
musicians. Give readers a concrete example and a clear starting link. Keep command
inventories, configuration, schemas and implementation details in linked guides,
package references and architecture documents. Architecture guides should explain
module ownership, data flow, state contracts, failure handling and performance
limits, with source links. Keep current capability separate from planned work and
dated experimental results. The documentation index is [docs/README.md](docs/README.md).

Update affected guides, references, diagrams and status alongside the change they
describe. Keep interface examples current and use synthetic data for public
screenshots. Verify affected links and examples; render changed diagrams and
visually inspect presentation changes before finalising. Preserve this standard
without allowing command inventories or session history to crowd the READMEs.

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
