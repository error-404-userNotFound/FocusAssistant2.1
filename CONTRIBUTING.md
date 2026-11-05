# Contributing

Run `Setup.command`, then use the project's `.venv/bin/python` for development.

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/extraction_checks.cjs
.venv/bin/python -m tests.ui_smoke
```

The GUI check uses synthetic temporary data. Unit tests inject fake input devices;
they must never send real shortcuts to a developer's browser. Live intervention
tests require disposable tabs and explicit awareness of the active desktop.

Preserve fail-closed target/focus checks, opt-in auto-close defaults, local-only
networking, the PyAutoGUI fail-safe and model approval for corrections. Do not
replace a failed identity check with a best-guess target or blind shortcut.

Include tests for behavior changes. Keep saved sessions, captured pages, local
logs, `.venv`, signing material and credentials out of commits/issues. Screenshots
and diagnostic output should be reviewed for private information before sharing.

Build instructions and release limitations are in `docs/DISTRIBUTION.md`.
Contributions are accepted under the project's MIT license.
