"""macOS page observation. Keyboard/window control lives in actions.py."""
import json
from pathlib import Path
import subprocess
import sys

from .models import Snapshot

ROOT = Path(__file__).resolve().parent


class BrowserObserver:
    def __init__(self):
        self.extractor = (ROOT / "extract_text.js").read_text()

    def observe(self, foreground_only=False, metadata_only=False):
        if sys.platform != "darwin":
            raise RuntimeError("Browser observation requires macOS.")
        payload = {"action": "foreground" if foreground_only else "metadata" if metadata_only else "observe", "extractor": self.extractor}
        result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", str(ROOT / "browser_bridge.js"), json.dumps(payload)],
                                capture_output=True, text=True, timeout=8)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or "macOS browser observation failed.")
        data = json.loads(result.stdout)
        return Snapshot(**{k: v for k, v in data.items() if k in Snapshot.__dataclass_fields__})
