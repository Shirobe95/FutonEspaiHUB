from __future__ import annotations

import os
import sys
from pathlib import Path

from futonhub.cloud.permissions import can_view_module
from futonhub.core.config import load_settings
from futonhub.core.pathing import calculo_coste_root, gestorwoo_root
from futonhub.ui.erp.models import ProjectAction


ROOT = gestorwoo_root()


class ProjectCatalogMixin:
    def _build_projects(self) -> list[ProjectAction]:
        calculo_path = Path(
            os.getenv(
                "FUTON_CALCULO_COSTE_PATH",
                str(calculo_coste_root()),
            )
        )
        calculo_script = os.getenv("FUTON_CALCULO_COSTE_SCRIPT", "coste_1.py")
        calculo_python = os.getenv("FUTON_CALCULO_COSTE_PYTHON", sys.executable)

        projects = [
            ProjectAction(
                name="Gestor WooCommerce",
                description=(
                    "Separa la organizacion visual del catalogo y los cambios de "
                    "precios para trabajar con mas seguridad."
                ),
                path=ROOT,
                command=self._app_command("woocommerce-inventory"),
                window_title="GestorWoo - Gestion de Inventario",
            ),
            ProjectAction(
                name="Calculo de coste",
                description=(
                    "Calcula costes desde base de datos local y permite exportar "
                    "resultados de compra."
                ),
                path=calculo_path,
                command=self._cost_command(calculo_python, calculo_path, calculo_script),
                window_title="FutonSpai",
            ),
            ProjectAction(
                name="Mapa Maestro",
                description=(
                    "Centraliza la ficha de producto, inventario de tienda, precios "
                    "de proveedor y referencias futuras de Heca."
                ),
                path=ROOT,
                command=self._app_command("inventory"),
                window_title="Futon Espai - Mapa Maestro",
            ),
            ProjectAction(
                name="Seguridad",
                description=(
                    "Bitacora de cambios reales del HUB: inventario, pedidos, "
                    "precios, constantes, backups y restauraciones."
                ),
                path=ROOT,
                command=self._app_command("logs"),
                window_title="Futon Espai - Seguridad - Logs",
            ),
            ProjectAction(
                name="Backups y Restauracion",
                description=(
                    "Crea copias fechadas de la base local y permite restaurarlas "
                    "con backup previo de seguridad."
                ),
                path=ROOT,
                command=self._app_command("backup"),
                window_title="Futon Espai - Backups",
            ),
        ]

        settings = load_settings()
        effective_role = self._effective_role()
        if settings.app_mode == "supabase_guarded" and not effective_role:
            return []
        visible_projects: list[ProjectAction] = []
        module_by_name = {
            "Gestor WooCommerce": "inventory",
            "Calculo de coste": "cost",
            "Mapa Maestro": "inventory",
            "Seguridad": "logs",
            "Backups y Restauracion": "backups",
        }
        for project in projects:
            module = module_by_name.get(project.name, project.name.lower())
            if can_view_module(effective_role or settings.sync_role, module):
                visible_projects.append(project)
        return visible_projects

    def _app_command(self, command: str) -> tuple[str, ...]:
        if getattr(sys, "frozen", False):
            return (sys.executable, command)
        return (sys.executable, str(ROOT / "gestorwoo.py"), command)

    def _cost_command(
        self,
        calculo_python: str,
        calculo_path: Path,
        calculo_script: str,
    ) -> tuple[str, ...]:
        if getattr(sys, "frozen", False):
            return (sys.executable, "cost")
        return (calculo_python, str(calculo_path / calculo_script))
