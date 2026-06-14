from __future__ import annotations

import runpy
from pathlib import Path

from futonhub.core.pathing import calculo_coste_root


def run_cost_individual() -> None:
    runpy.run_path(str(calculo_coste_root() / "coste_1.py"), run_name="__main__")


def run_cost_pedido(proveedor: str = "ekomat") -> None:
    path = calculo_coste_root() / "coste_pedido.py"
    namespace = runpy.run_path(str(path))
    main = namespace.get("main")
    if callable(main):
        main(proveedor)


def data_path() -> Path:
    return calculo_coste_root() / "data.xlsx"


__all__ = ["data_path", "run_cost_individual", "run_cost_pedido"]
