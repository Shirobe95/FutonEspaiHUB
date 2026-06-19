from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from futonhub.core.codes import is_inventory_pack_row
from futonhub.core.config import load_settings
from futonhub.ui.theme import C_BG, apply_theme
from futonhub.ui.windowing import center_window
from futonhub.cloud.operational import (
    format_internal_inventory_preview,
    preview_internal_inventory_update,
    search_cloud_inventory_items,
    update_internal_inventory_item,
)


class CloudInventoryBoardMixin:
    def _cloud_inventory_internal_board(self) -> None:
        """Buscador y editor seguro de inventario interno Supabase.

        No toca WooCommerce. Genera preview, snapshot y audit_log al aplicar.
        """
        if not self._ensure_cloud_session():
            return

        win = tk.Toplevel(self)
        win.title("Inventario interno Supabase")
        center_window(win, 1380, 820)
        win.minsize(1120, 720)
        win.configure(bg=C_BG)
        apply_theme(win)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Inventario interno", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(
            frame,
            text="Busca items simples, alias y packs por código exacto/componente. Previsualiza cambios de stock solo en Supabase.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(0, 10))
        query_var = tk.StringVar(value="0201001")
        ttk.Label(top, text="Buscar:").pack(side=tk.LEFT)
        entry = ttk.Entry(top, textvariable=query_var, width=42)
        entry.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(top, text="Buscar", command=lambda: reload_rows()).pack(side=tk.LEFT)
        ttk.Button(top, text="Ver contenido pack", command=lambda: show_pack_contents_popup()).pack(side=tk.LEFT, padx=(8, 0))

        columns = ("item_id", "code", "type", "name", "relation", "contents", "store", "warehouse", "woo", "link")
        table_frame = ttk.Frame(frame)
        table_frame.pack(fill=tk.BOTH, expand=True)
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", height=13)
        headings = {
            "item_id": "Item ID",
            "code": "Código",
            "type": "Tipo",
            "name": "Nombre",
            "relation": "Relación",
            "contents": "Contenido pack",
            "store": "Stock tienda",
            "warehouse": "Stock almacén",
            "woo": "Woo",
            "link": "Estado link",
        }
        widths = {"item_id": 86, "code": 125, "type": 82, "name": 235, "relation": 155, "contents": 330, "store": 80, "warehouse": 92, "woo": 220, "link": 100}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor=tk.W)
        yscroll = ttk.Scrollbar(table_frame, orient=tk.VERTICAL, command=tree.yview)
        xscroll = ttk.Scrollbar(table_frame, orient=tk.HORIZONTAL, command=tree.xview)
        tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        tree.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")
        xscroll.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)

        detail_frame = ttk.LabelFrame(frame, text="Detalle del item / contenido del pack", padding=8)
        detail_frame.pack(fill=tk.X, pady=(10, 0))
        detail_text = tk.Text(detail_frame, height=8, wrap=tk.WORD, bg="#ffffff", relief=tk.FLAT)
        detail_text.pack(fill=tk.X, expand=False)
        detail_text.configure(state=tk.DISABLED)

        row_by_iid: dict[str, dict] = {}

        def _short_text(value: object, max_len: int = 92) -> str:
            text_value = str(value or "")
            if len(text_value) <= max_len:
                return text_value
            return text_value[: max_len - 1].rstrip() + "…"

        def _format_qty(value: object) -> str:
            try:
                n = float(str(value or "1").replace(",", "."))
                if n.is_integer():
                    return str(int(n))
                return (f"{n:.3f}").rstrip("0").rstrip(".")
            except Exception:
                return str(value or "1")

        def _pack_code_from_row(row: dict) -> str:
            return str(
                row.get("hub_search_code")
                or row.get("hub_item_code")
                or row.get("heca_reference")
                or ""
            ).strip()

        def _load_pack_components_live(row: dict) -> list[dict]:
            """Carga componentes directamente al seleccionar un pack.

            v55.1: el resumen de la tabla puede venir vacío si Supabase/RLS no devuelve
            la consulta bulk de enriquecimiento. Esta carga bajo demanda hace visible el
            contenido real del pack en el panel de detalle.
            """
            code = _pack_code_from_row(row)
            if not code:
                return []
            try:
                resp = (
                    self._cloud_session.client.table("inventory_item_components")
                    .select("parent_item_code,component_item_code,component_name,quantity,relation_type,woo_id,woo_sku")
                    .eq("parent_item_code", code)
                    .eq("relation_type", "component")
                    .order("component_item_code", desc=False)
                    .execute()
                )
                return [dict(x) for x in (getattr(resp, "data", None) or [])]
            except Exception:
                return []

        def _components_to_text(components: list[dict], multiline: bool = False) -> str:
            parts: list[str] = []
            for comp in components:
                code = comp.get("component_item_code") or "-"
                qty = _format_qty(comp.get("quantity") or 1)
                name = comp.get("component_name") or ""
                line = f"{code} x{qty}" + (f" · {name}" if name else "")
                parts.append(line)
            if multiline:
                return "\n".join(f"- {part}" for part in parts)
            return "; ".join(parts)

        def _components_from_woo_sku(row: dict, multiline: bool = False) -> str:
            sku = str(row.get("woo_sku") or "").strip()
            if "|" not in sku:
                return ""
            counts: dict[str, int] = {}
            order: list[str] = []
            for raw in sku.split("|"):
                token = raw.strip()
                if not token:
                    continue
                if token not in counts:
                    counts[token] = 0
                    order.append(token)
                counts[token] += 1
            parts = [f"{token} x{counts[token]}" for token in order]
            if multiline:
                return "\n".join(f"- {part}" for part in parts)
            return "; ".join(parts)

        def _is_pack_row(row: dict) -> bool:
            return is_inventory_pack_row(row)

        def _selected_row_silent() -> dict | None:
            sel = tree.selection()
            return row_by_iid.get(sel[0]) if sel else None

        def show_pack_contents_popup() -> None:
            row = _selected_row_silent()
            if not row:
                messagebox.showinfo("Contenido pack", "Selecciona primero un pack o alias en la tabla.", parent=win)
                return
            code = _pack_code_from_row(row) or str(row.get("item_id") or "-")
            popup = tk.Toplevel(win)
            popup.title(f"Contenido pack · {code}")
            center_window(popup, 820, 420)
            popup.minsize(720, 340)
            popup.configure(bg=C_BG)
            apply_theme(popup)
            box = ttk.Frame(popup, padding=14)
            box.pack(fill=tk.BOTH, expand=True)
            ttk.Label(box, text=f"{code} · {row.get('name') or row.get('woo_name') or '-'}", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
            txt = tk.Text(box, height=14, wrap=tk.WORD, bg="#ffffff", relief=tk.FLAT)
            txt.pack(fill=tk.BOTH, expand=True)
            components = _load_pack_components_live(row) if _is_pack_row(row) else []
            if components:
                txt.insert(tk.END, "Contenido completo desde inventory_item_components:\n")
                txt.insert(tk.END, _components_to_text(components, multiline=True))
            else:
                fallback = row.get("hub_pack_components_multiline") or _components_from_woo_sku(row, multiline=True)
                if fallback:
                    txt.insert(tk.END, "Contenido visible por SKU/relación:\n")
                    txt.insert(tk.END, str(fallback))
                    txt.insert(tk.END, "\n\nNota: si faltan nombres, la tabla de componentes no devolvió detalle al HUB, pero el SKU compuesto permite ver los códigos.")
                else:
                    txt.insert(tk.END, "No encontré componentes para este item.\n\n")
                    txt.insert(tk.END, f"Código usado: {code}\n")
                    txt.insert(tk.END, f"Tipo: {row.get('hub_search_record_type') or row.get('item_record_type') or '-'}\n")
                    txt.insert(tk.END, f"Woo ID: {row.get('woo_id') or '-'}\n")
                    txt.insert(tk.END, f"Woo SKU: {row.get('woo_sku') or '-'}\n")
            txt.configure(state=tk.DISABLED)
            ttk.Button(box, text="Cerrar", command=popup.destroy).pack(anchor=tk.E, pady=(10, 0))

        def update_detail(_event=None) -> None:
            sel = tree.selection()
            row = row_by_iid.get(sel[0]) if sel else None
            detail_text.configure(state=tk.NORMAL)
            detail_text.delete("1.0", tk.END)
            if not row:
                detail_text.insert(tk.END, "Selecciona un item para ver su detalle.")
            else:
                code = row.get("hub_search_code") or row.get("hub_item_code") or row.get("heca_reference") or row.get("item_id")
                record_type = row.get("hub_search_record_type") or row.get("item_record_type") or "simple"
                detail_text.insert(tk.END, f"{code} · {record_type} · item_id={row.get('item_id')}\n")
                detail_text.insert(tk.END, f"Nombre: {row.get('name') or row.get('woo_name') or '-'}\n")
                contents = row.get("hub_pack_components_multiline") or row.get("hub_pack_components_text")
                if _is_pack_row(row):
                    live_components = _load_pack_components_live(row)
                    if live_components:
                        contents = _components_to_text(live_components, multiline=True)
                        row["hub_pack_components_text"] = _components_to_text(live_components, multiline=False)
                        row["hub_pack_components_multiline"] = contents
                    elif not contents:
                        contents = _components_from_woo_sku(row, multiline=True)
                if contents:
                    detail_text.insert(tk.END, "Contenido del pack / relación:\n")
                    detail_text.insert(tk.END, str(contents))
                    detail_text.insert(tk.END, "\n")
                elif _is_pack_row(row):
                    detail_text.insert(tk.END, "Contenido del pack: no visible todavía. Usa el botón Ver contenido pack para abrirlo en ventana aparte.\n")
                related = row.get("hub_search_related_code")
                if related:
                    qty = row.get("hub_search_relation_quantity") or ""
                    detail_text.insert(tk.END, f"Encontrado por: {row.get('hub_search_relation_type') or 'rel'} {related} x{qty}\n")
                detail_text.insert(tk.END, f"Woo: {row.get('woo_id') or '-'} · SKU: {row.get('woo_sku') or '-'}")
            detail_text.configure(state=tk.DISABLED)

        def reload_rows() -> None:
            query = query_var.get().strip()
            if not query:
                messagebox.showinfo("Inventario", "Escribe un texto para buscar.", parent=win)
                return
            try:
                rows = search_cloud_inventory_items(self._cloud_session, query, limit=60)
            except Exception as exc:
                messagebox.showerror("Inventario", f"No se pudo buscar inventario.\n\n{exc}", parent=win)
                return
            tree.delete(*tree.get_children())
            row_by_iid.clear()
            for row in rows:
                code = row.get("hub_search_code") or row.get("hub_item_code") or row.get("heca_reference") or row.get("item_id")
                record_type = row.get("hub_search_record_type") or row.get("item_record_type") or "simple"
                related = row.get("hub_search_related_code")
                relation_type = row.get("hub_search_relation_type")
                qty = row.get("hub_search_relation_quantity")
                if related:
                    qty_text = f" x{qty}" if qty not in (None, "") else ""
                    relation_text = f"{relation_type or 'rel'}: {related}{qty_text}"
                else:
                    relation_text = row.get("hub_search_match_type") or "directo"
                contents_text = row.get("hub_pack_components_text") or ""
                if not contents_text and _is_pack_row(row):
                    contents_text = _components_from_woo_sku(row, multiline=False) or "Selecciona / botón Ver contenido"
                woo_text = f"[{row.get('woo_item_kind') or record_type or '-'}] {row.get('woo_id') or '-'} · {row.get('woo_name') or row.get('name') or '-'}"
                iid = tree.insert("", tk.END, values=(
                    row.get("item_id"),
                    code,
                    record_type,
                    row.get("name") or row.get("woo_name") or "-",
                    relation_text,
                    _short_text(contents_text),
                    row.get("store_stock"),
                    row.get("warehouse_stock"),
                    woo_text,
                    row.get("woo_link_status") or "-",
                ))
                row_by_iid[iid] = row
            update_detail()

        def selected_row() -> dict | None:
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Inventario", "Selecciona un item primero.", parent=win)
                return None
            return row_by_iid.get(sel[0])

        def apply_change() -> None:
            row = selected_row()
            if not row:
                return
            item_id = int(row.get("item_id"))
            store_text = simpledialog.askstring(
                "Cambio inventario",
                f"Item: {row.get('name') or row.get('woo_name')}\nStock tienda actual: {row.get('store_stock')}\n\nNuevo stock tienda (vacío = no cambiar):",
                parent=win,
            )
            warehouse_text = simpledialog.askstring(
                "Cambio inventario",
                f"Stock almacén actual: {row.get('warehouse_stock')}\n\nNuevo stock almacén (vacío = no cambiar):",
                parent=win,
            )
            if not (store_text or warehouse_text):
                messagebox.showinfo("Cambio inventario", "No indicaste ningún cambio.", parent=win)
                return
            notes = simpledialog.askstring(
                "Cambio inventario",
                "Nota del cambio:",
                initialvalue="Cambio interno desde HUB.",
                parent=win,
            ) or ""
            try:
                preview = preview_internal_inventory_update(self._cloud_session, item_id, store_text or None, warehouse_text or None, notes)
                preview_text = format_internal_inventory_preview(preview)
            except Exception as exc:
                messagebox.showerror("Preview inventario", f"No se pudo generar preview.\n\n{exc}", parent=win)
                return
            if not messagebox.askyesno("Confirmar cambio inventario", preview_text + "\n\n¿Aplicar cambio interno?", parent=win):
                return
            try:
                result = update_internal_inventory_item(self._cloud_session, item_id, store_text or None, warehouse_text or None, notes, load_settings())
            except Exception as exc:
                messagebox.showerror("Inventario", f"No se pudo aplicar el cambio.\n\n{exc}", parent=win)
                return
            messagebox.showinfo(
                "Inventario actualizado",
                "Cambio interno aplicado correctamente.\n\n"
                f"Operación: {result['operation_id']}\n"
                f"Item ID: {item_id}\n\n"
                "Supabase actualizado. WooCommerce no fue tocado.\n"
                "Caja negra: audit_log + operation_snapshot generados.",
                parent=win,
            )
            reload_rows()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Aplicar cambio interno", command=apply_change).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Ver contenido pack", command=show_pack_contents_popup).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(buttons, text="Cerrar", command=win.destroy).pack(side=tk.RIGHT)
        entry.bind("<Return>", lambda _e: reload_rows())
        tree.bind("<<TreeviewSelect>>", update_detail)
        def _double_click_row(_event=None) -> None:
            row = _selected_row_silent()
            if row and _is_pack_row(row):
                show_pack_contents_popup()
            else:
                apply_change()

        tree.bind("<Double-1>", _double_click_row)
        reload_rows()
