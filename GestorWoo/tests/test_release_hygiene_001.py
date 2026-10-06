"""Higiene de release (auditoria 2026-10, corte 4)."""
from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import futonhub  # noqa: E402
import gestorwoo  # noqa: E402
from futonhub.version_info import app_version_label, deployed_commit  # noqa: E402


class VersionConsistencyTests(unittest.TestCase):
    def test_all_version_sources_agree(self) -> None:
        pyproject = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.M)
        changelog = re.search(r"^## (\d+\.\d+\.\d+)\b", (REPO / "CHANGELOG.md").read_text(encoding="utf-8"), re.M)
        self.assertIsNotNone(pyproject)
        self.assertIsNotNone(changelog)
        self.assertEqual(
            {pyproject.group(1), futonhub.__version__, gestorwoo.__version__, changelog.group(1)},
            {futonhub.__version__},
        )

    def test_obsolete_manifest_is_not_tracked(self) -> None:
        self.assertFalse((REPO / "MANIFEST_SHA256.txt").exists())

    def test_gitignore_covers_virtualenvs_and_secrets(self) -> None:
        lines = {line.strip() for line in (REPO / ".gitignore").read_text(encoding="utf-8").splitlines()}
        for entry in (".env", "*.sqlite3", ".venv*/"):
            self.assertIn(entry, lines)


class AppVersionLabelTests(unittest.TestCase):
    def test_label_without_deployed_commit(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(app_version_label(Path(temp)), f"v{futonhub.__version__}")

    def test_label_with_deployed_commit_from_launcher(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "SOURCE_COMMIT").write_text("a1b2c3d4e5f6" + "0" * 28 + "\n", encoding="ascii")
            self.assertEqual(app_version_label(Path(temp)), f"v{futonhub.__version__} · a1b2c3d4e5f6")

    def test_invalid_commit_file_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / "SOURCE_COMMIT").write_text("not-a-sha\n", encoding="ascii")
            self.assertEqual(deployed_commit(Path(temp)), "")

    def test_main_window_title_shows_the_version(self) -> None:
        source = (SRC / "futonhub" / "ui" / "erp" / "prototype.py").read_text(encoding="utf-8")
        self.assertIn('self.title(f"FutonHUB ERP {app_version_label()}")', source)


if __name__ == "__main__":
    unittest.main()
