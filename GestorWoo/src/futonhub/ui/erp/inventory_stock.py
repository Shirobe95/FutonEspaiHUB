from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox
from typing import Any

from futonhub.cloud.services.inventory import (
    format_internal_inventory_preview,
    preview_internal_inventory_update,
    update_internal_inventory_item,
)
from futonhub.core.config import load_settings
from futonhub.ui.erp.shared_ui import BG, CARD, INDIGO_SOFT, InventoryItem, LINE, MUTED, TEXT
from futonhub.ui.windowing import center_window


class ErpInventoryStockMixin:
    def _inventory_stock_form_values(self, store_text: str, warehouse_text: str, notes: str) -> tuple[str | None, str | None, str]:
        clean_notes = str(notes or "").strip()
        if not clean_notes:
            raise ValueError("Indica el motivo del movimiento de stock.")
        return (store_text.strip() or None, warehouse_text.strip() or None, clean_notes)

    def _inventory_stock_preview_text(self, item: InventoryItem, store_text: str, warehouse_text: str, notes: str) -> str:
        store_value, warehouse_value, clean_notes = self._inventory_stock_form_values(store_text, warehouse_text, notes)
        preview = preview_internal_inventory_update(
            self._cloud_session,
            int(item.code),
            store_value,
            warehouse_value,
            clean_notes,
        )
        return format_internal_inventory_preview(preview)

    def _apply_inventory_stock_change(self, item: InventoryItem, store_text: str, warehouse_text: str, notes: str) -> dict[str, Any]:
        store_value, warehouse_value, clean_notes = self._inventory_stock_form_values(store_text, warehouse_text, notes)
        return update_internal_inventory_item(
            self._cloud_session,
            int(item.code),
            store_value,
            warehouse_value,
            clean_notes,
            load_settings(),
        )

    def _open_inventory_stock_preview_modal(self, item: InventoryItem) -> None:
        if self._cloud_session is None:
            messagebox.showerror("Inventario", "No hay sesion Supabase activa.")
            return
        if not item.raw:
            messagebox.showinfo("Inventario", "Este item es visual/mock. Busca un item real antes de generar preview.")
            return
        win = tk.Toplevel(self)
        win.title("Preview cambio stock interno")
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        center_window(win, 760, 560)
        win.columnconfigure(0, weight=1)
        header = tk.Frame(win, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        header.grid(row=0, column=0, sticky="ew", padx=18, pady=(18, 0))
        header.columnconfigure(0, weight=1)
        tk.Label(header, text="Preview cambio stock interno", bg=CARD, fg=TEXT, font=("Segoe UI", 16, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(16, 2))
        tk.Label(header, text=f"{item.code} - {item.name}", bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", padx=18, pady=(0, 16))
        self._button(header, "Cerrar", command=win.destroy).grid(row=0, column=1, rowspan=2, padx=18, pady=16)

        body = tk.Frame(win, bg=CARD, highlightbackground=LINE, highlightthickness=1)
        body.grid(row=1, column=0, sticky="ew", padx=18, pady=12)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        store_var = tk.StringVar()
        warehouse_var = tk.StringVar()
        notes_var = tk.StringVar(value="Cambio interno desde detalle de Inventario.")
        self._field(body, "Nuevo stock tienda", store_var).grid(row=0, column=0, sticky="ew", padx=(16, 8), pady=(16, 10))
        self._field(body, "Nuevo stock almacen", warehouse_var).grid(row=0, column=1, sticky="ew", padx=(8, 16), pady=(16, 10))
        self._field(body, "Motivo", notes_var).grid(row=1, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        result = tk.Text(body, height=12, bg="#0F172A", fg="#E2E8F0", insertbackground="#E2E8F0", relief=tk.FLAT, wrap=tk.WORD, font=("Consolas", 9))
        result.insert("1.0", "Genera preview para validar el movimiento. No toca WooCommerce.")
        result.configure(state=tk.DISABLED)
        result.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 16))

        def render_preview(text: str) -> None:
            if not result.winfo_exists():
                return
            result.configure(state=tk.NORMAL)
            result.delete("1.0", tk.END)
            result.insert("1.0", text)
            result.configure(state=tk.DISABLED)

        def generate_preview() -> None:
            render_preview("Generando preview real...")

            def worker() -> None:
                try:
                    text = self._inventory_stock_preview_text(item, store_var.get(), warehouse_var.get(), notes_var.get())
                except Exception as exc:
                    text = f"ERROR: {exc}"
                self.after(0, lambda: render_preview(text))

            threading.Thread(target=worker, daemon=True).start()

        def apply_change() -> None:
            try:
                preview_text = self._inventory_stock_preview_text(item, store_var.get(), warehouse_var.get(), notes_var.get())
            except Exception as exc:
                messagebox.showerror("Preview inventario", f"No se pudo generar preview.\n\n{exc}", parent=win)
                return
            render_preview(preview_text)
            if not messagebox.askyesno("Confirmar cambio inventario", preview_text + "\n\nAplicar movimiento interno?", parent=win):
                return

            def worker() -> None:
                try:
                    result_data = self._apply_inventory_stock_change(item, store_var.get(), warehouse_var.get(), notes_var.get())
                    self.after(0, lambda: finish_ok(result_data))
                except Exception as exc:
                    self.after(0, lambda exc=exc: messagebox.showerror("Inventario", f"No se pudo aplicar el cambio.\n\n{exc}", parent=win))

            threading.Thread(target=worker, daemon=True).start()

        def finish_ok(result_data: dict[str, Any]) -> None:
            messagebox.showinfo(
                "Inventario actualizado",
                "Movimiento interno aplicado correctamente.\n\n"
                f"Operacion: {result_data.get('operation_id')}\n"
                f"Item ID: {item.code}\n\n"
                "Supabase actualizado. WooCommerce no fue tocado.\n"
                "Caja negra: audit_log + operation_snapshot generados.",
                parent=win,
            )
            self._after_inventory_item_updated(win)

        footer = tk.Frame(win, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        self._button(footer, "Aplicar movimiento", primary=True, command=apply_change).pack(side=tk.RIGHT)
        self._button(footer, "Generar preview", command=generate_preview).pack(side=tk.RIGHT, padx=(0, 8))
        self._button(footer, "Cancelar", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))
