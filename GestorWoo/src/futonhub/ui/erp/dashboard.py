from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from typing import Iterable

from futonhub.ui.erp.shared_ui import BG, CARD, GREEN, GREEN_SOFT, INDIGO, INDIGO_SOFT, LINE, MUTED, SOFT, TEXT


@dataclass(frozen=True)
class DashboardModule:
    key: str
    title: str
    description: str
    icon: str
    requires_admin: bool = False


# This is intentionally a navigation map, not an operational summary. The
# dashboard must not fabricate metrics, activity, alerts, or health claims.
DASHBOARD_MODULES: tuple[DashboardModule, ...] = (
    DashboardModule("inventario", "Inventario", "Consulta y organización del catálogo físico.", "INV"),
    DashboardModule("precios", "Cambio de Precios", "Propuestas, cálculo y trazabilidad de precios.", "EUR"),
    DashboardModule("calcular", "Pedidos", "Pedidos de proveedor y cálculo de costes de entrada.", "PED"),
    DashboardModule("woocommerce", "WooCommerce", "Operativa comercial y relaciones Woo verificadas.", "WOO"),
    DashboardModule("precios_proveedor", "Precio Proveedores", "Consulta y mantenimiento de referencias de proveedor.", "PRO"),
    DashboardModule("informes", "Informes / Exportaciones", "Informes operativos y exportaciones disponibles.", "REP"),
    DashboardModule("formulas", "Biblioteca de Fórmulas", "Consulta de fórmulas verificadas en código, en solo lectura.", "FX"),
    DashboardModule("seguridad", "Seguridad / Logs", "Auditoría, trazabilidad y controles de seguridad.", "SEC", requires_admin=True),
    DashboardModule("configuracion", "Configuración", "Constantes y configuración del ERP.", "CFG"),
)


def dashboard_modules(*, is_admin: bool) -> tuple[dict[str, str], ...]:
    """Return only real shell destinations and their truthful availability."""
    cards: list[dict[str, str]] = []
    for module in DASHBOARD_MODULES:
        available = not module.requires_admin or is_admin
        cards.append({
            "key": module.key,
            "title": module.title,
            "description": module.description,
            "icon": module.icon,
            "availability": "Disponible" if available else "Solo administradores",
            "access": "OPEN" if available else "RESTRICTED",
        })
    return tuple(cards)


def dashboard_summary(cards: Iterable[dict[str, str]]) -> dict[str, int]:
    values = tuple(cards)
    return {
        "modules": len(values),
        "available": sum(card["access"] == "OPEN" for card in values),
        "restricted": sum(card["access"] == "RESTRICTED" for card in values),
    }


class ErpDashboardMixin:
    def _build_dashboard(self, parent: tk.Frame) -> None:
        is_admin = bool(
            self._cloud_session is not None
            and str(getattr(self._cloud_session, "role", "") or "").lower() == "admin"
        )
        cards = dashboard_modules(is_admin=is_admin)

        viewport = tk.Frame(parent, bg=BG)
        viewport.pack(fill=tk.BOTH, expand=True)
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)
        canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        scroll = tk.Scrollbar(viewport, orient=tk.VERTICAL, command=canvas.yview)
        body = tk.Frame(canvas, bg=BG)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body_window = canvas.create_window((0, 0), window=body, anchor=tk.NW)
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        tk.Label(
            body,
            text="Dashboard",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 24, "bold"),
            anchor=tk.W,
        ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(4, 10))

        for index, card in enumerate(cards):
            self._dashboard_module_card(body, card).grid(
                row=(index // 2) + 1,
                column=index % 2,
                sticky="nsew",
                padx=(0 if index % 2 == 0 else 7, 7 if index % 2 == 0 else 0),
                pady=7,
            )

        def sync_scroll(_event: object | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                canvas.itemconfigure(body_window, width=canvas.winfo_width())
            except tk.TclError:
                return

        body.bind("<Configure>", sync_scroll)
        canvas.bind("<Configure>", sync_scroll)
        canvas.bind_all(
            "<MouseWheel>",
            lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            if getattr(self, "_current_key", "") == "dashboard"
            else None,
        )

    def _dashboard_module_card(self, parent: tk.Misc, card_data: dict[str, str]) -> tk.Frame:
        available = card_data["access"] == "OPEN"
        card = tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1, cursor="hand2" if available else "")
        card.columnconfigure(1, weight=1)
        badge_bg = INDIGO if available else SOFT
        badge_fg = "white" if available else MUTED
        tk.Label(
            card,
            text=card_data["icon"],
            bg=badge_bg,
            fg=badge_fg,
            font=("Segoe UI", 10, "bold"),
            width=5,
            pady=9,
        ).grid(row=0, column=0, rowspan=2, sticky="nw", padx=18, pady=18)
        text = tk.Frame(card, bg=CARD)
        text.grid(row=0, column=1, sticky="new", padx=(0, 18), pady=(18, 8))
        tk.Label(text, text=card_data["title"], bg=CARD, fg=TEXT, font=("Segoe UI", 13, "bold"), anchor=tk.W).pack(fill=tk.X)
        tk.Label(
            text,
            text=card_data["description"],
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 9),
            anchor=tk.W,
            justify=tk.LEFT,
            wraplength=360,
        ).pack(fill=tk.X, pady=(5, 0))
        footer = tk.Frame(card, bg=CARD)
        footer.grid(row=1, column=1, sticky="ew", padx=(0, 18), pady=(0, 18))
        status_bg = GREEN_SOFT if available else SOFT
        status_fg = GREEN if available else MUTED
        tk.Label(footer, text=card_data["availability"], bg=status_bg, fg=status_fg, font=("Segoe UI", 8, "bold"), padx=8, pady=4).pack(side=tk.LEFT)
        if available:
            self._button(
                footer,
                "Abrir",
                primary=True,
                command=lambda key=card_data["key"]: self._show_view(key),
            ).pack(side=tk.RIGHT)
            card.bind("<Enter>", lambda _event: card.configure(highlightbackground=INDIGO))
            card.bind("<Leave>", lambda _event: card.configure(highlightbackground=LINE))
        return card
