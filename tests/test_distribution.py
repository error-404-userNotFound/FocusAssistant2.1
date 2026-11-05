"""Portable startup and diagnostic checks without browser or input access."""
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from focusassistant import __version__
from focusassistant import diagnostics


class DistributionTests(unittest.TestCase):
    def test_cli_version_does_not_start_ui(self):
        result = subprocess.run([sys.executable, "-m", "focusassistant", "--version"], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), __version__)

    def test_diagnostics_does_not_require_permission_to_be_granted(self):
        fake = SimpleNamespace(AXIsProcessTrusted=lambda: False)
        with patch.object(diagnostics.importlib, "import_module", return_value=fake):
            result = diagnostics.report()
        self.assertFalse(result["checks"]["accessibility_trusted"])
        self.assertEqual(result["checks"]["pyautogui"], "available")
        self.assertTrue(result["checks"]["browser_resources"])

    def test_diagnostics_reports_missing_dependency_instead_of_crashing(self):
        with patch.object(diagnostics.importlib, "import_module", side_effect=ImportError("missing fixture module")):
            result = diagnostics.report()
        self.assertIn("unavailable", result["checks"]["pyautogui"])
        self.assertNotIn("accessibility_trusted", result["checks"])

    def test_diagnostic_exit_status_distinguishes_missing_installation(self):
        with patch.object(diagnostics, "report", return_value={"checks":{"browser_resources":False}}), patch("builtins.print"):
            self.assertEqual(diagnostics.main(), 1)

    def test_source_contains_no_development_home_paths(self):
        project = Path(__file__).resolve().parents[1]
        candidates = list((project / "focusassistant").glob("*.py")) + list((project / "focusassistant").glob("*.js"))
        candidates += [project / "README.md"]
        for path in candidates:
            with self.subTest(path=path.name):
                self.assertNotIn("/Users/", path.read_text())


if __name__ == "__main__":
    unittest.main()
