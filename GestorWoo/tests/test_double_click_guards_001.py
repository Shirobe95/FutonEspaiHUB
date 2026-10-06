"""U6: un segundo clic mientras un guardado sigue en curso no lanza otra escritura."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp import inventory_edit  # noqa: E402


class FakeReview:
    def __init__(self) -> None:
        self.children: list = []

    def winfo_children(self):
        return self.children

    def update_idletasks(self) -> None:
        pass

    def winfo_exists(self) -> bool:
        return True


class Shell:
    def __init__(self) -> None:
        self._cloud_session = SimpleNamespace()

    def after(self, _ms, fn):
        fn()


class DoubleClickTests(unittest.TestCase):
    def test_second_click_does_not_start_a_second_write(self) -> None:
        shell, review = Shell(), FakeReview()
        started: list[int] = []

        class FakeThread:
            def __init__(self, target, daemon=None):
                self.target = target

            def start(self):
                started.append(1)  # no se ejecuta el hilo: sigue "en curso"

        item = SimpleNamespace(code="7")
        with patch.object(inventory_edit.threading, "Thread", FakeThread):
            apply = inventory_edit.ErpInventoryEditMixin._apply_inventory_detail_changes
            apply(shell, review, item, {"name": ("a", "b")}, None)
            apply(shell, review, item, {"name": ("a", "b")}, None)
        self.assertEqual(len(started), 1)


if __name__ == "__main__":
    unittest.main()
