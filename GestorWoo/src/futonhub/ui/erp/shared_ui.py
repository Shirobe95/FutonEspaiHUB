from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk
from typing import Any

from futonhub.ui.windowing import center_window


BG = "#F8FAFC"
SIDEBAR = "#FFFFFF"
CARD = "#FFFFFF"
LINE = "#E2E8F0"
SOFT = "#F1F5F9"
TEXT = "#0F172A"
MUTED = "#64748B"
INDIGO = "#4F46E5"
INDIGO_SOFT = "#EEF2FF"
GREEN = "#059669"
GREEN_SOFT = "#ECFDF5"
BLUE = "#2563EB"
BLUE_SOFT = "#EFF6FF"
AMBER = "#D97706"
AMBER_SOFT = "#FFFBEB"
ORANGE = "#EA580C"
ORANGE_SOFT = "#FFF7ED"
ROSE = "#E11D48"
ROSE_SOFT = "#FFF1F2"


@dataclass(frozen=True)
class NavItem:
    key: str
    label: str
    group: str


# Candidatas a trasladarse a sus modulos de dominio cuando Inventario,
# Precios, Pedidos, WooCommerce, Informes y Seguridad sean extraidos.
@dataclass(frozen=True)
class InventoryItem:
    code: str
    name: str
    price: str
    stock: str
    status: str
    family: str
    provider: str
    m3: str
    sku_woo: str
    measures: str
    material: str
    sync_woo: str
    notes: str
    subgroup: str = "-"
    store_stock: str = "-"
    warehouse_stock: str = "-"
    stock_total: str = "-"
    woo_id: str = "-"
    woo_parent_id: str = "-"
    woo_name: str = "-"
    woo_price: str = "-"
    woo_categories: str = "-"
    woo_item_kind: str = "-"
    woo_link_status: str = "-"
    order_calculated_price: str = "-"
    weighted_average_cost: str = "-"
    supplier_order_qty: str = "-"
    supplier_order_provider: str = "-"
    status_reasons: tuple[str, ...] = ()
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class ProposalLine:
    code: str
    name: str
    old_price: str
    new_price: str
    change: str
    direction: str


@dataclass(frozen=True)
class PriceProposal:
    name: str
    date: str
    items: int
    up: int
    down: int
    flat: int
    change: str
    status: str
    lines: tuple[ProposalLine, ...]
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class OrderItem:
    code: str
    name: str
    quantity: int
    m3: str
    final_cost: str
    status: str
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class SupplierOrder:
    order_id: str
    provider: str
    date: str
    items_count: int
    total_m3: str
    status: str
    total_cost: str
    notes: str
    items: tuple[OrderItem, ...]
    raw: dict[str, Any] | None = None


@dataclass(frozen=True)
class WooDifference:
    local_id: str
    woo_id: str
    name: str
    field: str
    local_value: str
    woo_value: str
    difference: str
    classification: str
    action: str
    status: str
    detail: str


@dataclass(frozen=True)
class ExportRecord:
    date: str
    report_type: str
    module: str
    format: str
    user_role: str
    status: str
    file_name: str
    rows: str
    reference: str
    filters: str
    columns: str
    path: str


@dataclass(frozen=True)
class SecurityEvent:
    date: str
    level: str
    module: str
    action: str
    user_role: str
    result: str
    reference: str
    message: str
    payload: str


@dataclass(frozen=True)
class SecurityLogRow:
    created_at: str
    user_email: str
    role: str
    visual_module: str
    visual_action: str
    status: str
    severity: str
    entity_type: str
    entity_id: str
    operation_id: str
    message: str
    raw: dict[str, Any] | None = None


STATUS_STYLES = {
    "OK": (GREEN, GREEN_SOFT),
    "Info": (BLUE, BLUE_SOFT),
    "Warning": (AMBER, AMBER_SOFT),
    "Error": (ORANGE, ORANGE_SOFT),
    "Critical": (ROSE, ROSE_SOFT),
    "Pendiente": (AMBER, AMBER_SOFT),
    "Aprobada": (GREEN, GREEN_SOFT),
    "Rechazada": (ROSE, ROSE_SOFT),
    "Publicando": (BLUE, BLUE_SOFT),
    "Publicada": (GREEN, GREEN_SOFT),
    "Fallida": (ROSE, ROSE_SOFT),
    # Estados de pedidos guardados en Supabase.
    "Borrador": (BLUE, BLUE_SOFT),
    "Pendiente archivo": (AMBER, AMBER_SOFT),
    "Validacion": (AMBER, AMBER_SOFT),
    "Validacion": (AMBER, AMBER_SOFT),
    "Calculado": (GREEN, GREEN_SOFT),
    "Guardado": (BLUE, BLUE_SOFT),
    "Recibido parcial": (AMBER, AMBER_SOFT),
    "Recibido completo": (GREEN, GREEN_SOFT),
    "Exportado": (GREEN, GREEN_SOFT),
    "Cancelado": (ROSE, ROSE_SOFT),
}


class ErpSharedUiMixin:
    def _show_working_overlay(self, title: str, message: str = "Trabajando...") -> tk.Toplevel:
        """Blocking work overlay anchored to the ERP window, not to a random monitor."""
        self.update_idletasks()
        overlay = tk.Toplevel(self)
        overlay.title(title)
        overlay.configure(bg=BG)
        overlay.transient(self)
        overlay.grab_set()
        overlay.resizable(False, False)
        try:
            overlay.attributes("-topmost", True)
        except Exception:
            pass

        width, height = 500, 210
        try:
            root_x = self.winfo_rootx()
            root_y = self.winfo_rooty()
            root_w = max(self.winfo_width(), 800)
            root_h = max(self.winfo_height(), 520)
            x = root_x + max((root_w - width) // 2, 0)
            y = root_y + max((root_h - height) // 2, 0)
            overlay.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            center_window(overlay, width, height)

        blocker = tk.Frame(overlay, bg=BG)
        blocker.pack(fill=tk.BOTH, expand=True)
        card = tk.Frame(blocker, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill=tk.BOTH, expand=True, padx=16, pady=16)
        tk.Label(card, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 15, "bold")).pack(anchor=tk.W, padx=18, pady=(18, 6))
        tk.Label(card, text=message, bg=CARD, fg=MUTED, font=("Segoe UI", 10), justify=tk.LEFT, wraplength=430).pack(anchor=tk.W, padx=18, pady=(0, 12))
        tk.Label(card, text="Ventana bloqueada mientras termina la operacion.", bg=CARD, fg=INDIGO, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, padx=18, pady=(0, 8))
        progress = ttk.Progressbar(card, mode="indeterminate", length=420)
        progress.pack(fill=tk.X, padx=18, pady=(0, 18))
        progress.start(12)

        overlay.protocol("WM_DELETE_WINDOW", lambda: None)
        try:
            overlay.lift(self)
            overlay.focus_force()
            overlay.update_idletasks()
            overlay.update()
        except Exception:
            pass
        return overlay

    def _close_working_overlay(self, overlay: tk.Toplevel | None) -> None:
        if overlay is None:
            return
        try:
            overlay.grab_release()
        except Exception:
            pass
        try:
            overlay.attributes("-topmost", False)
        except Exception:
            pass
        try:
            overlay.destroy()
        except Exception:
            pass

    def _metric(self, parent: tk.Frame, label: str, value: str, status: str, *, command: object | None = None) -> tk.Frame:
        fg, bg = STATUS_STYLES.get(status, STATUS_STYLES.get(str(status).strip().title(), (BLUE, BLUE_SOFT)))
        frame = tk.Frame(parent, bg=bg, highlightbackground=LINE, highlightthickness=1)
        tk.Label(frame, text=label.upper(), bg=bg, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor=tk.W, padx=14, pady=(12, 4))
        tk.Label(frame, text=value, bg=bg, fg=fg, font=("Segoe UI", 20, "bold")).pack(anchor=tk.W, padx=14, pady=(0, 12))
        if command is not None:
            for widget in (frame, *frame.winfo_children()):
                widget.bind("<Button-1>", lambda _event: command(), add="+")
                widget.configure(cursor="hand2")
        return frame

    def _provider_card(self, parent: tk.Frame, provider: str, status: str) -> tk.Frame:
        return self._simple_card(parent, provider, f"Proveedor activo - acceso a Calcular Pedido {provider}.", status)

    def _simple_card(self, parent: tk.Misc, title: str, subtitle: str, status: str) -> tk.Frame:
        frame = self._card(parent)
        top = tk.Frame(frame, bg=CARD)
        top.pack(fill=tk.X, padx=16, pady=(16, 8))
        tk.Label(top, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)
        self._status_chip(top, status, status).pack(side=tk.RIGHT)
        tk.Label(frame, text=subtitle, bg=CARD, fg=MUTED, wraplength=260, justify=tk.LEFT).pack(fill=tk.X, padx=16, pady=(0, 16))
        return frame

    def _status_row(self, parent: tk.Misc, title: str, subtitle: str, status: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=SOFT, highlightbackground=LINE, highlightthickness=1)
        text = tk.Frame(frame, bg=SOFT)
        text.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=12, pady=9)
        tk.Label(text, text=title, bg=SOFT, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        tk.Label(text, text=subtitle, bg=SOFT, fg=MUTED, font=("Segoe UI", 9)).pack(anchor=tk.W)
        self._status_chip(frame, status, status).pack(side=tk.RIGHT, padx=10)
        return frame

    def _status_chip(self, parent: tk.Misc, text: str, status: str) -> tk.Label:
        fg, bg = STATUS_STYLES.get(status, (BLUE, BLUE_SOFT))
        return tk.Label(parent, text=text, bg=bg, fg=fg, font=("Segoe UI", 8, "bold"), padx=9, pady=4)

    def _button(self, parent: tk.Misc, text: str, *, primary: bool = False, command: object | None = None) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=command,
            bg=INDIGO if primary else CARD,
            fg="white" if primary else "#334155",
            activebackground="#4338CA" if primary else SOFT,
            activeforeground="white" if primary else TEXT,
            bd=0,
            relief=tk.FLAT,
            padx=13,
            pady=9,
            font=("Segoe UI", 9, "bold"),
            highlightbackground=LINE,
            highlightthickness=1,
        )

    def _field(self, parent: tk.Misc, label: str, variable: tk.StringVar, *, show: str | None = None) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD)
        tk.Label(
            frame,
            text=label.upper(),
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 5))
        entry = tk.Entry(
            frame,
            textvariable=variable,
            show=show or "",
            bg="white",
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            highlightbackground=LINE,
            highlightcolor=INDIGO,
            highlightthickness=1,
            font=("Segoe UI", 10),
        )
        entry.pack(fill=tk.X, ipady=8)
        return frame

    def _combo_field(self, parent: tk.Misc, label: str, values: list[str], selected: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=CARD)
        tk.Label(
            frame,
            text=label.upper(),
            bg=CARD,
            fg=MUTED,
            font=("Segoe UI", 8, "bold"),
            anchor=tk.W,
        ).pack(fill=tk.X, pady=(0, 5))
        combo = ttk.Combobox(frame, values=values, state="readonly", font=("Segoe UI", 10))
        combo.set(selected)
        combo.pack(fill=tk.X, ipady=5)
        return frame

    def _constant_row(self, parent: tk.Misc, name: str, description: str, value: str, unit: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=SOFT, highlightbackground=LINE, highlightthickness=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Frame(frame, bg=SOFT)
        text.grid(row=0, column=0, sticky="ew", padx=12, pady=9)
        tk.Label(text, text=name, bg=SOFT, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(anchor=tk.W)
        tk.Label(text, text=description, bg=SOFT, fg=MUTED, font=("Segoe UI", 8)).pack(anchor=tk.W)
        entry = tk.Entry(frame, bg="white", fg=TEXT, relief=tk.FLAT, highlightbackground=LINE, highlightthickness=1, width=10)
        entry.insert(0, value)
        entry.grid(row=0, column=1, padx=(0, 8), pady=9, ipady=5)
        frame._entry = entry  # type: ignore[attr-defined]
        tk.Label(frame, text=unit, bg=SOFT, fg=MUTED, font=("Segoe UI", 9, "bold"), width=8, anchor=tk.W).grid(row=0, column=2, padx=(0, 12), pady=9)
        return frame

    def _setting_switch_row(self, parent: tk.Misc, title: str, subtitle: str) -> tk.Frame:
        frame = tk.Frame(parent, bg=SOFT, highlightbackground=LINE, highlightthickness=1)
        frame.columnconfigure(0, weight=1)
        text = tk.Frame(frame, bg=SOFT)
        text.grid(row=0, column=0, sticky="ew", padx=12, pady=9)
        tk.Label(text, text=title, bg=SOFT, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)
        tk.Label(text, text=subtitle, bg=SOFT, fg=MUTED, font=("Segoe UI", 9)).pack(anchor=tk.W)
        switch = tk.Frame(frame, bg=GREEN_SOFT, highlightbackground="#BBF7D0", highlightthickness=1, width=54, height=26)
        switch.grid(row=0, column=1, padx=12, pady=9)
        switch.grid_propagate(False)
        tk.Frame(switch, bg=GREEN, width=20, height=20).place(x=29, y=2)
        return frame

    def _card(self, parent: tk.Misc) -> tk.Frame:
        return tk.Frame(parent, bg=CARD, highlightbackground=LINE, highlightthickness=1)
