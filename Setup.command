#!/bin/zsh
# Install only into this checkout; never sudo/pip-install into system Python.
set -e
cd -- "$(dirname "$0")"
fail() { print -u2 -- "$1"; exit 1; }
[[ "$(uname -s)" == Darwin ]] || fail "Focus Assistant requires macOS."
python_bin="${FOCUSASSISTANT_PYTHON:-python3}"
command -v "$python_bin" >/dev/null 2>&1 || fail "Install Python 3.11+ from https://www.python.org/downloads/macos/ and run Setup again."
"$python_bin" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11 or newer is required"; import tkinter' || fail "Use Python 3.11+ with Tk support. The standard python.org macOS installer includes Tk."
mkdir .setup.lock 2>/dev/null || fail "Another setup may be running. If no setup is running, remove the empty .setup.lock directory and retry."
trap 'rmdir .setup.lock 2>/dev/null || true' EXIT
if [[ ! -x .venv/bin/python ]]; then
    "$python_bin" -m venv .venv
fi
.venv/bin/python -m pip install --disable-pip-version-check -e .
.venv/bin/python -m pip check
.venv/bin/python -m focusassistant --diagnose
print -- "Setup complete. Double-click Launch Focus Assistant.command."
