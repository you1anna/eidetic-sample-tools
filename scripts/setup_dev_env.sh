#!/usr/bin/env bash
# Create or refresh the pinned test environment used on every machine.
#
#   scripts/setup_dev_env.sh           # set up or verify
#   scripts/setup_dev_env.sh --force   # reinstall the pinned requirements
#
# The environment is ~/.venvs/eidetic-sample-tools-dev (override with
# EIDETIC_DEV_VENV), built from requirements-dev.txt with the four packages
# installed editable from this checkout. A stamp records the setup version,
# Python version and requirements hash; unchanged inputs skip reinstalling.
# FFmpeg/FFprobe/libsndfile are installed only on Linux as root (cloud
# sessions and CI); on macOS they are reported, never installed.
set -euo pipefail

SETUP_VERSION=1
cd "$(dirname "$0")/.."
checkout=$(pwd)
venv=${EIDETIC_DEV_VENV:-$HOME/.venvs/eidetic-sample-tools-dev}
force=false
[ "${1:-}" = "--force" ] && force=true

log() { echo "setup_dev_env: $*"; }

missing_tools=()
for tool in ffmpeg ffprobe; do
  command -v "$tool" >/dev/null 2>&1 || missing_tools+=("$tool")
done
if [ "$(uname -s)" = "Linux" ] && ! ldconfig -p 2>/dev/null | grep -q libsndfile; then
  missing_tools+=(libsndfile)
fi
if [ ${#missing_tools[@]} -gt 0 ]; then
  if [ "$(uname -s)" = "Linux" ] && [ "$(id -u)" = "0" ] && command -v apt-get >/dev/null 2>&1; then
    log "installing system tools: ffmpeg libsndfile1"
    if ! (apt-get install -y -qq ffmpeg libsndfile1 >/dev/null 2>&1 \
          || { apt-get update -qq >/dev/null 2>&1 && apt-get install -y -qq ffmpeg libsndfile1 >/dev/null 2>&1; }); then
      log "WARNING: could not install ffmpeg/libsndfile1; audio tests will fail"
    fi
  else
    log "WARNING: missing ${missing_tools[*]}; on macOS run: brew install ffmpeg"
  fi
fi

python=""
for candidate in "${EIDETIC_BASE_PYTHON:-}" python3.12; do
  if [ -n "$candidate" ] && command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; sys.exit(sys.version_info[:2] != (3, 12))'; then
    python=$(command -v "$candidate")
    break
  fi
done
if [ -z "$python" ]; then
  log "FAIL: Python 3.12 not found; install it or set EIDETIC_BASE_PYTHON"
  exit 1
fi

if [ ! -x "$venv/bin/python" ]; then
  log "creating $venv"
  "$python" -m venv "$venv"
fi

stamp_file="$venv/.eidetic-setup-stamp"
stamp="setup=$SETUP_VERSION python=$("$venv/bin/python" -c 'import platform; print(platform.python_version())') requirements=$("$venv/bin/python" -c 'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1],"rb").read()).hexdigest())' requirements-dev.txt) checkout=$checkout"
if $force || [ ! -f "$stamp_file" ] || [ "$(cat "$stamp_file")" != "$stamp" ]; then
  log "installing pinned requirements"
  "$venv/bin/python" -m pip install -q --disable-pip-version-check -r requirements-dev.txt
  "$venv/bin/python" -m pip install -q --disable-pip-version-check --no-deps \
    -e ./library-tools -e ./sample-tools -e ./ableton-tools -e ./live-tools
  "$venv/bin/python" -m pip check
  printf '%s\n' "$stamp" > "$stamp_file"
else
  log "environment already matches requirements-dev.txt"
fi

"$venv/bin/python" scripts/dev_check.py --python "$venv/bin/python" doctor
