# Eidetic Sample Tools Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the repository documentation into a clean, personal-first product foundation for Eidetic Sample Tools without changing tool behaviour or hiding research history.

**Architecture:** The root README provides the product overview and routes readers into four canonical user guides. Package READMEs become command references, while `STATUS.md`, `decisions/`, and `docs/superpowers/` keep operational and research history visible. Existing workflow documents become concise compatibility pages that point to the canonical guides, preventing duplicated instructions from drifting.

**Tech Stack:** Markdown, TOML package metadata, Python 3.12 command-line tools, pytest

## Global Constraints

- Use **Eidetic Sample Tools** as the product name and `eidetic-music-tools` only for the repository or its path.
- Write in plain-spoken English with short paragraphs and task-led headings.
- Preserve personal studio context, beta work, research, decisions, specifications, and plans.
- Label capabilities as Stable, Beta, Experimental, Planned, or Retired using the definitions in the approved specification.
- State whether each workflow is read-only, writes derived files, copies audio, or moves audio.
- Human audition remains the final gate for curation, reclassification, and hardware crates.
- Do not change CLI behaviour, touch live audio, run migrations, add a licence, or make pricing and release claims.
- Do not document a command or flag unless it exists in current `--help` output.

---

## File Structure

### Product entry points

- Modify `README.md`: product promise, capability overview, safety summary, supported hardware, safe first run, research visibility, and documentation map.
- Modify `STATUS.md`: dated operational snapshot for the personal installation.
- Create `docs/ROADMAP.md`: product direction, maturity definitions, research map, and commercial-readiness gaps.

### Canonical user guides

- Create `docs/GETTING-STARTED.md`: portable installation, configuration, and first read-only run.
- Create `docs/WORKFLOWS.md`: canonical organise → curate → export sequence.
- Create `docs/SAFETY.md`: action levels, manifests, hashes, apply gates, undo behaviour, and automation limits.
- Modify `docs/STORAGE-AND-WORKFLOW.md`: short compatibility page linking to the canonical workflow and preserving the personal storage map.
- Modify `docs/SAMPLE-FOUNDATION-WORKFLOW.md`: short compatibility page linking to the canonical workflow and preserving the current studio profile commands.

### Command references and metadata

- Modify `library-tools/README.md`: installation and complete library command reference.
- Modify `sample-tools/README.md`: installation and complete device export reference.
- Modify `library-tools/pyproject.toml`: consistent package description.
- Modify `sample-tools/pyproject.toml`: consistent package description.

---

### Task 1: Product Landing Page and Roadmap

**Files:**
- Modify: `README.md`
- Create: `docs/ROADMAP.md`

**Interfaces:**
- Consumes: maturity definitions and product promise from the approved design specification.
- Produces: canonical product positioning and navigation labels used by all later documentation tasks.

- [ ] **Step 1: Capture the existing entry points before rewriting**

Run:

```bash
sed -n '1,220p' README.md
find decisions docs/superpowers/specs docs/superpowers/plans -type f | sort
```

Expected: the current personal README and the complete visible research record are listed; no files are changed.

- [ ] **Step 2: Rewrite the root README as the product landing page**

Use this exact heading order:

```markdown
# Eidetic Sample Tools
## What it does
## Why it is safe
## What works today
## Supported hardware
## Try a safe first run
## Documentation
## Research and beta work
## Project status
## Licence
```

The opening must use the approved promise and immediately say that the project is a personal-first CLI toolkit. `What works today` must separate Stable, Beta, Experimental, and Planned capabilities. `Try a safe first run` must use `sample-review --root /path/to/SAMPLES --no-probe --summary` and link to `docs/GETTING-STARTED.md`. The licence section must state that no software licence has been selected and that source visibility does not grant reuse rights.

- [ ] **Step 3: Write the product roadmap**

Create `docs/ROADMAP.md` with this structure:

```markdown
# Roadmap
## Product direction
## Maturity levels
## Current foundation
## Near-term personal priorities
## Research tracks
## What would make this a product
## Deliberately undecided
```

The near-term priorities are: apply and verify the catalogue foundation, complete the human ear review, produce trusted Octatrack/Digitakt/TR-8S exports, simplify installation, then test the workflow with a second library. The product-readiness gaps are: portable setup, unified packaging, clearer compatibility reporting, a guided workflow, recovery UX, and evidence from users beyond the current studio. Link research tracks to `STATUS.md`, `decisions/`, and `docs/superpowers/`.

- [ ] **Step 4: Check landing-page language and links**

Run:

```bash
rg -n 'Robin|/Users/macmini|/Volumes/Extreme|open.source|production.ready|AI-powered' README.md docs/ROADMAP.md
rg -n '\]\([^)]*\)' README.md docs/ROADMAP.md
```

Expected: personal paths do not appear in the root README; any mention of open source explains that no licence exists; every link target exists or will be created by this plan.

- [ ] **Step 5: Commit the product entry points**

```bash
git add README.md docs/ROADMAP.md
git commit -m "docs: establish Eidetic Sample Tools product story"
```

### Task 2: Portable Getting Started Guide and Package Metadata

**Files:**
- Create: `docs/GETTING-STARTED.md`
- Modify: `library-tools/pyproject.toml`
- Modify: `sample-tools/pyproject.toml`

**Interfaces:**
- Consumes: product name and safe-first-run command from Task 1.
- Produces: portable install commands and package descriptions referenced by both command READMEs.

- [ ] **Step 1: Verify installable entry points and current flags**

Run:

```bash
sed -n '/\[project.scripts\]/,$p' library-tools/pyproject.toml
sed -n '/\[project.scripts\]/,$p' sample-tools/pyproject.toml
python3.12 -m pytest library-tools/tests sample-tools/tests --collect-only -q
```

Expected: eleven `library-tools` entry points, one `sample-tools` entry point, and both test suites collect without importing live audio.

- [ ] **Step 2: Write the portable getting-started guide**

Use this heading order:

```markdown
# Getting started
## Before you begin
## Install the library tools
## Install the export tool
## Point the tools at your library
## Run a read-only review
## Read the output
## Choose your next workflow
## Robin's current setup
```

Requirements:

- State Python 3.12 and `ffmpeg`/`ffprobe` prerequisites.
- Use `python3.12 -m venv .venv` and editable installs from a cloned repository as the portable path.
- Use `/path/to/eidetic-music-tools` and `/path/to/SAMPLES` placeholders only in shell examples, with a sentence telling the reader to replace them.
- Explain that `sample-review` writes TSV output only when `--output` or `--index-dir` is supplied and never moves audio.
- Link to `WORKFLOWS.md`, `SAFETY.md`, both package READMEs, and `ROADMAP.md`.
- Keep the existing `/Users/macmini`, `/Volumes/Extreme SSD`, and `~/.venvs/` values under `Robin's current setup` only.

- [ ] **Step 3: Align package descriptions**

Set the exact descriptions to:

```toml
# library-tools/pyproject.toml
description = "Safely review, organise, curate, and analyse large sample libraries."

# sample-tools/pyproject.toml
description = "Prepare curated samples for Octatrack MKII, Digitakt MKI, and TR-8S."
```

- [ ] **Step 4: Verify metadata parses and the guide does not imply unsafe defaults**

Run:

```bash
python3.12 -c 'import tomllib; [tomllib.load(open(p, "rb")) for p in ("library-tools/pyproject.toml", "sample-tools/pyproject.toml")]'
rg -n -- '--apply|--sync|delete|overwrite' docs/GETTING-STARTED.md
```

Expected: TOML parsing exits 0; the getting-started guide contains no apply or sync command in its first-run path and says the tools do not delete or overwrite source audio.

- [ ] **Step 5: Commit portable setup and metadata**

```bash
git add docs/GETTING-STARTED.md library-tools/pyproject.toml sample-tools/pyproject.toml
git commit -m "docs: add portable getting started guide"
```

### Task 3: Canonical Workflow and Safety Guides

**Files:**
- Create: `docs/WORKFLOWS.md`
- Create: `docs/SAFETY.md`
- Modify: `docs/STORAGE-AND-WORKFLOW.md`
- Modify: `docs/SAMPLE-FOUNDATION-WORKFLOW.md`

**Interfaces:**
- Consumes: install and path conventions from Task 2.
- Produces: canonical operational and safety explanations linked by the root and package READMEs.

- [ ] **Step 1: Extract unique material from the two existing workflow documents**

Run:

```bash
sed -n '1,240p' docs/STORAGE-AND-WORKFLOW.md
sed -n '1,260p' docs/SAMPLE-FOUNDATION-WORKFLOW.md
```

Expected: the personal storage map, library zones, profile validation, catalogue migration, audition, promotion, and device export commands are available for consolidation.

- [ ] **Step 2: Write the canonical workflow guide**

Use this structure:

```markdown
# Workflows
## The operating model
## Library zones
## 1. Inspect without changing audio
## 2. Organise with a reviewed move plan
## 3. Curate by ear
## 4. Build device-specific exports
## 5. Recover or revise a decision
## Personal studio workflow
```

For every numbered phase add an `Action level:` line using one of: `Read-only`, `Writes derived files`, `Moves audio after --apply`, or `Copies approved audio`. Preserve the profile-aware catalogue, curation, and export commands from `SAMPLE-FOUNDATION-WORKFLOW.md`. Explain `PACKS/`, `CATALOGUE/`, and `CURATED/` once and link back to that definition rather than repeating it.

- [ ] **Step 3: Write the safety guide**

Use this structure:

```markdown
# Safety model
## The short version
## Action levels
## Preview before apply
## Manifests and content hashes
## Human approval
## Undo and quarantine
## Limits of automation
## Backup responsibilities
```

Include a table mapping representative commands to their default action and apply behaviour. State explicitly that `sample-review` is read-only with respect to audio, `sample-sort`, `sample-dedupe`, `sample-intake`, and catalogue migration default to preview, `sample-curate promote` copies approved audio, and export writes converted copies. State that classifier confidence is not measured musical correctness.

- [ ] **Step 4: Convert old workflow pages into concise compatibility pages**

Keep both existing filenames so saved links continue to work. Each page must:

- link to `WORKFLOWS.md`, `SAFETY.md`, and `GETTING-STARTED.md` at the top;
- state which guide is canonical;
- retain only unique personal setup information not already present in the canonical guides; and
- avoid duplicating full command sequences.

- [ ] **Step 5: Check action-level coverage and retained personal context**

Run:

```bash
rg -n '^Action level:' docs/WORKFLOWS.md
rg -n 'PACKS/|CATALOGUE/|CURATED/|eidetic-studio|Extreme SSD' docs/WORKFLOWS.md docs/STORAGE-AND-WORKFLOW.md docs/SAMPLE-FOUNDATION-WORKFLOW.md
rg -n 'classifier|human|audition|undo|quarantine|backup' docs/SAFETY.md
```

Expected: all five workflow phases have action-level labels; current studio details remain findable; the safety guide covers human gates, classifier limits, recovery, and backups.

- [ ] **Step 6: Commit the canonical guides**

```bash
git add docs/WORKFLOWS.md docs/SAFETY.md docs/STORAGE-AND-WORKFLOW.md docs/SAMPLE-FOUNDATION-WORKFLOW.md
git commit -m "docs: define safe sample workflows"
```

### Task 4: Library Command Reference

**Files:**
- Modify: `library-tools/README.md`

**Interfaces:**
- Consumes: portable installation from Task 2 and canonical safety/workflow explanations from Task 3.
- Produces: one complete reference for every `library-tools` console command.

- [ ] **Step 1: Capture authoritative command help**

Run:

```bash
for command in sample-review sample-sort sample-dedupe sample-intake sample-analyze sample-near-dupes sample-role-cleanup sample-benchmark sample-profile sample-curate sample-classify; do
  .venv/bin/$command --help
done
```

If the repository `.venv` does not contain the tools, use the installed `~/.venvs/library-tools/bin/` commands. Expected: every command exits 0 and displays the flags documented in the rewritten reference.

- [ ] **Step 2: Rewrite the package README as a command reference**

Use this structure:

```markdown
# Library tools
## Purpose
## Install
## Commands at a glance
## Safe starting point
## Review and index
## Organise and deduplicate
## Curate trusted samples
## Analyse and run experiments
## Profiles
## Output files
## Safety and recovery
```

The command table must include all eleven entry points and a maturity label. Put `sample-classify` under Retired or legacy use, the drum classifier and near-duplicate work under Experimental, and the profile/catalogue foundation under Beta until the live migration and ear review are complete. Replace shell aliases that shadow common commands such as `ls` with direct command names.

- [ ] **Step 3: Check completeness against package metadata**

Run:

```bash
python3.12 - <<'PY'
import re
import tomllib
from pathlib import Path

scripts = tomllib.loads(Path('library-tools/pyproject.toml').read_text())['project']['scripts']
readme = Path('library-tools/README.md').read_text()
missing = [name for name in scripts if f'`{name}`' not in readme]
assert not missing, f'missing commands: {missing}'
print(f'documented {len(scripts)} commands')
PY
```

Expected: `documented 11 commands`.

- [ ] **Step 4: Commit the library reference**

```bash
git add library-tools/README.md
git commit -m "docs: focus library tools command reference"
```

### Task 5: Export Reference and Operational Status

**Files:**
- Modify: `sample-tools/README.md`
- Modify: `STATUS.md`

**Interfaces:**
- Consumes: product terminology, portable setup, canonical workflows, and maturity model from Tasks 1–3.
- Produces: authoritative export instructions and an honest current-state snapshot.

- [ ] **Step 1: Capture current export help and status evidence**

Run:

```bash
~/.venvs/sample-tools/bin/sample-export --help
git log -8 --oneline
git status --short
```

Expected: export help confirms device selection, `--all`, `--list`, `--dry-run`, `--force`, `--sync`, `--profile`, and `--crate`; repository state is known before editing the status page.

- [ ] **Step 2: Rewrite the export README**

Use this structure:

```markdown
# Sample export tool
## Purpose
## Install
## Supported hardware
## Preview an export
## Export a reviewed crate
## Copy to removable media
## Manifest format
## Conversion rules
## Configuration
## Safety and troubleshooting
```

Lead with `--list` and `--dry-run`. Keep the correct device formats: Octatrack 44.1 kHz with source channel layout preserved; Digitakt MKI 48 kHz mono; TR-8S 48 kHz with mono default and approved stereo exceptions. Clearly distinguish staging an export from copying to a card, and explain that Digitakt uses Elektron Transfer rather than disk sync.

- [ ] **Step 3: Rewrite the status page as a dated operational snapshot**

Use this structure:

```markdown
# Project status
## Current position
## Working software
## Live-library state
## Beta and research
## Known limits
## Next actions
## Evidence and decisions
```

Keep the facts that the portable profile/catalogue/curation/export foundation is implemented, the live SSD migration and foundation-v1 ear review have not been applied, the saved classifier audit is suggestion-only, and the rejected `KICKS → CLAP-SNARE` route must not be used. Link detailed classifier history instead of repeating the full narrative.

- [ ] **Step 4: Check product terminology and critical status facts**

Run:

```bash
rg -n 'Eidetic Sample Tools|Octatrack|Digitakt|TR-8S|--list|--dry-run|Elektron Transfer' sample-tools/README.md
rg -n 'not been applied|suggestion|KICKS.*CLAP-SNARE|decisions/' STATUS.md
```

Expected: export preview and all three devices are documented; the status page retains the operational warnings that protect the current library.

- [ ] **Step 5: Commit export and status documentation**

```bash
git add sample-tools/README.md STATUS.md
git commit -m "docs: clarify export reference and project status"
```

### Task 6: Documentation and Test Verification

**Files:**
- Modify: any documentation file from Tasks 1–5 only when verification finds an error.

**Interfaces:**
- Consumes: all rewritten documentation.
- Produces: a link-clean, command-accurate, test-verified documentation set.

- [ ] **Step 1: Check all relative Markdown links and local anchors**

Run:

```bash
python3.12 - <<'PY'
import re
from pathlib import Path
from urllib.parse import unquote

files = [Path('README.md'), Path('STATUS.md'), *Path('docs').rglob('*.md'), Path('library-tools/README.md'), Path('sample-tools/README.md')]
errors = []
for source in files:
    text = source.read_text()
    for target in re.findall(r'\[[^]]*\]\(([^)]+)\)', text):
        if target.startswith(('http://', 'https://', 'mailto:')):
            continue
        path_text, _, anchor = unquote(target).partition('#')
        destination = (source.parent / path_text).resolve() if path_text else source.resolve()
        if not destination.exists():
            errors.append(f'{source}: missing {target}')
            continue
        if anchor and destination.is_file() and destination.suffix == '.md':
            headings = re.findall(r'^#{1,6}\s+(.+?)\s*$', destination.read_text(), re.M)
            slugs = {re.sub(r'[^a-z0-9 -]', '', h.lower()).strip().replace(' ', '-') for h in headings}
            if anchor not in slugs:
                errors.append(f'{source}: missing anchor {target}')
assert not errors, '\n'.join(errors)
print(f'checked {len(files)} Markdown files')
PY
```

Expected: the script prints the checked file count and exits 0.

- [ ] **Step 2: Check terminology, path labelling, and safety language**

Run:

```bash
rg -n '/Users/macmini|/Volumes/Extreme SSD' README.md docs library-tools/README.md sample-tools/README.md STATUS.md
rg -n 'Stable|Beta|Experimental|Planned|Retired' README.md docs/ROADMAP.md library-tools/README.md STATUS.md
rg -n -- '--apply|--sync' README.md docs/GETTING-STARTED.md docs/WORKFLOWS.md docs/SAFETY.md library-tools/README.md sample-tools/README.md
```

Expected: personal paths appear only in labelled personal examples; maturity labels are consistent; every apply or sync example is adjacent to a statement of its effect.

- [ ] **Step 3: Verify both test suites**

Run:

```bash
python3.12 -m pytest library-tools/tests -q
python3.12 -m pytest sample-tools/tests -q
```

Expected: both suites pass with no failures.

- [ ] **Step 4: Run final whitespace and diff review**

Run:

```bash
git diff --check
git diff --stat HEAD~5..HEAD
git status --short
```

Expected: no whitespace errors; only the planned documentation and two `pyproject.toml` files changed; the working tree is clean unless verification required a correction.

- [ ] **Step 5: Commit verification corrections if needed**

If verification required changes:

```bash
git add README.md STATUS.md docs library-tools/README.md sample-tools/README.md library-tools/pyproject.toml sample-tools/pyproject.toml
git commit -m "docs: correct documentation verification issues"
```

If no corrections were needed, do not create an empty commit.
