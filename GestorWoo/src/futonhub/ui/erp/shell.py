from __future__ import annotations

import tkinter as tk

from futonhub.ui.erp.shared_ui import (
    BG,
    CARD,
    INDIGO,
    INDIGO_SOFT,
    LINE,
    MUTED,
    NavItem,
    SIDEBAR,
    SOFT,
    TEXT,
)


NAV_ITEMS = [
    NavItem("dashboard", "Dashboard", "Principal"),
    NavItem("inventario", "Inventario", "Operaciones"),
    NavItem("precios", "Cambio de Precios", "Operaciones"),
    NavItem("calcular", "Pedidos", "Operaciones"),
    NavItem("woocommerce", "WooCommerce", "Gestion"),
    NavItem("precios_proveedor", "Precio Proveedores", "Gestion"),
    NavItem("informes", "Informes / Exportaciones", "Gestion"),
    NavItem("seguridad", "Seguridad / Logs", "Sistema"),
    NavItem("configuracion", "Configuracion", "Sistema"),
]


class ErpShellNavigationMixin:
    def _build_shell(self) -> None:
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        sidebar = tk.Frame(shell, bg=SIDEBAR, width=270, highlightbackground=LINE, highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        self._build_sidebar(sidebar)

        main = tk.Frame(shell, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)

        self._build_topbar(main)
        self._content = tk.Frame(main, bg=BG)
        self._content.grid(row=1, column=0, sticky="nsew", padx=24, pady=22)

    def _build_sidebar(self, parent: tk.Frame) -> None:
        brand = tk.Frame(parent, bg=SIDEBAR)
        brand.pack(fill=tk.X, padx=18, pady=(20, 28))
        logo = tk.Label(brand, text="F", bg=INDIGO, fg="white", font=("Segoe UI", 18, "bold"), width=2, height=1)
        logo.pack(side=tk.LEFT)
        text = tk.Frame(brand, bg=SIDEBAR)
        text.pack(side=tk.LEFT, padx=(12, 0))
        tk.Label(text, text="FutonHUB", bg=SIDEBAR, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor=tk.W)
        tk.Label(text, text="ERP privado - prototipo", bg=SIDEBAR, fg=MUTED, font=("Segoe UI", 9)).pack(anchor=tk.W)

        grouped: dict[str, list[NavItem]] = {}
        is_admin = self._cloud_session is not None and str(getattr(self._cloud_session, "role", "") or "").lower() == "admin"
        for item in NAV_ITEMS:
            if item.key == "seguridad" and not is_admin:
                continue
            grouped.setdefault(item.group, []).append(item)

        for group, items in grouped.items():
            tk.Label(
                parent,
                text=group.upper(),
                bg=SIDEBAR,
                fg="#94A3B8",
                font=("Segoe UI", 8, "bold"),
                anchor=tk.W,
            ).pack(fill=tk.X, padx=22, pady=(10, 4))
            for item in items:
                button = tk.Button(
                    parent,
                    text=item.label,
                    anchor=tk.W,
                    bd=0,
                    relief=tk.FLAT,
                    padx=14,
                    pady=10,
                    font=("Segoe UI", 10, "bold"),
                    command=lambda key=item.key: self._show_view(key),
                )
                button.pack(fill=tk.X, padx=14, pady=2)
                self._nav_buttons[item.key] = button

    def _build_topbar(self, parent: tk.Frame) -> None:
        topbar = tk.Frame(parent, bg=BG, highlightbackground=LINE, highlightthickness=1)
        topbar.grid(row=0, column=0, sticky="ew")
        topbar.columnconfigure(0, weight=1)

        search = tk.Frame(topbar, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        search.grid(row=0, column=0, sticky="ew", padx=20, pady=14)
        self._global_search_area = search
        tk.Label(search, text="Buscar producto, proveedor, informe o incidencia...", bg=CARD, fg=MUTED, anchor=tk.W).pack(
            fill=tk.X,
            padx=14,
            pady=10,
        )

        status = tk.Frame(topbar, bg=BG)
        status.grid(row=0, column=1, padx=(0, 20), pady=14)
        self._status_area = status
        self._render_session_status()

    def _global_search_visible_for_view(self, key: str) -> bool:
        return key != "precios"

    def _sync_global_search_visibility(self, key: str) -> None:
        search = getattr(self, "_global_search_area", None)
        if search is None:
            return
        if self._global_search_visible_for_view(key):
            search.grid()
        else:
            search.grid_remove()
        status = getattr(self, "_status_area", None)
        if status is not None:
            status.grid_configure(pady=6 if key == "precios" else 14)

    def _render_session_status(self) -> None:
        if self._status_area is None:
            return
        for child in self._status_area.winfo_children():
            child.destroy()
        role = self._cloud_session.role or "sin rol"
        self._status_chip(self._status_area, "Online", "OK").pack(side=tk.LEFT, padx=(0, 8))
        self._status_chip(self._status_area, role.title(), "Info").pack(side=tk.LEFT)

    def _show_view(self, key: str) -> None:
        if key == "inventory":
            key = "inventario"
        self._current_key = key
        self._sync_global_search_visibility(key)
        for item_key, button in self._nav_buttons.items():
            if item_key == key:
                button.configure(bg=INDIGO, fg="white", activebackground=INDIGO, activeforeground="white")
            else:
                button.configure(bg=SIDEBAR, fg="#475569", activebackground=SOFT, activeforeground=TEXT)

        if self._content is None:
            return
        for child in self._content.winfo_children():
            child.destroy()

        builders = {
            "dashboard": self._build_dashboard,
            "inventario": self._build_inventory,
            "precios": self._build_prices,
            "calcular": self._build_order_calc,
            "woocommerce": self._build_woocommerce,
            "precios_proveedor": self._build_supplier_prices,
            "informes": self._build_reports,
            "configuracion": self._build_settings,
            "seguridad": self._build_security,
        }
        builders.get(key, self._build_dashboard)(self._content)

    def _page_header(self, parent: tk.Frame, tag: str, title: str, subtitle: str, actions: list[str] | None = None) -> None:
        header = tk.Frame(parent, bg=BG)
        header.pack(fill=tk.X, pady=(0, 18))
        header.columnconfigure(0, weight=1)
        left = tk.Frame(header, bg=BG)
        left.grid(row=0, column=0, sticky="ew")
        tk.Label(left, text=tag, bg=INDIGO_SOFT, fg=INDIGO, font=("Segoe UI", 9, "bold"), padx=10, pady=4).pack(anchor=tk.W)
        tk.Label(left, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 24, "bold")).pack(anchor=tk.W, pady=(8, 2))
        tk.Label(left, text=subtitle, bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor=tk.W)
        if actions:
            right = tk.Frame(header, bg=BG)
            right.grid(row=0, column=1, sticky="e")
            for action in actions:
                command = self._page_header_action_command(action)
                self._button(right, action, primary=action == actions[-1], command=command).pack(side=tk.LEFT, padx=(8, 0))
