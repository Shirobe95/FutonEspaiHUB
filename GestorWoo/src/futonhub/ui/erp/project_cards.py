from __future__ import annotations

import sys
import tkinter as tk
from tkinter import ttk

from futonhub.core.pathing import gestorwoo_root
from futonhub.ui.erp.models import ProjectAction
from futonhub.ui.theme import C_BTN, C_PANEL, C_PANEL_LINE


ROOT = gestorwoo_root()
PROVEEDOR_TITULOS = {"ekomat": "Ekomat", "pascal": "Pascal", "hemei": "Hemei", "heimei": "Hemei", "cipta": "Cipta"}


class ProjectCardsMixin:
    def _project_card(self, parent: ttk.Frame, project: ProjectAction) -> ttk.Frame:
        frame = tk.Frame(
            parent,
            bg=C_PANEL,
            highlightbackground=C_PANEL_LINE,
            highlightthickness=1,
            bd=0,
        )
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        accent = tk.Frame(frame, bg=C_BTN, height=4)
        accent.grid(row=0, column=0, sticky="ew")

        content = ttk.Frame(frame, padding=16, style="Panel.TFrame")
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(3, weight=1)

        ttk.Label(
            content,
            text=project.name,
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            content,
            text=project.description,
            wraplength=240,
            justify=tk.LEFT,
            style="PanelMuted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(8, 12))

        if project.name == "Gestor WooCommerce":
            primary_text = "Gestión de Inventario"
        elif project.name == "Calculo de coste":
            primary_text = "Abrir Calculo de Coste"
        elif project.name == "Seguridad":
            primary_text = "Logs"
        else:
            primary_text = f"Abrir {project.name}"

        button = ttk.Button(
            content,
            text=primary_text,
            command=lambda: self._launch(project),
        )
        button.grid(row=4, column=0, sticky="ew")
        self._register_button(project.name, button, primary_text)

        if project.name == "Gestor WooCommerce":
            precios_button = ttk.Button(
                content,
                text="Cambio de Precios",
                command=lambda p=project: self._launch_custom(
                    key="Cambio de Precios",
                    path=p.path,
                    command=self._app_command("price-changes"),
                    window_title="GestorWoo - Cambio de Precios",
                ),
            )
            precios_button.grid(row=5, column=0, sticky="ew", pady=(8, 0))
            self._register_button(
                "Cambio de Precios",
                precios_button,
                "Cambio de Precios",
            )

        if project.name == "Calculo de coste":
            for offset, (provider, label) in enumerate((
                ("ekomat", "Pedido Ekomat"),
                ("pascal", "Pedido Pascal"),
                ("hemei", "Pedido Hemei"),
                ("cipta", "Pedido Cipta"),
            ), start=5):
                pedido_button = ttk.Button(
                    content,
                    text=label,
                    command=lambda provider=provider, label=label: self._launch_custom(
                        key=f"Calculo de Coste · {label}",
                        path=ROOT,
                        command=self._app_command("cost-pedido") + ("--proveedor", provider),
                        window_title=f"FutonSpai · Calculo de Coste de Pedido · {PROVEEDOR_TITULOS.get(provider, label)}",
                    ),
                )
                pedido_button.grid(row=offset, column=0, sticky="ew", pady=(8, 0))
                self._register_button(
                    f"Calculo de Coste · {label}",
                    pedido_button,
                    label,
                )

            constantes_button = ttk.Button(
                content,
                text="Cambiar Valores de Constantes",
                command=lambda p=project: self._launch_custom(
                    key="Constantes del negocio",
                    path=p.path,
                    command=(sys.executable, "constantes") if getattr(sys, "frozen", False) else (*p.command, "--constantes"),
                    window_title="Constantes del negocio",
                ),
            )
            constantes_button.grid(row=9, column=0, sticky="ew", pady=(8, 0))
            self._register_button(
                "Constantes del negocio",
                constantes_button,
                "Cambiar Valores de Constantes",
            )

        self._bind_card_hover(frame, project)

        return frame

    def _register_button(self, key: str, button: ttk.Button, closed_text: str) -> None:
        self._buttons[key] = button
        self._button_closed_text[key] = closed_text

    def _bind_card_hover(self, frame: tk.Frame, project: ProjectAction) -> None:
        widgets: list[tk.Widget] = [frame, *frame.winfo_children()]
        for child in frame.winfo_children():
            widgets.extend(child.winfo_children())

        for widget in widgets:
            widget.bind("<Enter>", lambda _event, f=frame, p=project: self._card_enter(f, p), add="+")
            widget.bind("<Leave>", lambda _event, f=frame: self._card_leave(f), add="+")

    def _card_enter(self, frame: tk.Frame, project: ProjectAction) -> None:
        frame.configure(highlightbackground=C_BTN, highlightthickness=2)

    def _card_leave(self, frame: tk.Frame) -> None:
        pointer_x = self.winfo_pointerx()
        pointer_y = self.winfo_pointery()
        left = frame.winfo_rootx()
        top = frame.winfo_rooty()
        right = left + frame.winfo_width()
        bottom = top + frame.winfo_height()
        if left <= pointer_x <= right and top <= pointer_y <= bottom:
            return

        frame.configure(highlightbackground=C_PANEL_LINE, highlightthickness=1)
