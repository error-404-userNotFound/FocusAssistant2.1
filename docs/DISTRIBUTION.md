# macOS distribution

## Source versus binary distribution

The source is portable across checkout locations and uses a per-user data
folder. `Setup.command` installs into a local virtual environment; no developer's
virtual environment, saved sessions, logs or credentials should be distributed.
Python 3.11+ and working Tk are required for source installation.

`Build macOS App.command` installs the declared build extra, invokes PyInstaller,
collects the JavaScript resources, and produces:

- `dist/Focus Assistant.app`
- `dist/FocusAssistant-2.1.0-<architecture>.zip`
- The ZIP's SHA-256 checksum file.

The app bundles Python/Tk/dependencies. A separate local model server/model and
browser permissions are still required. The CPU architecture and minimum OS
compatibility follow the interpreter/frameworks used to build it. Build/test on
both Apple Silicon and Intel rather than renaming an arm64 artifact as universal.

The build removes only signing-prohibited FinderInfo/ResourceFork metadata from
the generated app, excludes extended metadata from the ZIP, and strictly verifies
the signature after extracting that ZIP into a temporary directory. This verifies
the delivered artifact rather than just the build folder. It does not disable
Gatekeeper or alter quarantine settings on downloaded apps.

Signing and archive creation run in a temporary staging directory, away from
Finder-synced source folders. The bundle includes a `Licenses` resource directory
with the project's license, Python/Tcl/Tk notices, runtime dependency notices and
the PyInstaller bootloader license/exception. Unused MouseInfo, screenshot,
clipboard and popup helper modules are excluded from the keyboard-only binary.

The manual GitHub build workflow uses native `macos-15` and `macos-15-intel`
runners. Build outputs are available as GitHub Actions artifacts. Building on
macOS 15 does not establish compatibility with every older OS. Declare and test
a minimum OS before distributing a release to users of older Macs.

## Signing and notarization

By default PyInstaller uses a local/ad-hoc signature where required. This is
not Apple notarization, and a downloaded binary may be blocked by Gatekeeper.
A maintainer planning a broadly downloadable binary should:

1. Obtain and configure an Apple Developer ID Application certificate locally.
2. Set `FOCUSASSISTANT_CODESIGN_IDENTITY` to that identity when building. The spec
   passes it to the native build/signing process; no certificate is committed.
3. Verify the resulting bundle's signatures/entitlements and embedded resources.
4. Submit the ZIP using Apple's notarization tooling with credentials stored in
   the Keychain or a protected CI secret, never in the repository.
5. Staple the accepted notarization ticket to the app, recreate its ZIP and
   checksum, then verify the result on a clean Mac.
6. Test fresh Automation/Accessibility onboarding and disposable tab actions.

The included entitlements allow Apple Events and loading the packaged Python
libraries under hardened-runtime signing. The app is not App Sandbox enabled;
App Store distribution is not claimed. The Info.plist explains browser access.
No signing identity, provisioning material, notary credentials or public release
is created by this source preparation.

See the primary [PyInstaller macOS signing notes](https://pyinstaller.org/en/stable/feature-notes.html#macos-binary-code-signing)
and [Apple notarization documentation](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution).

## Release checklist

- Core tests, extraction checks and wheel-resource checks pass.
- Native app is built for the declared CPU/OS targets, with dependencies included.
- Real-model retries and approval decisions have been checked with synthetic data.
- Full-screen/Spaces, focus switches, pause cancellation and recovery are tested
  with disposable browser tabs. Do not use private or unsaved pages for these.
- Signing/notarization status is disclosed accurately; signature checks pass.
- Artifact contains no state files, local logs, credentials or developer paths.
- Users can find permission instructions, privacy information and safety limits.
- Publish release files only after repository access/visibility is intentionally set.
