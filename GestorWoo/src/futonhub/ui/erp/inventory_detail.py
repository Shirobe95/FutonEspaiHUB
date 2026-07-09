from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk
from typing import Any

from futonhub.cloud.services.inventory import fetch_inventory_item_history
from futonhub.ui.erp.shared_ui import (
    BG,
    CARD,
    GREEN,
    INDIGO,
    INDIGO_SOFT,
    InventoryItem,
    LINE,
    MUTED,
    SOFT,
    TEXT,
)


class ErpInventoryDetailMixin:
    def _inventory_detail_rows(self, item: InventoryItem) -> list[tuple[str, str]]:
        stock_total = item.stock_total if item.stock_total != "-" else item.stock
        rows = [
            ("ID", item.code),
            ("Codigo HUB", self._inventory_pack_parent_code(item) or self._clean_inventory_value((item.raw or {}).get("hub_item_code"), "-")),
            ("Tipo item", self._clean_inventory_value((item.raw or {}).get("item_record_type") or (item.raw or {}).get("hub_search_record_type"), "simple")),
            ("Nombre", item.name),
            ("Precio Woo", item.price),
            ("Stock tienda", item.store_stock),
            ("Stock almacen", item.warehouse_stock),
            ("Stock total", f"{stock_total} unidades"),
            ("Familia", item.family),
            ("Subgrupo", item.subgroup),
            ("Materiales", item.material),
            ("Medidas", item.measures),
            ("M3", item.m3),
            ("Woo ID", item.woo_id),
            ("Woo Parent ID", item.woo_parent_id),
            ("SKU Woo", item.sku_woo),
            ("Nombre Woo", item.woo_name),
            ("Categorias Woo", item.woo_categories),
            ("Tipo Woo", item.woo_item_kind),
            ("Estado vinculo Woo", item.woo_link_status),
            ("Coste calculado pedido", item.order_calculated_price),
            ("Coste medio ponderado", item.weighted_average_cost),
            ("Cantidad en pedido proveedor", item.supplier_order_qty),
            ("Proveedor pedido", item.supplier_order_provider),
            ("Estado", item.status),
            ("Notas internas", item.notes),
        ]
        pack_text = self._inventory_pack_contents_text(item, multiline=False)
        if pack_text:
            rows.insert(3, ("Contenido pack", pack_text))
        return rows

    def _render_inventory_detail(self, parent: tk.Frame, item: InventoryItem | None) -> None:
        for child in parent.winfo_children():
            child.destroy()
        detail = self._card(parent)
        detail.pack(fill=tk.BOTH, expand=True)
        detail.rowconfigure(0, weight=1)
        detail.columnconfigure(0, weight=1)
        if item is None:
            empty = tk.Frame(detail, bg=CARD)
            empty.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
            tk.Label(empty, text="Detalles", bg=INDIGO_SOFT, fg=INDIGO, font=("Segoe UI", 9, "bold"), padx=10, pady=4).pack(anchor=tk.W)
            tk.Label(empty, text="Selecciona un item", bg=CARD, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(anchor=tk.W, pady=(12, 4))
            tk.Label(empty, text="El inventario se carga desde Supabase. Si no aparecen items, pulsa Buscar / recargar.", bg=CARD, fg=MUTED, wraplength=300, justify=tk.LEFT).pack(anchor=tk.W)
            return

        scroll_frame = tk.Frame(detail, bg=CARD)
        scroll_frame.grid(row=0, column=0, sticky="nsew", padx=18, pady=(16, 10))
        scroll_frame.rowconfigure(0, weight=1)
        scroll_frame.columnconfigure(0, weight=1)
        canvas = tk.Canvas(scroll_frame, bg=CARD, highlightthickness=0)
        scrollbar = ttk.Scrollbar(scroll_frame, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        scroll_area = tk.Frame(canvas, bg=CARD)
        window_id = canvas.create_window((0, 0), window=scroll_area, anchor="nw")
        scroll_area.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))

        tk.Label(scroll_area, text="Detalles", bg=INDIGO_SOFT, fg=INDIGO, font=("Segoe UI", 9, "bold"), padx=10, pady=4).pack(anchor=tk.W)
        tk.Label(scroll_area, text=item.name, bg=CARD, fg=TEXT, font=("Segoe UI", 16, "bold"), wraplength=300, justify=tk.LEFT).pack(
            anchor=tk.W,
            pady=(10, 2),
        )
        tk.Label(scroll_area, text=f"ID: {item.code}", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(anchor=tk.W, pady=(0, 14))

        for label, value in self._inventory_detail_rows(item)[:18]:
            self._detail_row(scroll_area, label, value).pack(fill=tk.X, pady=4)

        self._render_inventory_pack_inline_box(scroll_area, item, compact=True)

        actions = tk.Frame(detail, bg=CARD, highlightbackground=SOFT, highlightthickness=1)
        actions.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 18))
        detail_pad = (12, 7)
        self._button(actions, "Abrir detalle completo", primary=True, command=lambda: self._open_inventory_detail_window(item)).pack(
            fill=tk.X,
            padx=12,
            pady=detail_pad,
        )
        self._button(actions, "Movimiento stock", command=lambda: self._open_inventory_stock_preview_modal(item)).pack(
            fill=tk.X,
            padx=12,
            pady=(0, 7),
        )
        self._button(actions, "Agregar a Propuesta de precios", command=lambda: self._open_inventory_proposal_modal(item)).pack(
            fill=tk.X,
            padx=12,
            pady=(0, 12),
        )

    def _load_inventory_history(self, price_host: tk.Frame, stock_host: tk.Frame, item: InventoryItem) -> None:
        self._render_inventory_history_card(price_host, "Historial completo", [], "Cargando historial real...", item.price, INDIGO)
        self._render_inventory_history_card(stock_host, "Historial de stock", [], "Cargando historial real...", item.stock, GREEN)

        def history_worker() -> None:
            try:
                if self._cloud_session is None:
                    raise RuntimeError("No hay sesion Supabase activa.")
                history = fetch_inventory_item_history(self._cloud_session, int(item.code), limit=120)
                self.after(0, lambda: self._render_inventory_history(price_host, stock_host, history, item))
            except Exception as exc:
                self.after(0, lambda exc=exc: self._render_inventory_history_error(price_host, stock_host, str(exc), item))

        threading.Thread(target=history_worker, daemon=True).start()

    def _render_inventory_history(self, price_host: tk.Frame, stock_host: tk.Frame, history: list[dict[str, Any]], item: InventoryItem) -> None:
        price_history = [row for row in history if str(row.get("field") or "").lower() in {"price", "woo_price", "precio", "precio local", "price_local"}]
        stock_history = [row for row in history if str(row.get("field") or "").lower() in {"store_stock", "warehouse_stock", "stock", "stock_total"}]
        self._render_inventory_history_card(price_host, "Historial completo", price_history, "Sin historial de precios registrado", item.price, INDIGO)
        self._render_inventory_history_card(stock_host, "Historial de stock", stock_history, "Sin historial de stock registrado", item.stock, GREEN)

    def _render_inventory_history_error(self, price_host: tk.Frame, stock_host: tk.Frame, error: str, item: InventoryItem) -> None:
        self._render_inventory_history_card(price_host, "Historial completo", [], f"No se pudo cargar historial: {error}", item.price, INDIGO)
        self._render_inventory_history_card(stock_host, "Historial de stock", [], f"No se pudo cargar historial: {error}", item.stock, GREEN)

    def _render_inventory_history_card(self, parent: tk.Frame, title: str, history: list[dict[str, Any]], empty_text: str, current_value: str, color: str) -> None:
        for child in parent.winfo_children():
            child.destroy()
        frame = self._card(parent)
        frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(frame, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).pack(anchor=tk.W, padx=16, pady=(16, 4))
        tk.Label(frame, text="Historial real guardado en Supabase / caja negra.", bg=CARD, fg=MUTED).pack(anchor=tk.W, padx=16, pady=(0, 10))
        canvas = tk.Canvas(frame, height=145, bg="#FFFFFF", highlightbackground=SOFT, highlightthickness=1)
        canvas.pack(fill=tk.X, padx=16, pady=(0, 8))
        for x in range(24, 560, 86):
            canvas.create_line(x, 18, x, 124, fill=SOFT)
        for y in range(24, 130, 34):
            canvas.create_line(18, y, 560, y, fill=SOFT)
        points: list[tuple[float, float]] = []
        values: list[float] = []
        ordered = list(reversed(history[-8:]))
        for row in ordered:
            raw_value = row.get("after")
            try:
                values.append(float(str(raw_value).replace("EUR", "").replace(",", ".").strip()))
            except Exception:
                continue
        if values:
            minimum, maximum = min(values), max(values)
            spread = maximum - minimum or 1.0
            width = 520
            step = width / max(len(values) - 1, 1)
            for idx, value in enumerate(values):
                x = 24 + idx * step
                y = 124 - ((value - minimum) / spread) * 96
                points.append((x, y))
            for start, end in zip(points, points[1:]):
                canvas.create_line(*start, *end, fill=color, width=3)
            for x, y in points:
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill=color, outline=color)
        else:
            canvas.create_text(290, 72, text=empty_text, fill=MUTED, font=("Segoe UI", 10, "bold"))
        footer = tk.Frame(frame, bg=CARD)
        footer.pack(fill=tk.X, padx=16, pady=(0, 16))
        tk.Label(footer, text=f"Eventos: {len(history)}", bg=CARD, fg=MUTED, font=("Segoe UI", 9)).pack(side=tk.LEFT)
        tk.Label(footer, text=f"Valor actual: {current_value}", bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(side=tk.RIGHT)
