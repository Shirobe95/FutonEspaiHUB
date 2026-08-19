from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


class PostRc7PerformanceTests(unittest.TestCase):
    def test_woocommerce_import_no_longer_loads_requests_at_module_import_time(self) -> None:
        code = (
            "import sys;"
            "import gestorwoo.woocommerce;"
            "print('requests' in sys.modules)"
        )
        completed = subprocess.run(
            [sys.executable, "-c", code],
            check=True,
            capture_output=True,
            text=True,
            env={"PYTHONPATH": str(SRC)},
        )

        self.assertEqual(completed.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
