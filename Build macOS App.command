#!/bin/zsh
set -e
cd -- "$(dirname "$0")"
[[ "$(uname -s)" == Darwin ]] || { print -u2 "Build on macOS."; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
    /bin/zsh Setup.command
fi
.venv/bin/python -m pip install --disable-pip-version-check -e '.[build]'
# Build/sign/archive outside Finder-synced checkout folders. Only generated files
# live here; cleanup never touches a user's downloaded app or system settings.
build_root="$(mktemp -d "${TMPDIR:-/tmp}/focusassistant-build.XXXXXX")"
trap '/bin/rm -rf -- "$build_root"' EXIT
.venv/bin/python scripts/collect_licenses.py "$build_root/licenses"
export FOCUSASSISTANT_LICENSE_DIR="$build_root/licenses"
.venv/bin/python -m PyInstaller --clean --noconfirm --distpath "$build_root/dist" --workpath "$build_root/work" packaging/FocusAssistant.spec
app="$build_root/dist/Focus Assistant.app"
/usr/bin/xattr -dr com.apple.FinderInfo "$app" 2>/dev/null || true
/usr/bin/xattr -dr com.apple.ResourceFork "$app" 2>/dev/null || true
# Re-sign the outer bundle after cleanup; PyInstaller signs the embedded code.
signing_identity="${FOCUSASSISTANT_CODESIGN_IDENTITY:--}"
signing_options=()
if [[ "$signing_identity" != '-' ]]; then
    signing_options=(--options runtime --timestamp)
fi
/usr/bin/codesign --force --sign "$signing_identity" "${signing_options[@]}" --entitlements packaging/entitlements.plist "$app"
/usr/bin/codesign --verify --deep --strict "$app"
version="$(.venv/bin/python -c 'from focusassistant import __version__; print(__version__)')"
archive_file="FocusAssistant-${version}-$(uname -m).zip"
/usr/bin/ditto -c -k --norsrc --noextattr --keepParent "$app" "$build_root/$archive_file"
.venv/bin/python scripts/check_release_archive.py "$build_root/$archive_file"
/usr/bin/ditto -x -k --noextattr "$build_root/$archive_file" "$build_root/extracted"
/usr/bin/codesign --verify --deep --strict "$build_root/extracted/Focus Assistant.app"
# Verify dependency imports from the exact extracted release artifact. No UI,
# browsing session, permission prompts or input events are started.
"$build_root/extracted/Focus Assistant.app/Contents/MacOS/FocusAssistant" --diagnose
mkdir -p dist
/bin/cp "$build_root/$archive_file" "dist/$archive_file"
# A fresh copy is only a local convenience; the verified ZIP is the release asset.
/bin/rm -rf -- 'dist/Focus Assistant.app'
/usr/bin/ditto --norsrc --noextattr "$app" 'dist/Focus Assistant.app'
(
    cd dist
    /usr/bin/shasum -a 256 "$archive_file" > "${archive_file}.sha256"
)
print -- "Created dist/$archive_file (native architecture only); extracted signature/import checks passed."
print -- "Without an Apple Developer ID and notarization, this is a local/ad-hoc build, not a notarized release."
