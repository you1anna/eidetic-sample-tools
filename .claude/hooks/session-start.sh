#!/bin/bash
# Cloud sessions only: build the same pinned environment the Macs use.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

"$CLAUDE_PROJECT_DIR/scripts/setup_dev_env.sh"

if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
  echo "export EIDETIC_PYTHON=\"${EIDETIC_DEV_VENV:-$HOME/.venvs/eidetic-sample-tools-dev}/bin/python\"" >> "$CLAUDE_ENV_FILE"
fi
