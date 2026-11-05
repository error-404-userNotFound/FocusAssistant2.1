#!/bin/zsh
set -e
cd -- "$(dirname "$0")"
[[ "$(uname -s)" == Darwin ]] || { print -u2 "Build on macOS."; exit 1; }
if [[ ! -x .venv/bin/python ]]; then
    /bin/zsh Setup.command
fi
.venv/bin/python -m pip install --disable-pip-version-check -e '.[build]'
.venv/bin/python -m PyInstaller --clean --noconfirm --distpath dist --workpath build/app packaging/FocusAssistant.spec
# Remove only Finder/resource-fork detritus in this generated bundle. Preserve
# quarantine and other security metadata; never disable Gatekeeper.
/usr/bin/xattr -dr com.apple.FinderInfo "dist/Focus Assistant.app" 2>/dev/null || true
/usr/bin/xattr -dr com.apple.ResourceFork "dist/Focus Assistant.app" 2>/dev/null || true
/usr/bin/codesign --verify --deep --strict "dist/Focus Assistant.app"
version="$(.venv/bin/python -c 'from focusassistant import __version__; print(__version__)')"
archive="dist/FocusAssistant-${version}-$(uname -m).zip"
/usr/bin/ditto -c -k --sequesterRsrc --keepParent "dist/Focus Assistant.app" "$archive"
/usr/bin/shasum -a 256 "$archive" > "${archive}.sha256"
print -- "Created $archive (native architecture only)."
print -- "Without an Apple Developer ID and notarization, this is a local/ad-hoc build, not a notarized release."
