"""L4: BOM, comentarios en línea y comillas en load_env_file."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gestorwoo.config import load_env_file  # noqa: E402


class LoadEnvFileTests(unittest.TestCase):
    def load(self, content: bytes) -> dict[str, str]:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {}, clear=False):
            path = Path(temp) / ".env"
            path.write_bytes(content)
            for key in ("A_KEY", "B_KEY", "C_KEY", "D_KEY", "E_KEY"):
                os.environ.pop(key, None)
            load_env_file(path)
            return {k: os.environ[k] for k in ("A_KEY", "B_KEY", "C_KEY", "D_KEY", "E_KEY") if k in os.environ}

    def test_bom_does_not_corrupt_first_key(self) -> None:
        values = self.load("﻿A_KEY=1\nB_KEY=2\n".encode("utf-8"))
        self.assertEqual(values["A_KEY"], "1")

    def test_inline_comment_is_not_part_of_value(self) -> None:
        values = self.load(b"A_KEY=abc # comentario\nB_KEY=x#y\n")
        self.assertEqual(values["A_KEY"], "abc")
        self.assertEqual(values["B_KEY"], "x#y")  # sin espacio antes: es parte del valor

    def test_quoted_values_keep_hash_and_spaces(self) -> None:
        values = self.load(b'A_KEY="a # b"\nB_KEY=\'  v  \'\n')
        self.assertEqual(values["A_KEY"], "a # b")
        self.assertEqual(values["B_KEY"], "  v  ")

    def test_export_prefix_and_blank_lines(self) -> None:
        values = self.load(b"\n# nota\nexport A_KEY=ok\nC_KEY=\n")
        self.assertEqual(values["A_KEY"], "ok")
        self.assertEqual(values["C_KEY"], "")

    def test_real_environment_variables_win_over_the_env_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp, patch.dict(os.environ, {"A_KEY": "del_equipo"}, clear=False):
            path = Path(temp) / ".env"
            path.write_text("A_KEY=del_env\nB_KEY=nuevo\n", encoding="utf-8")
            os.environ.pop("B_KEY", None)
            load_env_file(path)
            self.assertEqual(os.environ["A_KEY"], "del_equipo")
            self.assertEqual(os.environ["B_KEY"], "nuevo")
            os.environ.pop("B_KEY", None)


class MachineNameTests(unittest.TestCase):
    def test_machine_name_is_detected_not_copied_from_env_file(self) -> None:
        from gestorwoo import config

        with tempfile.TemporaryDirectory() as temp:
            (Path(temp) / ".env").write_text("GESTORWOO_MACHINE_NAME=PC-COPIADO\n", encoding="utf-8")
            with patch.dict(os.environ, {}, clear=False), patch.object(config, "gestorwoo_root", return_value=Path(temp)), patch.object(config.socket, "gethostname", return_value="PC-REAL"):
                os.environ.pop("GESTORWOO_MACHINE_NAME", None)
                settings = config.load_settings()
                os.environ.pop("GESTORWOO_MACHINE_NAME", None)
        self.assertEqual(settings.machine_name, "PC-REAL")


if __name__ == "__main__":
    unittest.main()
