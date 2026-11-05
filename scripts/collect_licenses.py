"""Collect public runtime/bootloader license notices into an app build directory."""
from importlib import metadata
from pathlib import Path
import json
import re
import shutil
import sys
import sysconfig
import tkinter

project = Path(__file__).resolve().parents[1]
destination = Path(sys.argv[1])
destination.mkdir(parents=True, exist_ok=True)
shutil.copy2(project / "LICENSE", destination / "FocusAssistant.txt")
index = []
for name in ("PyAutoGUI", "pytweening", "pyobjc-core", "pyobjc-framework-Cocoa",
             "pyobjc-framework-Quartz", "pyobjc-framework-ApplicationServices",
             "pyobjc-framework-CoreText", "PyInstaller"):
    distribution = metadata.distribution(name)
    output = destination / name
    output.mkdir(exist_ok=True)
    copied = []
    for item in distribution.files or []:
        if re.match(r"^(LICENSE|LICENCE|COPYING|NOTICE)([._-].*)?$", item.name, re.I) and item.suffix.lower() not in (".py", ".pyc", ".so", ".dylib", ".pyd", ".dll", ".a", ".o"):
            source = Path(distribution.locate_file(item))
            if source.is_file():
                target = output / item.name
                shutil.copyfile(source, target)
                copied.append(item.name)
    index.append({"name": name, "version": distribution.version,
                  "declared_license": distribution.metadata.get("License-Expression") or distribution.metadata.get("License", ""),
                  "home": distribution.metadata.get("Home-page", ""), "notices": sorted(set(copied))})
python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
if not python_license.is_file():
    raise SystemExit("Python's LICENSE.txt is missing from this interpreter; supply a complete Python installation before building.")
shutil.copyfile(python_license, destination / "Python-PSF.txt")
tcl = Path(tkinter.Tcl().eval("info library"))
candidates = [tcl / "license.terms", tcl.parent.parent / "license.terms",
              tcl.parent / ("tk" + str(tkinter.TkVersion)) / "demos" / "license.terms",
              project / "packaging" / "licenses" / "Tcl-Tk.txt"]
tcl_license = next((p for p in candidates if p.is_file()), None)
if tcl_license is None:
    raise SystemExit("Tcl/Tk license notice is missing.")
shutil.copyfile(tcl_license, destination / "Tcl-Tk.txt")
(destination / "components.json").write_text(json.dumps(index, indent=2) + "\n")
(destination / "README.txt").write_text(
    "Focus Assistant and third-party notices\n\n"
    "Focus Assistant is MIT licensed. Python and Tcl/Tk retain their own terms.\n"
    "PyObjC components share the PyObjC project license included with Cocoa.\n"
    "PyInstaller's bootloader license includes its distribution exception; see COPYING.txt.\n"
    "Unused MouseInfo, screenshot, popup and clipboard helper modules are excluded from this keyboard-only binary.\n"
    "Source installations resolve external dependencies separately.\n")
print("Collected application, Python/Tk, runtime dependency and bootloader notices")
