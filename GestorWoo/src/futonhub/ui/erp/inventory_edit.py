from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from futonhub.cloud.services.inventory import update_inventory_item_fields
from futonhub.ui.erp.shared_ui import BG, CARD, INDIGO, INDIGO_SOFT, InventoryItem, LINE, MUTED, SOFT, TEXT
from futonhub.ui.windowing import center_window


INVENTORY_DETAIL_EDITABLE_FIELDS: tuple[tuple[str, str], ...] = (
    ("Nombre", "name"),
    ("Familia", "family"),
    ("Subgrupo", "subgroup"),
    ("Medidas", "size"),
    ("Materiales", "materials"),
    ("M3 unidad", "cubic_meters"),
    ("Rotacion C", "rotation_c"),
    ("Bultos", "packages"),
    ("Precio proveedor", "primary_supplier_price"),
    ("Precio Pascal", "pascal_price"),
    ("Notas internas", "notes"),
)

INVENTORY_DETAIL_READONLY_RESERVED_FIELDS: tuple[tuple[str, str], ...] = (
    ("Estado comercial", "commercial_status"),
    ("HECA reference", "heca_reference"),
    ("Woo SKU", "woo_sku"),
    ("Stock tienda", "store_stock"),
    ("Stock almacen", "warehouse_stock"),
)


class ErpInventoryEditMixin:
    def _inventory_editable_initial_values(self, item: InventoryItem) -> dict[str, str]:
        raw = item.raw or {}
        return {
            "name": str(raw.get("name") or item.name or ""),
            "family": str(raw.get("family") or ("" if item.family in {"Sin definir", "-"} else item.family)),
            "subgroup": str(raw.get("subgroup") or ("" if item.subgroup in {"Sin definir", "-"} else item.subgroup)),
            "materials": str(raw.get("materials") or ("" if item.material in {"Sin definir", "-"} else item.material)),
            "size": str(raw.get("size") or ("" if item.measures in {"Sin definir", "-"} else item.measures)),
            "cubic_meters": "" if raw.get("cubic_meters") in (None, "") else str(raw.get("cubic_meters")),
            "rotation_c": "" if raw.get("rotation_c") in (None, "") else str(raw.get("rotation_c")),
            "packages": "" if raw.get("packages") in (None, "") else str(raw.get("packages")),
            "primary_supplier_price": "" if raw.get("primary_supplier_price") in (None, "") else str(raw.get("primary_supplier_price")),
            "pascal_price": "" if raw.get("pascal_price") in (None, "") else str(raw.get("pascal_price")),
            "commercial_status": str(raw.get("commercial_status") or "Normal"),
            "heca_reference": str(raw.get("heca_reference") or ""),
            "woo_sku": str(raw.get("woo_sku") or item.sku_woo or ""),
            "store_stock": "" if raw.get("store_stock") in (None, "") else str(raw.get("store_stock")),
            "warehouse_stock": "" if raw.get("warehouse_stock") in (None, "") else str(raw.get("warehouse_stock")),
            "notes": str(raw.get("notes") or ""),
        }

    def _inventory_detail_editable_rows(self) -> tuple[tuple[str, str], ...]:
        return INVENTORY_DETAIL_EDITABLE_FIELDS

    def _inventory_detail_readonly_reserved_fields(self) -> tuple[tuple[str, str], ...]:
        return INVENTORY_DETAIL_READONLY_RESERVED_FIELDS

    def _inventory_detail_readonly_reserved_rows(self, initial: dict[str, str]) -> list[tuple[str, str]]:
        return [(label, initial.get(field) or "Sin definir") for label, field in INVENTORY_DETAIL_READONLY_RESERVED_FIELDS]

    def _inventory_detail_editable_initial_values(self, initial: dict[str, str]) -> dict[str, str]:
        return {field: initial.get(field, "") for _label, field in INVENTORY_DETAIL_EDITABLE_FIELDS}

    def _collect_inventory_detail_changes(self, initial: dict[str, str], vars_by_field: dict[str, tk.StringVar]) -> dict[str, tuple[str, str]]:
        changes: dict[str, tuple[str, str]] = {}
        for field, old_value in initial.items():
            new_value = vars_by_field[field].get().strip()
            old_clean = str(old_value or "").strip()
            if new_value != old_clean:
                changes[field] = (old_clean, new_value)
        return changes

    def _editable_detail_row(self, parent: tk.Misc, label: str, variable: tk.StringVar) -> tk.Frame:
        frame = tk.Frame(parent, bg=SOFT, highlightbackground=LINE, highlightthickness=1)
        frame.columnconfigure(1, weight=1)
        tk.Label(frame, text=label, bg=SOFT, fg=MUTED, font=("Segoe UI", 9), anchor=tk.W).grid(row=0, column=0, sticky="w", padx=12, pady=9)
        entry = tk.Entry(frame, textvariable=variable, bg="white", fg=TEXT, insertbackground=TEXT, relief=tk.FLAT, highlightbackground=LINE, highlightcolor=INDIGO, highlightthickness=1, font=("Segoe UI", 9))
        entry.grid(row=0, column=1, sticky="ew", padx=(0, 12), pady=8, ipady=4)
        return frame

    def _open_inventory_changes_review(
        self,
        owner: tk.Toplevel,
        item: InventoryItem,
        changes: dict[str, tuple[str, str]],
        *,
        on_discard: object | None,
        on_applied: object | None,
    ) -> None:
        if not changes:
            messagebox.showinfo("Inventario", "No hay cambios pendientes.")
            return
        review = tk.Toplevel(owner)
        review.title("Revisar cambios del item")
        review.configure(bg=BG)
        review.transient(owner)
        review.grab_set()
        center_window(review, 760, 520)
        review.columnconfigure(0, weight=1)
        review.rowconfigure(1, weight=1)

        header = tk.Frame(review, bg=BG, highlightbackground=LINE, highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Cambios detectados", bg=INDIGO_SOFT, fg=INDIGO, font=("Segoe UI", 9, "bold"), padx=10, pady=4).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 4))
        tk.Label(header, text=f"{item.name} - {item.code}", bg=BG, fg=TEXT, font=("Segoe UI", 16, "bold")).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))

        table_card = self._card(review)
        table_card.grid(row=1, column=0, sticky="nsew", padx=18, pady=18)
        table_card.rowconfigure(0, weight=1)
        table_card.columnconfigure(0, weight=1)
        columns = ("Campo", "Valor anterior", "Valor nuevo")
        tree = ttk.Treeview(table_card, columns=columns, show="headings", height=10)
        for column, width in {"Campo": 170, "Valor anterior": 250, "Valor nuevo": 250}.items():
            tree.heading(column, text=column, anchor=tk.CENTER)
            tree.column(column, width=width, anchor=tk.CENTER)
        for field, (before, after) in changes.items():
            tree.insert("", tk.END, values=(field, before or "Sin definir", after or "Sin definir"))
        tree.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)

        footer = tk.Frame(review, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        footer.columnconfigure(0, weight=1)
        if on_discard is not None:
            self._button(footer, "Descartar cambios", command=lambda: (review.destroy(), on_discard())).grid(row=0, column=0, sticky="w")
        self._button(footer, "Cancelar", command=review.destroy).grid(row=0, column=1, padx=(8, 0), sticky="e")
        self._button(
            footer,
            "Aceptar y guardar",
            primary=True,
            command=lambda: self._apply_inventory_detail_changes(review, item, changes, on_applied),
        ).grid(row=0, column=2, padx=(8, 0), sticky="e")

    def _apply_inventory_detail_changes(self, review: tk.Toplevel, item: InventoryItem, changes: dict[str, tuple[str, str]], on_applied: object | None) -> None:
        if self._cloud_session is None:
            messagebox.showerror("Inventario", "No hay sesion Supabase activa.")
            return
        payload = {field: after for field, (_before, after) in changes.items()}
        for child in review.winfo_children():
            child.configure(cursor="watch") if hasattr(child, "configure") else None
        review.update_idletasks()

        def worker() -> None:
            try:
                result = update_inventory_item_fields(
                    self._cloud_session,
                    int(item.code),
                    payload,
                    notes="Cambio aceptado desde detalle completo de Inventario UI ERP.",
                )
                self.after(0, lambda: finish_ok(result))
            except Exception as exc:
                self.after(0, lambda exc=exc: finish_error(exc))

        def finish_ok(result: dict[str, Any]) -> None:
            if review.winfo_exists():
                review.destroy()
            messagebox.showinfo("Inventario", f"Item actualizado.\noperation_id: {result.get('operation_id')}")
            if on_applied is not None:
                on_applied()

        def finish_error(exc: Exception) -> None:
            if review.winfo_exists():
                for child in review.winfo_children():
                    child.configure(cursor="") if hasattr(child, "configure") else None
            messagebox.showerror("Inventario", f"No se pudo guardar el item: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _after_inventory_item_updated(self, detail_window: tk.Toplevel) -> None:
        if detail_window.winfo_exists():
            detail_window.destroy()
        if self._content is not None and self._current_key == "inventario":
            self._inventory_loaded_once = False
            self._refresh_inventory(self._content, self._inventory_query, allow_empty=True)
