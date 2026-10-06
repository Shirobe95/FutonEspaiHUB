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


if __name__ == "__main__":
    unittest.main()
