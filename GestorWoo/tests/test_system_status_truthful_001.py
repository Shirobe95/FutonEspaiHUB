"""Valores mostrados: el estado del sistema del panel no afirma lo que no comprueba."""
from __future__ import annotations

import sys
import tkinter as tk
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp.prototype import FutonHubErpPrototype as P  # noqa: E402


class Shell:
    def __init__(self, parent, session) -> None:
        self.rows: dict[str, tuple[str, str]] = {}
        self._cloud_session = session
        self.parent = parent

    def _card(self, parent):
        return tk.Frame(parent)

    def _status_row(self, parent, label, detail, status):
        self.rows[label] = (detail, status)
        return tk.Frame(parent)


class SystemStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            self.root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(str(exc))
        self.addCleanup(self.root.destroy)

    def rows(self, session):
        shell = Shell(self.root, session)
        P._system_status(shell, self.root)
        return shell.rows

    def test_without_session_supabase_is_not_reported_connected(self) -> None:
        rows = self.rows(None)
        self.assertEqual(rows["Supabase"], ("Sin sesion", "Info"))

    def test_with_session_it_says_session_active_and_nothing_unverified(self) -> None:
        rows = self.rows(object())
        self.assertEqual(rows["Supabase"], ("Sesion activa", "OK"))
        self.assertNotIn("disponible", rows["WooCommerce"][0].lower())
        self.assertEqual(rows["WooCommerce"][1], "Info")
        self.assertEqual(rows["Locks"], ("No comprobado", "Info"))


if __name__ == "__main__":
    unittest.main()
