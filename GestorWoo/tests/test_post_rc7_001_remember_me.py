from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from futonhub.security.remembered_session import (  # noqa: E402
    InMemorySecureSessionStore,
    RememberedSessionError,
    clear_remembered_session,
    has_remembered_session,
    load_remembered_session,
    save_remembered_session,
)
from gestorwoo.cloud import auth as auth_module  # noqa: E402
from gestorwoo.cloud.auth import (  # noqa: E402
    CloudUserSession,
    SupabaseRefreshSessionError,
    register_device_seen,
    sign_in_with_refresh_token,
)


class _FakeAuth:
    def __init__(self, response=None, exc: Exception | None = None) -> None:
        self.response = response
        self.exc = exc
        self.calls: list[object] = []
        self.sessions: list[tuple[str, str]] = []

    def refresh_session(self, refresh_token):
        self.calls.append(refresh_token)
        if self.exc is not None:
            raise self.exc
        return self.response

    def set_session(self, access_token, refresh_token):
        self.sessions.append((access_token, refresh_token))


class _FakeResponse:
    def __init__(self, data=None) -> None:
        self.data = data or []


class _FakeTable:
    def __init__(self, client, name: str) -> None:
        self.client = client
        self.name = name
        self.payloads: list[dict[str, object]] = []

    def select(self, *_args, **_kwargs):
        return self

    def eq(self, *_args, **_kwargs):
        return self

    def limit(self, *_args, **_kwargs):
        return self

    def insert(self, payload):
        self.payloads.append(dict(payload))
        self.client.device_payloads.append(dict(payload))
        return self

    def execute(self):
        if self.name == "profiles":
            return _FakeResponse([
                {
                    "id": "user-1",
                    "email": "worker@example.test",
                    "display_name": "Worker",
                    "role": "worker",
                    "active": True,
                }
            ])
        return _FakeResponse([])


class _FakeClient:
    def __init__(self, auth) -> None:
        self.auth = auth
        self.headers: dict[str, str] = {}
        self.device_payloads: list[dict[str, object]] = []

    def table(self, name: str):
        return _FakeTable(self, name)


def _auth_response(access_token="access-new", refresh_token="refresh-new"):
    return SimpleNamespace(
        user=SimpleNamespace(id="user-1", email="worker@example.test"),
        session=SimpleNamespace(access_token=access_token, refresh_token=refresh_token),
    )


class RememberedSessionStoreTests(unittest.TestCase):
    def test_save_load_clear_uses_protected_secret_without_password_or_plain_token(self) -> None:
        store = InMemorySecureSessionStore()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "remembered_session.json"
            save_remembered_session("Worker@Example.Test", "fake-refresh-token", path=path, store=store)

            raw = path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            self.assertTrue(payload["remember_enabled"])
            self.assertEqual(payload["email"], "worker@example.test")
            self.assertNotIn("fake-refresh-token", raw)
            self.assertNotIn("password", raw.lower())
            self.assertNotIn("access_token", raw.lower())
            self.assertNotIn("refresh_token", raw.lower())

            loaded = load_remembered_session(path=path, store=store)
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded.email, "worker@example.test")
            self.assertEqual(loaded.refresh_token, "fake-refresh-token")
            self.assertTrue(has_remembered_session(path=path))

            clear_remembered_session(path=path)
            self.assertFalse(has_remembered_session(path=path))
            self.assertIsNone(load_remembered_session(path=path, store=store))

    def test_decrypt_failure_fails_safe_without_returning_token(self) -> None:
        store = InMemorySecureSessionStore()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "remembered_session.json"
            save_remembered_session("worker@example.test", "fake-refresh-token", path=path, store=store)

            with self.assertRaises(RememberedSessionError) as ctx:
                load_remembered_session(path=path, store=InMemorySecureSessionStore())

            self.assertNotIn("fake-refresh-token", str(ctx.exception))

    def test_corrupt_file_fails_safe(self) -> None:
        store = InMemorySecureSessionStore()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "remembered_session.json"
            path.write_text("{not-json", encoding="utf-8")
            with self.assertRaises(RememberedSessionError):
                load_remembered_session(path=path, store=store)


class RememberedSupabaseAuthTests(unittest.TestCase):
    def test_refresh_token_login_builds_authenticated_cloud_session_and_applies_token(self) -> None:
        fake_auth = _FakeAuth(response=_auth_response())
        fake_client = _FakeClient(fake_auth)
        settings = SimpleNamespace(hub_user_email="worker@example.test")

        with patch.object(auth_module, "create_supabase_client", return_value=fake_client):
            session = sign_in_with_refresh_token("refresh-old", settings)

        self.assertIsInstance(session, CloudUserSession)
        self.assertEqual(session.user_id, "user-1")
        self.assertEqual(session.email, "worker@example.test")
        self.assertEqual(session.role, "worker")
        self.assertEqual(session.refresh_token, "refresh-new")
        self.assertEqual(fake_auth.calls, ["refresh-old"])
        self.assertEqual(fake_client.headers["Authorization"], "Bearer access-new")

    def test_invalid_refresh_token_is_classified_and_sanitized(self) -> None:
        fake_auth = _FakeAuth(exc=RuntimeError("invalid refresh token fake-refresh-token"))
        fake_client = _FakeClient(fake_auth)
        settings = SimpleNamespace(hub_user_email="worker@example.test")

        with patch.object(auth_module, "create_supabase_client", return_value=fake_client):
            with self.assertRaises(SupabaseRefreshSessionError) as ctx:
                sign_in_with_refresh_token("fake-refresh-token", settings)

        self.assertEqual(ctx.exception.kind, "invalid_session")
        self.assertNotIn("fake-refresh-token", str(ctx.exception))

    def test_network_refresh_failure_preserves_local_session_semantics(self) -> None:
        fake_auth = _FakeAuth(exc=RuntimeError("connection timeout"))
        fake_client = _FakeClient(fake_auth)
        settings = SimpleNamespace(hub_user_email="worker@example.test")

        with patch.object(auth_module, "create_supabase_client", return_value=fake_client):
            with self.assertRaises(SupabaseRefreshSessionError) as ctx:
                sign_in_with_refresh_token("fake-refresh-token", settings)

        self.assertEqual(ctx.exception.kind, "network_error")
        self.assertNotIn("fake-refresh-token", str(ctx.exception))

    def test_register_device_seen_still_runs_after_remembered_login(self) -> None:
        fake_client = _FakeClient(_FakeAuth())
        settings = SimpleNamespace(machine_name="PC-1", sync_role="worker")
        session = CloudUserSession(client=fake_client, user_id="user-1", email="worker@example.test", role="worker")

        register_device_seen(session, settings)

        self.assertEqual(fake_client.device_payloads[0]["user_id"], "user-1")
        self.assertEqual(fake_client.device_payloads[0]["machine_name"], "PC-1")


class RememberMeUiContractTests(unittest.TestCase):
    def test_login_ui_exposes_remember_me_without_text_confirmation_or_password_persistence(self) -> None:
        source = (SRC / "futonhub" / "ui" / "erp" / "prototype.py").read_text(encoding="utf-8")

        self.assertIn("Recuerdame en este equipo", source)
        self.assertIn("Usar otra cuenta", source)
        self.assertIn("Olvidar este equipo", source)
        self.assertIn("sign_in_with_refresh_token", source)
        self.assertIn("save_remembered_session", source)
        self.assertIn("clear_remembered_session", source)
        self.assertNotIn("ACEPTAR", source)


if __name__ == "__main__":
    unittest.main()
