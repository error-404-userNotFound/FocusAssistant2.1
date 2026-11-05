# Focus Assistant

**Experimental macOS focus assistant · Python · Safari and Google Chrome · local inference**

Describe the task you want to focus on. Focus Assistant observes the **single
active browser page**, classifies it against your task through rules, cached
decisions and a local OpenAI-compatible model server, then displays a reminder
or optionally closes a verified distracting tab. No browser extension is needed.

Features:

- Focus sessions with pause/resume, saved reports, timelines and time-range totals.
- Local domain/keyword rules and task/page/content-sensitive classification cache.
- Up to three uncertain-result assessments with increasing captured context.
- Visible correction applications requiring a written reason and LLM approval.
- **Opt-in, off-by-default** guarded Command-W and conditional recovery through
  Command-Shift-T after an approved correction.
- Native/DOM full-screen exit before reminders, with Space-aware warning panels.

This is a personal focus tool, not a security boundary. Keyboard shortcuts cannot
atomically lock focus to a tab, LLM decisions can be wrong, and closing a tab may
lose unsaved data. Read [behavior and safety](docs/BEHAVIOR.md) and
[verification limits](CHECKS.md) before enabling automatic closing.

## Requirements

- macOS with a supported **Python 3.11+ installation including Tk** for source use.
  Apple Silicon and Intel are targeted; the CI matrix covers both architectures.
- Safari or Google Chrome. Other browser families are not yet supported.
- A local OpenAI-compatible chat-completions server, such as LM Studio, with an
  appropriate text model loaded. Model/server availability and performance depend
  on your hardware; neither is bundled with the app.
- Internet access during dependency installation. Normal classification requests
  go only to the configured loopback server.

The [python.org macOS installers](https://www.python.org/downloads/macos/) include
Tk; see [Python's macOS/Tk guidance](https://www.python.org/download/mac/tcltk/).
A system Python or package-manager Python may have a different Tk installation.

## Download and run from source

Download this repository as a ZIP and extract it, or clone it. Open Terminal in
the extracted project folder and run:

```sh
/bin/zsh Setup.command
/bin/zsh 'Launch Focus Assistant.command'
```

You can also double-click those scripts in Finder when executable permissions
are preserved. Setup creates **only a project-local `.venv`**, checks Python/Tk,
installs declared dependencies, and prints a local diagnostic report. It does not
use sudo, grant permissions, install models or send browser input.

After setup, these commands are equivalent:

```sh
.venv/bin/python run.py
.venv/bin/python -m focusassistant
```

For a specific Python, set `FOCUSASSISTANT_PYTHON` when running Setup. The launcher
normally uses `.venv`; its interpreter override is intended for development.
If you move the checkout, recreate `.venv` with Setup rather than copying a
virtual environment from another computer.

## First session and permissions

1. Start your local model server and load a text instruction model.
2. In **Settings**, check `http://127.0.0.1:1234/v1` (or your local server's URL),
   select the available model, and save. Only loopback addresses are accepted.
3. Start a focus session and switch to Safari or Chrome. Grant browser
   **Automation** access when macOS requests it.
4. Grant **Accessibility** to the actual launcher/app under System Settings →
   Privacy & Security for native focus checks, full-screen exit and keyboard
   control. Source and bundled launches may have different permission entries.
5. For Chrome text extraction, enable View → Developer → **Allow JavaScript from
   Apple Events**. Safari can read native text without it, but **automatic closing
   requires JavaScript automation in either browser** to verify document identity.

Screen Recording is not needed. The app never changes these settings itself.
Without sufficient access, the status explains why an observation/action was
refused. Missing identity or changed focus must not be replaced with a guessed
close target.

Auto-close is disabled by default. Configure rules if wanted, and initially try
warning-only mode with disposable pages. A model that spends all its output
budget on reasoning may need thinking disabled or a larger context configuration
in the server. Connection/model errors remain uncertain; they are not counted as
three valid semantic uncertainty responses.

The main app must keep running. Closing its main window ends the session and
quits. It is not an always-on background service.

## Data and privacy

Default state: `~/Library/Application Support/FocusAssistant/state.json`.
This is separate from the earlier development copy. For an isolated store:

```sh
.venv/bin/python run.py --data-dir ./data
```

Tasks, page URLs/titles, labels, review reasons and activity records are stored
locally. Page bodies and recovery receipts stay in memory. There is no telemetry
or automatic upload. A local server can itself log/forward data; configure it
separately. See [PRIVACY.md](PRIVACY.md).

## Installation diagnostics

```sh
.venv/bin/python -m focusassistant --version
.venv/bin/python -m focusassistant --diagnose
```

Diagnostics checks imports/resources and permission status. It does not open a
focus session, read pages, request permissions or send keys. A false Accessibility
status means permission still needs to be granted, not that installation failed.
Review diagnostic output for private paths in error messages before sharing it.

## Standalone `.app` builds

The source checkout is ready for installation through Setup. A separate build
recipe produces a Python-bundled macOS app and ZIP:

```sh
/bin/zsh 'Build macOS App.command'
```

Build on each desired CPU architecture; an arm64 build is not automatically an
Intel build. The manual **Build macOS apps** GitHub workflow builds separate
Apple Silicon/Intel artifacts. It does not publish a release or change repository
visibility. Private-repository artifacts require repository access.

An ad-hoc/local build is **not Developer-ID signed and notarized**. Smooth public
binary distribution still requires signing, notarization and testing the stated
minimum OS/hardware configurations. See [distribution instructions](docs/DISTRIBUTION.md).
Never disable Gatekeeper globally to install this project.

## Development and verification

```sh
.venv/bin/python -m unittest discover -s tests -v
node tests/extraction_checks.cjs       # optional test-only Node dependency
.venv/bin/python -m tests.ui_smoke     # synthetic GUI check, no live controls
```

GitHub Actions runs core/extraction/package checks on Apple Silicon and Intel
macOS runners. Passing injected-interface tests does not establish live
close/reopen, multiple-Space behavior or model accuracy. See [CHECKS.md](CHECKS.md).

Architecture and the detailed correction/recovery safeguards are documented in
[docs/BEHAVIOR.md](docs/BEHAVIOR.md). For changes and contributions, see
[CHANGELOG.md](CHANGELOG.md) and [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE). Third-party Python packages and model weights retain their own
licenses. This repository does not include model weights or redistribute a local
model server. Repository visibility is independent of the source license; a
private repository is accessible only to people you authorize.
