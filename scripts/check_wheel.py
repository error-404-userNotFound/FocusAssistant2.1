"""Check distribution contents without installing or running browser control."""
from pathlib import Path
import zipfile

wheel = next(Path("dist").glob("*.whl"))
with zipfile.ZipFile(wheel) as archive:
    names = set(archive.namelist())
    required = {"focusassistant/" + name for name in
                ("browser_bridge.js", "browser_control.js", "extract_text.js", "diagnostics.py")}
    assert required <= names, f"Missing distribution files: {required - names}"
    assert not any(name.startswith(("tests/", "checks/", ".venv/")) for name in names)
print("Wheel resources and source-only boundaries verified")
