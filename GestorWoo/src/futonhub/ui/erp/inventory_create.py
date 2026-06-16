from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any

from futonhub.cloud.services.inventory import create_cloud_inventory_item, preview_create_cloud_inventory_item
from futonhub.ui.erp.shared_ui import BG, CARD, INDIGO_SOFT, LINE, MUTED, TEXT


class ErpInventoryCreateMixin:
    def _open_create_inventory_item_modal(self) -> None:
        if self._cloud_session is None:
            messagebox.showwarning("Inventario", "Inicia sesión en Supabase para crear artículos.")
            return

        win = tk.Toplevel(self)
        win.title("Crear nuevo artículo")
        win.configure(bg=BG)
        win.geometry("820x720")
        win.transient(self)
        win.grab_set()

        shell = tk.Frame(win, bg=BG)
        shell.pack(fill=tk.BOTH, expand=True, padx=18, pady=18)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(1, weight=1)

        tk.Label(
            shell,
            text="Crear nuevo artículo",
            bg=BG,
            fg=TEXT,
            font=("Segoe UI", 18, "bold"),
        ).grid(row=0, column=0, sticky="w")

        subtitle = tk.Label(
            shell,
            text="Se creará en Supabase inventory_items. No toca WooCommerce ni stock externo.",
            bg=BG,
            fg=MUTED,
            font=("Segoe UI", 10),
        )
        subtitle.grid(row=0, column=0, sticky="w", pady=(34, 0))

        card = self._card(shell)
        card.grid(row=1, column=0, sticky="nsew", pady=(18, 12))
        card.columnconfigure(0, weight=1)
        card.rowconfigure(0, weight=1)

        canvas = tk.Canvas(card, bg=CARD, highlightthickness=0)
        scroll = ttk.Scrollbar(card, orient=tk.VERTICAL, command=canvas.yview)
        form = tk.Frame(canvas, bg=CARD)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)
        canvas.create_window((0, 0), window=form, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")

        def _sync_scroll(_event: object | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))

        form.bind("<Configure>", _sync_scroll)

        fields: dict[str, tk.Entry | tk.Text] = {}
        defaults = {
            "commercial_status": "Normal",
            "packages": "1",
            "store_stock": "0",
            "warehouse_stock": "0",
        }

        def add_entry(row: int, col: int, key: str, label: str, *, width: int = 22) -> None:
            tk.Label(form, text=label, bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(
                row=row, column=col, sticky="w", padx=(18 if col == 0 else 12, 8), pady=(12, 4)
            )
            entry = tk.Entry(
                form,
                bg="white",
                fg=TEXT,
                relief=tk.FLAT,
                highlightbackground=LINE,
                highlightthickness=1,
                font=("Segoe UI", 10),
                width=width,
            )
            entry.insert(0, defaults.get(key, ""))
            entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, 18 if col == 2 else 8), pady=(12, 4), ipady=7)
            fields[key] = entry

        add_entry(0, 0, "item_id", "ID / Referencia *")
        add_entry(0, 2, "heca_reference", "HECA reference")
        add_entry(1, 0, "name", "Nombre *")
        add_entry(1, 2, "commercial_status", "Estado comercial")
        add_entry(2, 0, "family", "Familia")
        add_entry(2, 2, "subgroup", "Subgrupo")
        add_entry(3, 0, "size", "Medida")
        add_entry(3, 2, "materials", "Materiales")
        add_entry(4, 0, "cubic_meters", "M3 unidad")
        add_entry(4, 2, "rotation_c", "Rotación C")
        add_entry(5, 0, "packages", "Bultos")
        add_entry(5, 2, "primary_supplier_price", "Precio proveedor")
        add_entry(6, 0, "pascal_price", "Precio Pascal")
        add_entry(6, 2, "woo_sku", "Woo SKU")
        add_entry(7, 0, "store_stock", "Stock tienda")
        add_entry(7, 2, "warehouse_stock", "Stock almacén")

        tk.Label(form, text="Notas", bg=CARD, fg=TEXT, font=("Segoe UI", 9, "bold")).grid(
            row=8, column=0, sticky="nw", padx=(18, 8), pady=(12, 8)
        )
        notes = tk.Text(form, height=5, bg="white", fg=TEXT, relief=tk.FLAT, highlightbackground=LINE, highlightthickness=1)
        notes.grid(row=8, column=1, columnspan=3, sticky="ew", padx=(0, 18), pady=(12, 8))
        fields["notes"] = notes

        help_box = tk.Label(
            form,
            text="Campos obligatorios: ID y Nombre. Si HECA reference queda vacío, se usará el ID con ceros a la izquierda. Bultos por defecto = 1.",
            bg=INDIGO_SOFT,
            fg="#3730A3",
            wraplength=720,
            justify=tk.LEFT,
            padx=12,
            pady=10,
        )
        help_box.grid(row=9, column=0, columnspan=4, sticky="ew", padx=18, pady=(8, 16))

        def get_payload() -> dict[str, Any]:
            data: dict[str, Any] = {}
            for key, widget in fields.items():
                if isinstance(widget, tk.Text):
                    data[key] = widget.get("1.0", tk.END).strip()
                else:
                    data[key] = widget.get().strip()
            if not data.get("heca_reference") and data.get("item_id"):
                try:
                    data["heca_reference"] = str(int(str(data["item_id"]).strip())).zfill(7)
                except Exception:
                    pass
            return data

        footer = tk.Frame(shell, bg=BG)
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)

        status_var = tk.StringVar(value="Listo para crear.")
        tk.Label(footer, textvariable=status_var, bg=BG, fg=MUTED, anchor=tk.W).grid(row=0, column=0, sticky="ew")

        def preview() -> None:
            try:
                result = preview_create_cloud_inventory_item(self._cloud_session, get_payload())
            except Exception as exc:
                messagebox.showerror("Validación", str(exc))
                return
            payload = result.get("payload") or {}
            if result.get("exists"):
                existing = result.get("existing") or {}
                messagebox.showwarning(
                    "Artículo existente",
                    f"Ya existe el item {existing.get('item_id')}:\n{existing.get('name') or '-'}\n\nNo se creará duplicado.",
                )
                return
            lines = [
                "PREVIEW NUEVO ARTÍCULO",
                "",
                f"ID: {payload.get('item_id')}",
                f"Nombre: {payload.get('name')}",
                f"Familia: {payload.get('family') or '-'}",
                f"Subgrupo: {payload.get('subgroup') or '-'}",
                f"Medida: {payload.get('size') or '-'}",
                f"M3: {payload.get('cubic_meters') or '-'}",
                f"Rotación C: {payload.get('rotation_c') or '-'}",
                f"Bultos: {payload.get('packages') or '-'}",
                f"Precio proveedor: {payload.get('primary_supplier_price') or '-'}",
                f"Precio Pascal: {payload.get('pascal_price') or '-'}",
                "",
                "No toca WooCommerce. No toca stock externo.",
            ]
            messagebox.showinfo("Preview", "\n".join(lines))

        def save() -> None:
            try:
                result = preview_create_cloud_inventory_item(self._cloud_session, get_payload())
            except Exception as exc:
                messagebox.showerror("Validación", str(exc))
                return
            if result.get("exists"):
                existing = result.get("existing") or {}
                messagebox.showwarning(
                    "Artículo existente",
                    f"Ya existe el item {existing.get('item_id')}:\n{existing.get('name') or '-'}",
                )
                return
            payload = result.get("payload") or {}
            confirm_text = (
                f"Se creará el artículo {payload.get('item_id')}:\n"
                f"{payload.get('name')}\n\n"
                "Se guardará en Supabase con log y snapshot.\n"
                "No se tocará WooCommerce.\n\n¿Continuar?"
            )
            if not messagebox.askyesno("Crear artículo", confirm_text):
                return
            try:
                created = create_cloud_inventory_item(self._cloud_session, get_payload())
            except Exception as exc:
                messagebox.showerror("Crear artículo", f"No se pudo crear el artículo.\n\n{exc}")
                return
            messagebox.showinfo("Artículo creado", f"Artículo creado correctamente.\nOperation ID: {created.get('operation_id')}")
            win.destroy()
            self._inventory_loaded_once = False
            self._refresh_inventory(self._content, str(payload.get("item_id") or ""), allow_empty=True)

        self._button(footer, "Cancelar", command=win.destroy).grid(row=0, column=1, padx=(8, 0), sticky="e")
        self._button(footer, "Preview", command=preview).grid(row=0, column=2, padx=(8, 0), sticky="e")
        self._button(footer, "Crear artículo", primary=True, command=save).grid(row=0, column=3, padx=(8, 0), sticky="e")
