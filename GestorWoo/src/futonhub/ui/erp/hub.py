from __future__ import annotations

import subprocess
import tkinter as tk
from tkinter import ttk

from futonhub.ui.erp.cloud_admin import CloudAdminToolsMixin
from futonhub.ui.erp.cloud_inventory import CloudInventoryBoardMixin
from futonhub.ui.erp.cloud_prices import CloudPriceBoardMixin
from futonhub.ui.erp.diagnostics import DiagnosticsMixin
from futonhub.ui.erp.launching import ProjectLaunchingMixin
from futonhub.ui.erp.login import LoginMixin
from futonhub.ui.erp.project_cards import ProjectCardsMixin
from futonhub.ui.erp.project_catalog import ProjectCatalogMixin
from futonhub.core.config import load_settings
from futonhub.ui.theme import (
    C_BG,
    apply_theme,
)
from futonhub.ui.windowing import center_window


class FutonEspaiHub(LoginMixin, DiagnosticsMixin, ProjectCatalogMixin, ProjectCardsMixin, ProjectLaunchingMixin, CloudInventoryBoardMixin, CloudPriceBoardMixin, CloudAdminToolsMixin, tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Futon Espai")
        center_window(self, 980, 700)
        self.minsize(860, 620)
        self.configure(bg=C_BG)
        apply_theme(self)
        self._processes: dict[str, subprocess.Popen[object]] = {}
        self._buttons: dict[str, ttk.Button] = {}
        self._button_closed_text: dict[str, str] = {}
        self._cloud_session = None
        self._login_in_progress = False
        self._login_overlay: tk.Frame | None = None
        self._role_status_label: ttk.Label | None = None
        self._main_container: ttk.Frame | None = None
        self.projects = self._build_projects()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_layout()
        self.after(1000, self._poll_processes)

    def _add_footer_menu(self, parent: ttk.Frame, label: str, items: list[tuple[str, object]]) -> None:
        """Añade un menú compacto al pie del HUB.

        Mantiene la pantalla limpia: en vez de una fila infinita de botones,
        las herramientas secundarias quedan agrupadas.
        """
        valid_items = [(text, command) for text, command in items if command is not None]
        if not valid_items:
            return
        button = ttk.Menubutton(parent, text=label)
        menu = tk.Menu(button, tearoff=False)
        for text, command in valid_items:
            if text == "---":
                menu.add_separator()
            else:
                menu.add_command(label=text, command=command)
        button["menu"] = menu
        button.pack(side=tk.RIGHT, padx=(0, 10))

    def _rebuild_layout(self) -> None:
        self.projects = self._build_projects()
        self._buttons.clear()
        self._button_closed_text.clear()
        if self._main_container is not None and self._main_container.winfo_exists():
            self._main_container.destroy()
        self._build_layout()

    def _build_layout(self) -> None:
        container = ttk.Frame(self, padding=28)
        self._main_container = container
        container.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(container)
        header.pack(fill=tk.X, pady=(0, 22))

        title = ttk.Label(
            header,
            text="Futon Espai",
            style="Title.TLabel",
        )
        title.pack(anchor=tk.W)

        subtitle = ttk.Label(
            header,
            text="Herramientas internas de gestion y calculo.",
            style="Muted.TLabel",
        )
        subtitle.pack(anchor=tk.W, pady=(4, 0))

        db_status = ttk.Label(
            header,
            text=self._database_status_text(),
            style="Muted.TLabel",
        )
        db_status.pack(anchor=tk.W, pady=(8, 0))

        safety_status = ttk.Label(
            header,
            text=self._safety_status_text(),
            style="Muted.TLabel",
        )
        safety_status.pack(anchor=tk.W, pady=(4, 0))

        role_status = ttk.Label(
            header,
            text=self._role_status_text(),
            style="Muted.TLabel",
        )
        role_status.pack(anchor=tk.W, pady=(4, 0))
        self._role_status_label = role_status

        body = ttk.Frame(container)
        body.pack(fill=tk.BOTH, expand=True)
        columns = 3
        if not self.projects:
            empty = ttk.Frame(body, padding=26)
            empty.pack(fill=tk.BOTH, expand=True)
            ttk.Label(empty, text="HUB bloqueado hasta iniciar sesión", style="Section.TLabel").pack(anchor=tk.CENTER, pady=(80, 8))
            ttk.Label(
                empty,
                text="Inicia sesión en Supabase para cargar solo las herramientas permitidas para tu rol.",
                style="Muted.TLabel",
                justify=tk.CENTER,
            ).pack(anchor=tk.CENTER)
        else:
            for row in range((len(self.projects) + columns - 1) // columns):
                body.rowconfigure(row, weight=1, minsize=210)
            for column in range(columns):
                body.columnconfigure(column, weight=1, uniform="project_cards")

            for index, project in enumerate(self.projects):
                row = index // columns
                column = index % columns
                self._project_card(body, project).grid(
                    row=row,
                    column=column,
                    sticky="nsew",
                    padx=(0, 8) if column == 0 else (8, 8) if column == 1 else (8, 0),
                    pady=(0, 12),
                )

        footer = ttk.Frame(container)
        footer.pack(fill=tk.X, pady=(20, 0))
        ttk.Button(footer, text="Salir", command=self._close).pack(side=tk.RIGHT)
        ttk.Button(footer, text="Login Supabase", command=self._login_supabase).pack(side=tk.RIGHT, padx=(0, 10))

        try:
            settings_for_operational = load_settings()
            show_operational_test = settings_for_operational.app_mode == "supabase_guarded"
        except Exception:
            show_operational_test = False

        if show_operational_test and self._has_cloud_session():
            # Menú compacto de pruebas operativas. Deja el pie limpio aunque
            # mantengamos herramientas de verificación durante el desarrollo.
            self._add_footer_menu(
                footer,
                "Pruebas",
                [
                    ("Buscar productos cloud", self._cloud_search_products),
                    ("Inventario real interno", self._cloud_inventory_internal_board),
                    ("Bandeja propuestas", self._cloud_price_proposals_board),
                    ("Propuesta real precio", self._cloud_real_price_proposal),
                    ("Test estrés precios", self._cloud_price_heart_attack_tests),
                    ("---", None),
                    ("Precio simulado", self._cloud_worker_price_test),
                    ("Inventario simulado", self._cloud_worker_inventory_test),
                    ("Pedido simulado", self._cloud_worker_order_test),
                    ("Constante worker", self._cloud_worker_feedback_test),
                    ("Constante cloud", self._cloud_test_constant),
                ],
            )

        show_admin_cloud_tools = self._is_authenticated_admin()

        if show_admin_cloud_tools:
            self._add_footer_menu(
                footer,
                "Caja negra",
                [
                    ("Bandeja propuestas", self._cloud_price_proposals_board),
                    ("---", None),
                    ("Aprobar precio test", lambda: self._cloud_review_worker_price_test("approved")),
                    ("Rechazar precio test", lambda: self._cloud_review_worker_price_test("rejected")),
                    ("---", None),
                    ("Logs cloud", self._show_cloud_logs),
                    ("Snapshots cloud", self._show_cloud_snapshots),
                    ("Rollback snapshot", self._cloud_rollback_snapshot),
                    ("Estado operativo cloud", self._show_cloud_operational_status),
                    ("---", None),
                    ("Test log", self._cloud_test_log),
                    ("Test snapshot", self._cloud_test_snapshot),
                ],
            )
            self._add_footer_menu(
                footer,
                "Limpieza test",
                [
                    ("Limpiar precio test", self._cloud_clean_worker_price_test),
                    ("Limpiar inventario test", self._cloud_clean_worker_inventory_test),
                    ("Limpiar pedido test", self._cloud_clean_worker_order_test),
                    ("Limpiar constante worker", self._cloud_clean_worker_feedback_test),
                ],
            )
        try:
            settings_diag = load_settings()
            show_local_diagnostics = settings_diag.app_mode != "supabase_guarded"
        except Exception:
            show_local_diagnostics = False
        if show_local_diagnostics or self._is_authenticated_admin():
            ttk.Button(
                footer,
                text="Diagnóstico del sistema",
                command=self._show_diagnostics,
            ).pack(side=tk.RIGHT, padx=(0, 10))
            ttk.Button(
                footer,
                text="Estado de seguridad",
                command=self._show_diagnostics,
            ).pack(side=tk.RIGHT, padx=(0, 10))

    def _close(self) -> None:
        self.destroy()

def run_hub() -> None:
    app = FutonEspaiHub()
    app.mainloop()


FutonHubApp = FutonEspaiHub
