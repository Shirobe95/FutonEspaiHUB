from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from futonhub.cloud.services.inventory import list_cloud_inventory_items, search_cloud_inventory_items
from futonhub.ui.erp.shared_ui import (
    BG,
    CARD,
    INDIGO,
    INDIGO_SOFT,
    InventoryItem,
    LINE,
    ROSE,
    ROSE_SOFT,
    TEXT,
)


class ErpInventoryListMixin:
    def _build_inventory(self, parent: tk.Frame) -> None:
        if self._cloud_session is not None and not self._inventory_loaded_once and not self._inventory_loading:
            self.after(80, lambda: self._refresh_inventory(parent, self._inventory_query, allow_empty=True))

        top = tk.Frame(parent, bg=BG)
        top.pack(fill=tk.X, pady=(0, 16))
        top.columnconfigure(0, weight=1)
        query_var = tk.StringVar()
        search = tk.Entry(
            top,
            textvariable=query_var,
            bg=CARD,
            fg=TEXT,
            insertbackground=TEXT,
            relief=tk.FLAT,
            highlightbackground=LINE,
            highlightcolor=INDIGO,
            highlightthickness=1,
            font=("Segoe UI", 10),
        )
        search.insert(0, "")
        search.grid(row=0, column=0, sticky="ew", ipady=10)
        search.configure()
        self._button(top, "Buscar / recargar", primary=True, command=lambda: self._refresh_inventory(parent, query_var.get(), allow_empty=True)).grid(row=0, column=1, padx=(12, 0), sticky="e")
        self._button(top, "Crear nuevo artÃ­culo", primary=True, command=self._open_create_inventory_item_modal).grid(row=0, column=2, padx=(8, 0), sticky="e")
        self._button(top, "Exportacion de inventario", command=self._export_inventory_visible).grid(row=0, column=3, padx=(8, 0), sticky="e")
        self._button(top, "Diagnosticar estados", command=self._open_inventory_status_diagnostics_modal).grid(row=0, column=4, padx=(8, 0), sticky="e")
        search.bind("<Return>", lambda _event: self._refresh_inventory(parent, query_var.get(), allow_empty=True))
        tk.Label(
            parent,
            text=self._inventory_error
            or ("Cargando inventario real..." if self._inventory_loading else "Inventario real Supabase. Busca por ID, nombre, SKU, familia o referencia. WooCommerce no se toca desde esta vista."),
            bg=ROSE_SOFT if self._inventory_error else INDIGO_SOFT,
            fg=ROSE if self._inventory_error else "#4338CA",
            anchor=tk.W,
            justify=tk.LEFT,
            padx=12,
            pady=9,
        ).pack(fill=tk.X, pady=(0, 14))

        body = tk.Frame(parent, bg=BG)
        body.pack(fill=tk.BOTH, expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        table_card = self._card(body)
        table_card.grid(row=0, column=0, sticky="nsew", padx=(0, 14))
        table_card.rowconfigure(1, weight=1)
        table_card.columnconfigure(0, weight=1)
        head = tk.Frame(table_card, bg=CARD)
        head.grid(row=0, column=0, sticky="ew", padx=18, pady=(16, 10))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text="Tabla de inventario", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        columns = ["ID", "Tipo", "Nombre", "Contenido pack", "Precio Woo", "Stock", "Estado"]
        tree = ttk.Treeview(table_card, columns=columns, show="headings", height=14)
        widths = {"ID": 130, "Tipo": 92, "Nombre": 250, "Contenido pack": 330, "Precio Woo": 100, "Stock": 80, "Estado": 95}
        for column in columns:
            tree.heading(column, text=column, anchor=tk.CENTER)
            tree.column(column, width=widths[column], anchor=tk.CENTER)
        item_by_iid: dict[str, InventoryItem] = {}
        items = list(self._inventory_items)
        if items and self._selected_inventory_item not in items:
            self._selected_inventory_item = items[0]
        if not items:
            tree.insert("", tk.END, values=("-", "Sin inventario real cargado", "-", "-", "Info"))
        for item in items:
            content_preview = self._inventory_pack_contents_text(item, multiline=False)
            if len(content_preview) > 72:
                content_preview = content_preview[:71].rstrip() + "â€¦"
            iid = tree.insert(
                "",
                tk.END,
                values=(
                    item.code,
                    self._inventory_item_type_text(item),
                    item.name,
                    content_preview or "-",
                    item.price,
                    item.stock,
                    item.status,
                ),
            )
            item_by_iid[iid] = item
            if item == self._selected_inventory_item:
                tree.selection_set(iid)
                tree.focus(iid)
        tree.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))

        detail_host = tk.Frame(body, bg=BG)
        detail_host.grid(row=0, column=1, sticky="nsew")

        def render_detail(item: InventoryItem) -> None:
            self._selected_inventory_item = item
            self._render_inventory_detail(detail_host, item)

        def on_select(_event: object | None = None) -> None:
            selection = tree.selection()
            if not selection or selection[0] not in item_by_iid:
                return
            render_detail(item_by_iid[selection[0]])

        tree.bind("<<TreeviewSelect>>", on_select)
        self._render_inventory_detail(detail_host, self._selected_inventory_item)

    def _refresh_inventory(self, parent: tk.Frame, query: str, *, allow_empty: bool = False) -> None:
        query = query.strip()
        if not query and not allow_empty:
            self._inventory_error = "Introduce un texto o ID para buscar inventario real en Supabase."
            self._inventory_loading = False
            if self._current_key == "inventario" and parent.winfo_exists():
                self._show_view("inventario")
            return
        if self._cloud_session is None:
            self._inventory_error = "No hay sesion Supabase activa."
            self._inventory_loading = False
            if self._current_key == "inventario" and parent.winfo_exists():
                self._show_view("inventario")
            return
        self._inventory_query = query
        self._inventory_error = ""
        self._inventory_loading = True
        if self._current_key == "inventario" and parent.winfo_exists():
            self._show_view("inventario")

        def worker() -> None:
            try:
                if query:
                    server_rows = search_cloud_inventory_items(self._cloud_session, query, limit=100)
                    if self._inventory_query_is_code_like(query):
                        rows = server_rows
                    else:
                        all_rows = list_cloud_inventory_items(self._cloud_session, limit=500)
                        rows = self._merge_inventory_rows([server_rows, self._accent_insensitive_inventory_search(all_rows, query)])
                else:
                    rows = list_cloud_inventory_items(self._cloud_session, limit=150)
                items = [self._inventory_item_from_cloud_row(row) for row in rows]
                empty_msg = "Sin resultados reales visibles." if query and not items else ("No hay inventario real visible en Supabase." if not items else "")
                self.after(0, lambda: self._finish_inventory_refresh(items, empty_msg))
            except Exception as exc:
                self.after(0, lambda exc=exc: self._finish_inventory_refresh([], f"No se pudo leer inventario real Supabase: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_inventory_refresh(self, items: list[InventoryItem], error: str) -> None:
        self._inventory_items = list(items)
        self._inventory_error = error
        self._inventory_loading = False
        self._inventory_loaded_once = True
        self._selected_inventory_item = self._inventory_items[0] if self._inventory_items else None
        if self._current_key == "inventario":
            self._show_view("inventario")
