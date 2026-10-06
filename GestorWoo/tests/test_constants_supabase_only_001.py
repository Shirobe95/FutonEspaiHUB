"""Decisión de negocio: las constantes salen solo de Supabase; sin valores inventados."""
from __future__ import annotations

import sys
import types
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.services import business_constants as bc  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype as P  # noqa: E402


class FakeTable:
    def __init__(self, rows, fail=False):
        self.rows, self.fail = rows, fail

    def select(self, *_a, **_k):
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("sin red")
        return types.SimpleNamespace(data=self.rows)


class FakeSession:
    def __init__(self, rows, fail=False):
        self.client = types.SimpleNamespace(table=lambda _name: FakeTable(rows, fail))


class Shell:
    def __init__(self, session):
        self._cloud_session = session
        self._business_constants = {}

    def __getattr__(self, name):
        return types.MethodType(getattr(P, name), self)


class ConstantsTests(unittest.TestCase):
    def test_no_default_value_is_a_number(self) -> None:
        for key, meta in bc.DEFAULT_BUSINESS_CONSTANTS.items():
            self.assertIsNone(meta["value"], key)
            self.assertTrue(meta["unit"] or key)

    def test_unreadable_supabase_returns_values_as_none(self) -> None:
        result = bc.list_business_constants(FakeSession([], fail=True))
        self.assertTrue(all(meta["value"] is None for meta in result.values()))

    def test_a_real_zero_in_supabase_is_not_replaced_by_a_default(self) -> None:
        rows = [{"key": key, "value": 0} for key in bc.DEFAULT_BUSINESS_CONSTANTS]
        values = Shell(FakeSession(rows))._current_business_constant_values(refresh_cloud=True)
        self.assertEqual(values["PC_GASTOS_MANIPULACION"], 0.0)
        self.assertEqual(values["IMPORTE_DESCARGA_MT"], 0.0)

    def test_calculation_stops_when_required_constants_cannot_be_read(self) -> None:
        shell = Shell(FakeSession([], fail=True))
        with self.assertRaises(RuntimeError):
            shell._current_business_constant_values(
                refresh_cloud=True, fail_on_refresh_error=True,
                required_keys=bc.SUPPLIER_ORDER_GENERAL_REQUIRED_CONSTANTS,
            )


if __name__ == "__main__":
    unittest.main()
