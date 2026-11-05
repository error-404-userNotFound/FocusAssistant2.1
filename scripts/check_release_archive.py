"""Verify release archive structure/notices before publishing it."""
from pathlib import Path, PurePosixPath
import plistlib
import sys
import zipfile

path = Path(sys.argv[1])
prefix = "Focus Assistant.app/Contents/Resources/"
with zipfile.ZipFile(path) as archive:
    names = set(archive.namelist())
    expected = {prefix + "Licenses/" + name for name in ("FocusAssistant.txt", "Python-PSF.txt", "Tcl-Tk.txt", "components.json")}
    expected |= {prefix + "focusassistant/" + name for name in ("browser_bridge.js", "browser_control.js", "extract_text.js")}
    assert expected <= names, f"Missing release resources: {expected - names}"
    assert not any(name.startswith("__MACOSX/") for name in names), "Extended resource metadata was archived"
    assert not any(".." in PurePosixPath(name).parts or name.startswith("/") for name in names), "Unsafe archive path"
    assert not any("/Licenses/" in name and Path(name).suffix.lower() in (".so", ".dylib", ".pyd", ".dll", ".pyc") for name in names), "Code was mistakenly collected as a license notice"
    info = plistlib.loads(archive.read("Focus Assistant.app/Contents/Info.plist"))
    assert info["CFBundleIdentifier"] == "io.github.focusassistant.desktop"
    assert info["CFBundleShortVersionString"] == "2.1.0"
print("Release archive resources, notices, metadata and path boundaries verified")
