# Development and release checks

Use Python 3.12, FFmpeg and FFprobe. Keep environments on the current machine's
local disk; library data and portable state belong on the sample drive. Never use
real sample libraries as test fixtures or commit generated library state.

The [September 2026 review](REVIEW-2026-09-09.md) records installation and data
maintenance findings, verification and remaining work.

## Reproduce the test environment

From the repository root:

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools-dev"
source "$HOME/.venvs/eidetic-sample-tools-dev/bin/activate"
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e ./library-tools -e ./sample-tools -e ./ableton-tools
python -m pip check
python -m pytest library-tools sample-tools ableton-tools -q -rs
```

The combined environment exercises the handoff between packages. Existing
package-specific environments also work for their individual suites. Two optional
CLAP checks download and run model checkpoints; the standard suite skips them.
Hardware playback and save/reload checks remain separate from software tests.

## Verify installed packages

Build all three wheels, install them in a separate environment, and run the same
smoke check used by CI:

```bash
WHEEL_DIR="$(mktemp -d)"
python -m pip wheel --no-deps --wheel-dir "$WHEEL_DIR" ./library-tools ./sample-tools ./ableton-tools
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools-wheel-check"
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip install -c requirements-dev.txt "$WHEEL_DIR/"*.whl
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip check
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" scripts/check_installed_packages.py --core-only
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip install -c requirements-dev.txt --find-links "$WHEEL_DIR" 'librarytools[review-ui]'
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip check
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" scripts/check_installed_packages.py
```

Use a fresh wheel-check environment; reusing one with development dependencies
can hide undeclared runtime imports. Constraints limit versions without installing
unused packages. The base check must pass before installing `review-ui`, so browser
dependencies cannot accidentally become mandatory for ordinary CLI use.

The check rejects editable imports. It verifies installed commands and resources,
onboards two synthetic machines in sequence, scans generated audio, checks approval
requirements, converts with FFmpeg, reuses exports after a changed mount path, and
verifies historical capture, backup and restore. Its temporary library is removed
when the check ends.

The [CI workflow](../.github/workflows/tests.yml) runs the suite and installed-package
check on macOS and Linux. A local pass does not establish that a remote CI run has
completed.

## Dependency ownership and updates

Each package's `pyproject.toml` owns its runtime requirements and optional extras.
`sampletools` and `abletontools` have no third-party Python runtime dependencies;
`librarytools` needs NumPy and SoundFile. FFmpeg/FFprobe remain system dependencies.
The library's `dev` extra includes pytest and Flask for browser tests; model
dependencies are separate and are not needed for the standard suite.

The optional [AI setup](AI-SETUP.md) now has a separate, hash-verified Apple Silicon
snapshot, generated from package extras, and an explicitly triggered real-model
CI workflow. Keep this separate from the lightweight default test environment.

`requirements-dev.txt` is the pinned Python 3.12 test snapshot, including transitive
dependencies. It is not a hash-verified lockfile or a model-environment lock. Do not
maintain a second runtime dependency list in `sample-tools/requirements.txt`.

To refresh the snapshot, create a fresh local environment, install
`-e './library-tools[dev]' -e './sample-tools[dev]' -e './ableton-tools[dev]'`, and run
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
