"""Build on a Mac of the desired architecture; no cross-compilation is claimed."""
import os
from pathlib import Path

project = Path(SPECPATH).parent
identity = os.environ.get("FOCUSASSISTANT_CODESIGN_IDENTITY") or None
entitlements = str(project / "packaging" / "entitlements.plist")
analysis = Analysis(
    [str(project / "run.py")],
    pathex=[str(project)],
    binaries=[],
    datas=[(str(path), "focusassistant") for path in (project / "focusassistant").glob("*.js")]
          + [(os.environ["FOCUSASSISTANT_LICENSE_DIR"], "Licenses")],
    hiddenimports=["AppKit", "ApplicationServices", "Quartz", "pyautogui", "pyautogui._pyautogui_osx",
                   "tkinter", "tkinter.ttk", "tkinter.messagebox"],
    hookspath=[],
    # Keyboard-only use: do not redistribute unused popup, screenshot, clipboard
    # or MouseInfo helpers. PyAutoGUI supports their absence through ImportError.
    excludes=["tests", "pytest", "mouseinfo", "pygetwindow", "pyrect", "pyscreeze", "pymsgbox", "PIL", "rubicon", "pyperclip"],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz, analysis.scripts, [],
    exclude_binaries=True,
    name="FocusAssistant",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    argv_emulation=False,  # Tk handles Apple Events; do not consume them in the bootloader.
    target_arch=None,
    codesign_identity=identity,
    entitlements_file=entitlements,
)
collection = COLLECT(executable, analysis.binaries, analysis.datas, strip=False, upx=False, name="FocusAssistant")
application = BUNDLE(
    collection,
    name="Focus Assistant.app",
    bundle_identifier="io.github.focusassistant.desktop",
    version="2.1.0",
    info_plist={
        "CFBundleShortVersionString": "2.1.0",
        "NSHumanReadableCopyright": "Copyright 2026 Focus Assistant contributors. MIT License.",
        "NSHighResolutionCapable": True,
        "LSApplicationCategoryType": "public.app-category.productivity",
        "NSAppleEventsUsageDescription": "Focus Assistant reads the active Safari or Chrome page to compare it with your focus task and supports optional browser control.",
    },
)
