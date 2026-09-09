# Development and release checks

Use Python 3.12, FFmpeg and FFprobe. Keep environments on the current machine's
local disk; library data and portable state belong on the sample drive. Never use
real sample libraries as test fixtures or commit generated library state.

## Reproduce the test environment

From the repository root:

```bash
python3.12 -m venv "$HOME/.venvs/eidetic-sample-tools-dev"
source "$HOME/.venvs/eidetic-sample-tools-dev/bin/activate"
python -m pip install -r requirements-dev.txt
python -m pip install --no-deps -e ./library-tools -e ./sample-tools -e ./ableton-tools
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
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip install -r requirements-dev.txt
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" -m pip install --force-reinstall --no-deps "$WHEEL_DIR/"*.whl
"$HOME/.venvs/eidetic-sample-tools-wheel-check/bin/python" scripts/check_installed_packages.py
```

The check rejects editable imports. It verifies installed commands and resources,
onboards two synthetic machines in sequence, scans generated audio, checks approval
requirements, converts with FFmpeg, reuses exports after a changed mount path, and
verifies historical capture, backup and restore. Its temporary library is removed
when the check ends.

The [CI workflow](../.github/workflows/tests.yml) runs the suite and installed-package
check on macOS and Linux. A local pass does not establish that a remote CI run has
completed.

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
