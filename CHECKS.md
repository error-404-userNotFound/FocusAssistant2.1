# Verification

This release retains the inherited core/action/review test suite and adds
portable installation, diagnostics, wheel-resource and app-bundle checks.
Generated test logs and previous personal-machine browser probes are intentionally
excluded from the source tree. Reproduce tests locally or inspect GitHub Actions.

Local release-preparation run (6 November 2026): **87 Python tests, six extraction
checks and the synthetic GUI smoke check passed**. A fresh Setup installation,
dependency consistency check, source/wheel build and wheel-resource verification
passed. The native **arm64 app bundle built successfully**, and its own
`--diagnose` confirmed Python/Tk, AppKit, ApplicationServices, Quartz, PyAutoGUI
and the browser resources were available from inside the bundle. That diagnostic
did not read pages, request permissions or send input. This is an ad-hoc build,
not a notarized release. Intel execution and live interventions are not covered
by that local arm64 result.

```sh
/bin/zsh Setup.command
.venv/bin/python -m unittest discover -s tests -v
node tests/extraction_checks.cjs
.venv/bin/python -m tests.ui_smoke
.venv/bin/python -m pip install -e '.[build]'
.venv/bin/python -m build
.venv/bin/python scripts/check_wheel.py
```

## Coverage

- Rule boundaries/conflicts, cache isolation, error pages, uncertain model retries
  with increasing context, strict approval parsing and full review-prompt inputs.
- Session/app transitions, pending observation recording, stale model results,
  approved correction precedence and cancellation of pending actions on pause.
- Three-stream report merge, partial prefix queries, pause-aware totals, ranking,
  queue expiry, corrupt-state preservation, record recovery and large logs.
- Injected keyboard/observer/native interfaces: mismatched app/window/tab/document
  token/content/process, late focus switch, modal rejection, final dispatch veto,
  slow imports/checks, close transition verification and guarded single-use restore.
- Explicit native/DOM full-screen exits and refusal after page changes during a
  transition, through fakes rather than physical desktop intervention.
- Exact browser text-extraction resource: DFS order, excluded nodes, traversal and
  text limits, deep nesting and empty pages.
- Synthetic GUI sessions: reminders, correction form, mocked approval, pause/end,
  reports, rankings and settings. No live keyboard/browser controls are enabled.
- Distribution checks verify packaged JavaScript resources and exclude test data.

## Evidence boundaries

A passing unit test is not a real-model accuracy result or proof of native
keyboard delivery. This repository makes no accuracy percentage claim.
Accessibility being granted to one source invocation does not establish
permission for a downloaded app bundle on another machine.

Live close/reopen, full-screen/Spaces, multiple displays, browser close-history
changes, fresh-machine permission onboarding and model/server compatibility
still require controlled manual tests on the release artifacts. The app is
experimental; see `SECURITY.md` and `docs/BEHAVIOR.md` for remaining global-key
races and restore-history limitations.

The CI matrix targets macOS Apple Silicon/Intel with Python 3.11/3.13. Only runs
actually passing are verification evidence; the presence of a workflow alone is
not a compatibility claim. App-build artifacts are not automatically notarized.
