"""Non-interactive installation report. Never reads pages or sends input."""
import importlib
import json
import platform
from pathlib import Path
import sys

from . import __version__


def report():
    checks = {}
    for module in ("tkinter", "AppKit", "ApplicationServices", "Quartz", "pyautogui"):
        try:
            imported = importlib.import_module(module)
            checks[module] = "available"
            if module == "ApplicationServices":
                checks["accessibility_trusted"] = bool(imported.AXIsProcessTrusted())
        except Exception as exc:
            checks[module] = f"unavailable: {type(exc).__name__}: {exc}"
    checks["browser_resources"] = all(Path(__file__).with_name(name).is_file() for name in
        ("browser_bridge.js", "browser_control.js", "extract_text.js"))
    return {"version": __version__, "macos": platform.mac_ver()[0], "architecture": platform.machine(),
            "python": platform.python_version(), "bundled": bool(getattr(sys, "frozen", False)), "checks": checks}


def main():
    result = report()
    print(json.dumps(result, indent=2))
    return 0 if result["checks"]["browser_resources"] and all(
        result["checks"].get(name) == "available" for name in ("tkinter", "AppKit", "ApplicationServices", "Quartz", "pyautogui")) else 1
