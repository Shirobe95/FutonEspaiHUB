"""U1: tras logout/login las generaciones no pueden volver a un valor ya usado.

Si vuelven a 0/1, un hilo lanzado por el usuario anterior pasa el filtro
``generation != actual`` y pinta sus datos al usuario siguiente.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402

GENERATIONS = (
    "_price_catalog_generation",
    "_price_filter_metadata_generation",
    "_price_items_generation",
    "_price_live_sync_generation",
    "_price_refresh_generation",
    "_price_detail_generation",
)


class Shell:
    """Objeto mínimo: ejecuta el reseteo real sin construir la ventana Tk."""

    def __getattr__(self, name):  # los helpers de UI no importan aquí
        if name.startswith("_") and name not in self.__dict__:
            return lambda *a, **k: None
        raise AttributeError(name)


class LogoutGenerationTests(unittest.TestCase):
    def reset(self, shell: Shell) -> None:
        FutonHubErpPrototype._reset_session_state_after_logout(shell)

    def test_generations_never_go_backwards_after_logout(self) -> None:
        shell = Shell()
        for name in GENERATIONS:
            setattr(shell, name, 5)
        self.reset(shell)
        for name in GENERATIONS:
            self.assertGreater(getattr(shell, name), 5, name)

    def test_stale_thread_of_previous_user_is_discarded(self) -> None:
        shell = Shell()
        shell._price_detail_generation = 1  # el hilo del usuario A capturó 1
        stale = shell._price_detail_generation
        self.reset(shell)
        self.assertNotEqual(shell._price_detail_generation, stale)

    def test_repeated_logouts_keep_increasing(self) -> None:
        shell = Shell()
        seen = set()
        for _ in range(3):
            self.reset(shell)
            value = shell._price_refresh_generation
            self.assertNotIn(value, seen)
            seen.add(value)


if __name__ == "__main__":
    unittest.main()
