from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk

from futonhub.cloud.services.inventory import list_cloud_inventory_items_by_ids
from futonhub.services.catalog_operational_baseline import CatalogOperationalBaseline
from futonhub.ui.erp.catalog_filters import (
    CatalogFilterConfigurationError,
    CatalogFilterSelection,
    PhysicalCatalogSnapshot,
    build_catalog_filter_bar,
    catalog_filter_options,
    filter_catalog_rows,
)
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
    def _inventory_operational_baseline(self) -> CatalogOperationalBaseline:
        baseline = self.__dict__.get("_inventory_operational_baseline_cache")
        if isinstance(baseline, CatalogOperationalBaseline):
            return baseline
        baseline = CatalogOperationalBaseline()
        self._inventory_operational_baseline_cache = baseline
        return baseline

    def _build_inventory(self, parent: tk.Frame) -> None:
        if self._cloud_session is not None and not self._inventory_loaded_once and not self._inventory_loading:
            self.after(80, lambda: self._refresh_inventory(parent, "", allow_empty=True))

        top = tk.Frame(parent, bg=BG)
        top.pack(fill=tk.X, pady=(0, 16))
        selection = self._inventory_catalog_filter_selection()
        build_catalog_filter_bar(
            top,
            selection=selection,
            options=catalog_filter_options(self._inventory_catalog_loaded_rows(), selection),
            on_selection_change=self._inventory_catalog_filter_selection_changed,
            on_apply=self._apply_inventory_catalog_filters,
            on_clear=self._clear_inventory_catalog_filters,
            button_factory=self._button,
            colors={"card": CARD, "line": LINE, "text": TEXT, "indigo": INDIGO},
        )
        actions = tk.Frame(top, bg=BG)
        actions.pack(fill=tk.X)
        self._button(actions, "Crear nuevo articulo", primary=True, command=self._open_create_inventory_item_modal).pack(side=tk.LEFT)
        self._button(actions, "Exportacion de inventario", command=self._export_inventory_visible).pack(side=tk.LEFT, padx=(8, 0))
        self._button(actions, "Diagnosticar estados", command=self._open_inventory_status_diagnostics_modal).pack(side=tk.LEFT, padx=(8, 0))
        status_text = self._inventory_error or (self._inventory_catalog_status_text() if self._inventory_loading else "")
        if status_text:
            tk.Label(
                parent,
                text=status_text,
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
        table_viewport = tk.Frame(table_card, bg=CARD)
        table_viewport.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 18))
        table_viewport.rowconfigure(0, weight=1)
        table_viewport.columnconfigure(0, weight=1)
        tree = ttk.Treeview(table_viewport, columns=columns, show="headings", height=14)
        widths = {"ID": 130, "Tipo": 92, "Nombre": 250, "Contenido pack": 330, "Precio Woo": 100, "Stock": 80, "Estado": 95}
        for column in columns:
            tree.heading(column, text=column, anchor=tk.CENTER)
            tree.column(column, width=widths[column], anchor=tk.CENTER)
        item_by_iid: dict[str, InventoryItem] = {}
        items = self._inventory_filtered_items()
        if items and self._selected_inventory_item not in items:
            self._selected_inventory_item = items[0]
        if not items:
            empty_text = "Sin resultados para los filtros aplicados" if self._inventory_catalog_applied_selection().has_hierarchy or self._inventory_catalog_applied_selection().query else "Sin inventario fisico elegible cargado"
            tree.insert("", tk.END, values=("-", empty_text, "-", "-", "Info"))
        for item in items:
            content_preview = self._inventory_pack_contents_text(item, multiline=False)
            if len(content_preview) > 72:
                content_preview = content_preview[:71].rstrip() + "..."
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
        vertical_scroll = ttk.Scrollbar(table_viewport, orient=tk.VERTICAL, command=tree.yview)
        horizontal_scroll = ttk.Scrollbar(table_viewport, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=vertical_scroll.set, xscrollcommand=horizontal_scroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vertical_scroll.grid(row=0, column=1, sticky="ns")
        horizontal_scroll.grid(row=1, column=0, sticky="ew")

        def scroll_page(direction: int) -> str:
            tree.yview_scroll(direction, "pages")
            return "break"

        tree.bind("<Prior>", lambda _event: scroll_page(-1))
        tree.bind("<Next>", lambda _event: scroll_page(1))

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

    def _inventory_catalog_filter_selection(self) -> CatalogFilterSelection:
        return getattr(self, "_inventory_catalog_filter_selection_state", CatalogFilterSelection())

    def _inventory_catalog_applied_selection(self) -> CatalogFilterSelection:
        return getattr(self, "_inventory_catalog_applied_filter_state", CatalogFilterSelection())

    def _inventory_catalog_loaded_rows(self) -> list[dict[str, object]]:
        return list(getattr(self, "_inventory_catalog_source_rows", []))

    def _inventory_catalog_snapshot(self) -> PhysicalCatalogSnapshot:
        snapshot = getattr(self, "_inventory_catalog_snapshot_cache", None)
        if isinstance(snapshot, PhysicalCatalogSnapshot):
            return snapshot
        path = getattr(self, "_inventory_catalog_snapshot_path", None)
        snapshot = PhysicalCatalogSnapshot.load(path)
        self._inventory_catalog_snapshot_cache = snapshot
        return snapshot

    def _inventory_catalog_filter_selection_changed(self, selection: CatalogFilterSelection) -> None:
        self._inventory_catalog_filter_selection_state = selection
        if self._current_key == "inventario":
            self._show_view("inventario")

    def _apply_inventory_catalog_filters(self, selection: CatalogFilterSelection) -> None:
        self._inventory_catalog_filter_selection_state = selection
        self._inventory_catalog_applied_filter_state = selection
        self._inventory_query = selection.query
        if self._current_key == "inventario":
            self._show_view("inventario")

    def _clear_inventory_catalog_filters(self) -> None:
        selection = CatalogFilterSelection()
        self._inventory_catalog_filter_selection_state = selection
        self._inventory_catalog_applied_filter_state = selection
        self._inventory_query = ""
        if self._current_key == "inventario":
            self._show_view("inventario")

    def _inventory_filtered_items(self) -> list[InventoryItem]:
        selection = self._inventory_catalog_applied_selection()
        source_rows = filter_catalog_rows(self._inventory_catalog_loaded_rows(), selection)
        item_by_id = {
            str((item.raw or {}).get("item_id") or item.code): item
            for item in self._inventory_items
        }
        return [
            item_by_id[str(row.get("item_id") or "")]
            for row in source_rows
            if str(row.get("item_id") or "") in item_by_id
        ]

    def _inventory_catalog_status_text(self) -> str:
        if self._inventory_loading:
            return "Cargando inventario fisico elegible..."
        return ""

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
        try:
            snapshot = self._inventory_catalog_snapshot()
        except CatalogFilterConfigurationError as exc:
            self._inventory_catalog_source_rows = []
            self._finish_inventory_refresh([], f"No se puede cargar el catalogo fisico: {exc}")
            return
        selection = self._inventory_catalog_filter_selection().with_query(query)
        self._inventory_catalog_filter_selection_state = selection
        self._inventory_catalog_applied_filter_state = selection
        self._inventory_query = query
        self._inventory_error = ""
        self._inventory_loading = True
        if self._current_key == "inventario" and parent.winfo_exists():
            self._show_view("inventario")

        def worker() -> None:
            try:
                rows = list_cloud_inventory_items_by_ids(self._cloud_session, snapshot.item_ids)
                eligible_rows = snapshot.eligible_live_rows(rows)
                eligible_rows = self._inventory_operational_baseline().enrich_rows(eligible_rows)
                items = [self._inventory_item_from_cloud_row(row) for row in eligible_rows]
                missing_count = len(snapshot.item_ids) - len(eligible_rows)
                warning = ""
                if missing_count:
                    warning = f"Aviso de catalogo: {missing_count} registros no cumplen el contrato operativo y no se muestran."
                self.after(0, lambda: self._finish_inventory_refresh(items, warning, eligible_rows))
            except Exception as exc:
                self.after(0, lambda exc=exc: self._finish_inventory_refresh([], f"No se pudo leer inventario fisico Supabase: {exc}", []))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_inventory_refresh(self, items: list[InventoryItem], error: str, source_rows: list[dict[str, object]] | None = None) -> None:
        self._inventory_items = list(items)
        if source_rows is not None:
            self._inventory_catalog_source_rows = list(source_rows)
        self._inventory_error = error
        self._inventory_loading = False
        self._inventory_loaded_once = True
        self._selected_inventory_item = self._inventory_items[0] if self._inventory_items else None
        if self._current_key == "inventario":
            self._show_view("inventario")
