"""Cierre de sesion (auditoria 2026-10, corte 3b): se revoca la sesion en Supabase (scope local)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.auth import CloudUserSession, sign_out_session  # noqa: E402


def make_session(sign_out) -> CloudUserSession:
    client = SimpleNamespace(auth=SimpleNamespace(sign_out=sign_out))
    return CloudUserSession(client=client, user_id="u1", email="a@b.c", access_token="t", refresh_token="r")


class SignOutSessionTests(unittest.TestCase):
    def test_signs_out_only_this_session(self) -> None:
        sign_out = MagicMock()
        self.assertTrue(sign_out_session(make_session(sign_out)))
        sign_out.assert_called_once_with({"scope": "local"})

    def test_never_raises(self) -> None:
        self.assertFalse(sign_out_session(make_session(MagicMock(side_effect=RuntimeError("red")))))
        self.assertFalse(sign_out_session(None))
        self.assertFalse(sign_out_session(SimpleNamespace(client=SimpleNamespace())))


class LogoutFlowTests(unittest.TestCase):
    def test_logout_revokes_the_session_and_clears_it(self) -> None:
        try:
            from futonhub.ui.erp import prototype
        except Exception as exc:  # pragma: no cover - sin tkinter
            self.skipTest(f"prototype no importable: {exc}")
        sign_out = MagicMock()
        session = make_session(sign_out)
        calls: list[str] = []
        fake = SimpleNamespace(
            _cloud_session=session,
            _remembered_login_cancelled=False,
            _login_in_progress=True,
            _hide_login_loading=lambda: calls.append("hide"),
            _reset_session_state_after_logout=lambda: calls.append("reset"),
            withdraw=lambda: calls.append("withdraw"),
            _destroy_authenticated_shell=lambda: calls.append("destroy"),
            _show_startup_login=lambda **kw: calls.append(f"login:{kw.get('default_email_override')}"),
        )

        class SyncThread:
            def __init__(self, target, args=(), daemon=None):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        with patch.object(prototype, "clear_remembered_session") as clear, patch.object(prototype.threading, "Thread", SyncThread):
            prototype.FutonHubErpPrototype._logout_change_user_confirmed(fake)
        clear.assert_called_once()
        sign_out.assert_called_once_with({"scope": "local"})
        self.assertIsNone(fake._cloud_session)
        self.assertEqual(calls[-1], "login:a@b.c")
        self.assertIn("reset", calls)


if __name__ == "__main__":
    unittest.main()
