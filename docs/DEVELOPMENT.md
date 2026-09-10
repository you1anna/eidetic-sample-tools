# Development and release checks

Use Python 3.12, FFmpeg and FFprobe. Keep environments on the current machine's
local disk; library data and portable state belong on the sample drive. Never use
real sample libraries as test fixtures or commit generated library state.

The [September 2026 review](REVIEW-2026-09-09.md) records installation and data
maintenance findings, verification and remaining work.

## Fast local checks

Use the existing environment before setting up another one:

```bash
python3 scripts/dev_check.py doctor
python3 scripts/dev_check.py test -- library-tools/tests/test_collection_plan.py -q
python3 scripts/dev_check.py test
```

`doctor` reports the selected Python 3.12 virtual environment, dependency
availability, FFmpeg/FFprobe and all four source import paths. It does not load
models, install dependencies or inspect the sample drive. The helper tries the
current/active environment, then `~/.venvs/eidetic-sample-tools-dev`, `eidetic-ai`
and `library-tools`. Set `EIDETIC_PYTHON` or put `--python /path/to/venv/bin/python`
before the subcommand to choose explicitly; a broken explicit choice is an error.
`doctor --json` provides the same information for local tooling.

`test` works from any working directory when the script path is absolute. It uses
this checkout's four source directories even if older wheels are installed.
Arguments after `--` replace the default combined suite; pytest's exit status is
preserved. Use focused checks while editing, then run the relevant final suite
once. Repeat checks after a change or failure, not merely to accumulate passes.

## Reproduce the test environment

From the repository root:

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools-dev"
source "$HOME/.venvs/eidetic-sample-tools-dev/bin/activate"
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e ./library-tools -e ./sample-tools -e ./ableton-tools -e ./live-tools
python -m pip check
python -m pytest library-tools sample-tools ableton-tools live-tools -q -rs
```

The combined environment exercises the handoff between packages. Existing
package-specific environments also work for their individual suites. Two optional
CLAP checks download and run model checkpoints; the standard suite skips them.
Hardware playback and save/reload checks remain separate from software tests.

## Verify installed packages

Build all four wheels, install the core and optional layers separately in a fresh
environment, and run the same
smoke check used by CI:

```bash
CHECKOUT_DIR="$PWD"
WHEEL_DIR="$(mktemp -d)"
python -m pip wheel --no-deps --wheel-dir "$WHEEL_DIR" ./library-tools ./sample-tools ./ableton-tools ./live-tools
python3.12 -m venv "$WHEEL_DIR/venv"
CHECK_PYTHON="$WHEEL_DIR/venv/bin/python"
"$CHECK_PYTHON" -m pip install -c "$CHECKOUT_DIR/requirements-dev.txt" \
  "$WHEEL_DIR/"/librarytools-*.whl "$WHEEL_DIR/"/sampletools-*.whl "$WHEEL_DIR/"/abletontools-*.whl
"$CHECK_PYTHON" -m pip check
cd "$WHEEL_DIR"
env -u PYTHONPATH -u PYTHONHOME "$CHECK_PYTHON" "$CHECKOUT_DIR/scripts/check_installed_packages.py" --core-only
"$CHECK_PYTHON" -m pip install -c "$CHECKOUT_DIR/requirements-dev.txt" \
  --find-links "$WHEEL_DIR" 'librarytools[review-ui,live]'
"$CHECK_PYTHON" -m pip check
env -u PYTHONPATH -u PYTHONHOME "$CHECK_PYTHON" "$CHECKOUT_DIR/scripts/check_installed_packages.py"
cd "$CHECKOUT_DIR"
```

Use a fresh wheel-check environment; reusing one with development dependencies
can hide undeclared runtime imports. Constraints limit versions without installing
unused packages. The base check must pass before installing `review-ui` and `live`;
it asserts that neither Flask nor `eidetic-live-tools` leaked into the ordinary CLI
install. The second check imports all four installed packages, exercises browser
resources and probes the Live API and command help without requiring a running Set.

The check rejects editable imports. It verifies installed commands and resources,
onboards two synthetic machines in sequence, scans generated audio, checks approval
requirements, converts with FFmpeg, reuses exports after a changed mount path, and
verifies historical capture, backup and restore. Its temporary library is removed
when the check ends.

Collection planning is exercised through its installed console command in both
modes, including alias deduplication, actual export-receipt history, shortages and
offline regeneration with pins. Both checks run outside the checkout with Python
path overrides cleared. Reusing operational wheels is a useful integration check,
but it does not prove a fresh dependency installation; CI retains that boundary.

The [CI workflow](../.github/workflows/tests.yml) runs the suite and installed-package
check on macOS and Linux. A local pass does not establish that a remote CI run has
completed.

## Compare collection-planner performance

Use the same environment discovery for a repeatable benchmark:

```bash
python3 scripts/dev_check.py benchmark
python3 scripts/dev_check.py benchmark -- --identities 1000 --count 100 --history 24 --pins 10
```

The default builds a temporary SQLite fixture with 22,000 distinct identities,
one exact alias and 240 previous exports, then selects 1,000 candidates and retains
10 pins across regeneration. It creates no audio and accepts no real library path.
JSON on stdout records configuration, Python/platform, Git revision, dirty state,
artifact sizes and median stage times over three runs; `--repeats` changes that
count. Save comparisons outside the repository when useful.

Timings include the public planner's validation and actual writes with `fsync`.
Separate checks verify aliases, exclusions, shortages, reproducibility, parent
lineage, unreviewed pins, offline regeneration and unchanged parent/index files.
Temporary artifacts are removed. Small-fixture regression tests run in the normal
suite; the 22,000-identity benchmark is explicit and has no timing pass threshold.
Compare like configurations on the same machine. These measurements cover
metadata planning, not AI inference, musical quality, listening time or exports.

## Dependency ownership and updates

Each package's `pyproject.toml` owns its runtime requirements and optional extras.
`sampletools`, `abletontools` and `eideticlive` have no third-party Python runtime dependencies;
`librarytools` needs NumPy and SoundFile. FFmpeg/FFprobe remain system dependencies.
The library's `dev` extra includes pytest and Flask for browser tests; model
dependencies are separate and are not needed for the standard suite. Its `live`
extra adds Flask and the exactly matched `eidetic-live-tools` distribution.

The [AI setup](AI-SETUP.md) has a separate, hash-verified Apple Silicon
snapshot, generated from package extras, and an explicitly triggered real-model
CI workflow. Keep this separate from the lightweight default test environment.

`requirements-dev.txt` is the pinned Python 3.12 test snapshot, including transitive
dependencies. It is not a hash-verified lockfile or a model-environment lock. Do not
maintain a second runtime dependency list in `sample-tools/requirements.txt`.

To refresh the snapshot, create a fresh local environment, install
`-e './library-tools[dev,live]' -e './sample-tools[dev]' -e './ableton-tools[dev]' -e './live-tools[dev]'`, and run
`python -m pip check` and the combined test suite. Capture
`python -m pip freeze --exclude-editable` as the candidate `requirements-dev.txt`.
Review version changes and rerun the fresh wheel checks on macOS and Linux before
adopting it. Update package requirements first when changing supported dependency
ranges. Update optional model dependencies through their own hashed snapshot and
real-model tests; checkpoint pins alone do not pin the inference environment.

## Before committing a release

- Run the suite and installed-package check against the final code.
- Keep package versions, bundled resources and the [changelog](../CHANGELOG.md)
  consistent. Tests compare copied profiles and manifests with canonical sources.
- Run `git diff --check` and inspect new files for generated or private evidence.
- Keep migrations explicit, previews intact, and backups and recovery reproducible.
- Preserve dated operational findings in [STATUS.md](../STATUS.md); passing tests
  do not resolve a live-library discrepancy.

Package publication and live-library onboarding are separate actions. Follow the
[lifecycle guide](LIFECYCLE.md) for per-machine installation and historical state.
