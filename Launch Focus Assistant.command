#!/bin/zsh
set -e
cd -- "$(dirname "$0")"
if [[ -n "$FOCUSASSISTANT_PYTHON" ]]; then
    exec "$FOCUSASSISTANT_PYTHON" run.py
elif [[ -x .venv/bin/python ]]; then
    exec .venv/bin/python run.py
else
    print -u2 -- "Run Setup.command first to install this project's dependencies in .venv."
    exit 1
fi
