from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from futonhub.core.config import load_settings
from futonhub.ui.theme import C_BG, apply_theme
from futonhub.ui.windowing import center_window
from futonhub.cloud.operational import (
    create_real_price_proposal,
    format_existing_price_proposal_preview,
    format_price_heart_attack_tests,
    format_real_price_proposal_preview,
    format_woocommerce_publish_preview,
    format_woocommerce_publish_result,
    list_real_price_proposals,
    preview_existing_price_proposal,
    preview_real_price_proposal,
    preview_woocommerce_publish,
    price_heart_attack_tests,
    publish_woocommerce_price,
    review_latest_real_price_proposal,
    search_cloud_products,
)


class CloudPriceBoardMixin:
    def _cloud_search_products(self) -> None:
        """Buscador visual operativo desde Supabase.

        Permite localizar un producto/variación y crear una propuesta desde la
        misma ventana, sin copiar IDs de memoria.
        """
        if not self._ensure_cloud_session():
            return

        win = tk.Toplevel(self)
        win.title("Buscar producto / variación")
        center_window(win, 1050, 620)
        win.minsize(900, 520)
        win.configure(bg=C_BG)
        apply_theme(win)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Buscar item en Supabase", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))
        ttk.Label(
            frame,
            text="Busca producto o variación, selecciona una fila y crea una propuesta. WooCommerce no se toca.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        top = ttk.Frame(frame)
        top.pack(fill=tk.X, pady=(0, 10))
        query_var = tk.StringVar(value="Test Product")
        ttk.Label(top, text="Buscar:").pack(side=tk.LEFT)
        entry = ttk.Entry(top, textvariable=query_var, width=42)
        entry.pack(side=tk.LEFT, padx=(6, 8))
        ttk.Button(top, text="Buscar", command=lambda: reload_rows()).pack(side=tk.LEFT)

        columns = ("kind", "woo_id", "name", "type", "price", "stock", "warning")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=15)
        headings = {
            "kind": "Tipo",
            "woo_id": "Woo ID",
            "name": "Producto/variación",
            "type": "Clase",
            "price": "Precio",
            "stock": "Stock",
            "warning": "Aviso",
        }
        widths = {"kind": 80, "woo_id": 80, "name": 360, "type": 95, "price": 90, "stock": 100, "warning": 300}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True)

        row_by_iid: dict[str, dict] = {}

        def reload_rows() -> None:
            query = query_var.get().strip()
            if not query:
                messagebox.showinfo("Buscar productos", "Escribe un texto para buscar.", parent=win)
                return
            try:
                rows = search_cloud_products(self._cloud_session, query, limit=40)
            except Exception as exc:
                messagebox.showerror("Buscar productos", f"No se pudo buscar en Supabase.\n\n{exc}", parent=win)
                return
            tree.delete(*tree.get_children())
            row_by_iid.clear()
            for row in rows:
                stock = f"{row.get('stock_status') or '-'} {row.get('stock_quantity') if row.get('stock_quantity') is not None else ''}".strip()
                iid = tree.insert("", tk.END, values=(
                    row.get("item_kind"),
                    row.get("woo_id"),
                    row.get("name"),
                    row.get("type"),
                    row.get("price") or "-",
                    stock,
                    row.get("price_warning") or "",
                ))
                row_by_iid[iid] = row

        def selected_row() -> dict | None:
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Buscar productos", "Selecciona un item primero.", parent=win)
                return None
            return row_by_iid.get(sel[0])

        def create_from_selected() -> None:
            row = selected_row()
            if not row:
                return
            self._create_price_proposal_from_item(
                str(row.get("item_kind") or ""),
                int(row.get("woo_id")),
                str(row.get("name") or ""),
                parent=win,
            )

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Crear propuesta", command=create_from_selected).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Cerrar", command=win.destroy).pack(side=tk.RIGHT)
        entry.bind("<Return>", lambda _e: reload_rows())
        tree.bind("<Double-1>", lambda _e: create_from_selected())
        reload_rows()

    def _create_price_proposal_from_item(self, item_kind: str, woo_id: int, item_name: str = "", parent: tk.Misc | None = None) -> None:
        """Crea propuesta con preview previo obligatorio."""
        if not self._ensure_cloud_session():
            return
        parent = parent or self
        new_price_text = simpledialog.askstring(
            "Nueva propuesta",
            f"Item seleccionado:\n[{item_kind}] {woo_id} · {item_name}\n\nNuevo precio propuesto:",
            parent=parent,
        )
        if not new_price_text:
            return
        notes = simpledialog.askstring(
            "Nueva propuesta",
            "Notas de la propuesta:",
            initialvalue="Propuesta creada desde búsqueda del HUB.",
            parent=parent,
        ) or ""
        try:
            proposed = float(new_price_text.replace(",", "."))
            preview = preview_real_price_proposal(self._cloud_session, item_kind, int(woo_id), proposed, notes, load_settings())
        except CloudAuditError as exc:
            messagebox.showerror("Preview propuesta", str(exc), parent=parent)
            return
        except Exception as exc:
            messagebox.showerror("Preview propuesta", f"No se pudo crear preview.\n\n{exc}", parent=parent)
            return

        preview_text = format_real_price_proposal_preview(preview)
        safety = (preview.get("price_safety") or {}).get("status")
        if safety == "ERROR":
            self._show_text_window("Propuesta bloqueada", preview_text)
            return
        if not messagebox.askyesno(
            "Confirmar propuesta",
            preview_text + "\n\n¿Crear esta propuesta interna?",
            parent=parent,
        ):
            return
        ack = safety == "WARNING"
        try:
            result = create_real_price_proposal(
                self._cloud_session,
                item_kind.strip().lower(),
                int(woo_id),
                proposed,
                notes,
                load_settings(),
                acknowledge_price_warning=ack,
            )
        except CloudAuditError as exc:
            messagebox.showerror("Propuesta real interna", str(exc), parent=parent)
            return
        except Exception as exc:
            messagebox.showerror("Propuesta real interna", f"No se pudo crear la propuesta.\n\n{exc}", parent=parent)
            return
        prop = result["proposal"]
        messagebox.showinfo(
            "Propuesta creada",
            "Propuesta real interna creada/actualizada correctamente.\n\n"
            f"Operación: {result['operation_id']}\n"
            f"Item: [{prop.get('item_kind')}] {prop.get('item_woo_id')} · {prop.get('name')}\n"
            f"Precio anterior: {result['old_price']}\n"
            f"Precio propuesto: {result['new_price']}\n"
            f"Validación: {(result.get('price_safety') or {}).get('status', 'OK')}\n\n"
            "WooCommerce no fue tocado.",
            parent=parent,
        )

    def _cloud_real_price_proposal(self) -> None:
        """Entrada manual mantenida para desarrollo; ahora también muestra preview."""
        if not self._ensure_cloud_session():
            return
        item_kind = simpledialog.askstring("Propuesta real interna", "Tipo de item: product o variation", initialvalue="variation", parent=self)
        if not item_kind:
            return
        woo_id_text = simpledialog.askstring("Propuesta real interna", "Woo ID del producto/variación en Supabase:", parent=self)
        if not woo_id_text:
            return
        try:
            self._create_price_proposal_from_item(item_kind.strip().lower(), int(woo_id_text.strip()), parent=self)
        except ValueError:
            messagebox.showerror("Propuesta real interna", "Woo ID debe ser numérico.", parent=self)

    def _cloud_review_real_price_proposal(self, decision: str, proposal_id: str | None = None) -> None:
        if not self._ensure_cloud_session():
            return
        role = (self._cloud_session.role or "").lower()
        if role not in {"admin", "worker"}:
            messagebox.showwarning("Revisar propuesta", "Solo admin o worker pueden aprobar/rechazar propuestas.", parent=self)
            return
        label = "aprobar" if decision == "approved" else "rechazar"
        target = proposal_id or "la última propuesta real pendiente no TEST"
        if not messagebox.askyesno(
            "Revisar propuesta real interna",
            f"Esto va a {label} {target}.\n\n"
            "No se publicará nada en WooCommerce. Se generará snapshot y log.\n\n¿Continuar?",
            parent=self,
        ):
            return
        try:
            result = review_latest_real_price_proposal(self._cloud_session, decision, proposal_id, load_settings())
        except CloudAuditError as exc:
            messagebox.showerror("Revisar propuesta real interna", str(exc), parent=self)
            return
        except Exception as exc:
            messagebox.showerror("Revisar propuesta real interna", f"No se pudo revisar la propuesta.\n\n{exc}", parent=self)
            return
        prop = result["proposal"]
        messagebox.showinfo(
            "Revisar propuesta real interna",
            "Propuesta real interna revisada correctamente.\n\n"
            f"Operación: {result['operation_id']}\n"
            f"Decisión: {result['decision']}\n"
            f"Item: [{prop.get('item_kind')}] {prop.get('item_woo_id')} · {prop.get('name')}\n\n"
            "WooCommerce no fue tocado.",
            parent=self,
        )

    def _cloud_price_proposals_board(self) -> None:
        if not self._ensure_cloud_session():
            return

        win = tk.Toplevel(self)
        win.title("Propuestas de precio")
        center_window(win, 1100, 650)
        win.minsize(960, 560)
        win.configure(bg=C_BG)
        apply_theme(win)

        frame = ttk.Frame(win, padding=14)
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Propuestas de precio internas", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 8))
        ttk.Label(
            frame,
            text="Aprobar/rechazar es trabajo operativo: admin y worker. Publicar en WooCommerce sigue siendo solo admin.",
            style="Muted.TLabel",
        ).pack(anchor=tk.W, pady=(0, 10))

        controls = ttk.Frame(frame)
        controls.pack(fill=tk.X, pady=(0, 8))
        status_var = tk.StringVar(value="pending")
        ttk.Label(controls, text="Estado:").pack(side=tk.LEFT)
        status_combo = ttk.Combobox(
            controls,
            textvariable=status_var,
            values=["pending", "approved", "publishing", "rejected", "published", "error", "cancelled", "all"],
            width=14,
            state="readonly",
        )
        status_combo.pack(side=tk.LEFT, padx=(6, 12))
        ttk.Button(controls, text="Recargar", command=lambda: reload_rows()).pack(side=tk.LEFT)

        columns = ("status", "item", "woo_id", "old", "new", "delta", "created", "proposal_id")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=16)
        headings = {
            "status": "Estado",
            "item": "Producto/variación",
            "woo_id": "Woo ID",
            "old": "Precio anterior",
            "new": "Propuesto",
            "delta": "Dif.",
            "created": "Creado",
            "proposal_id": "Proposal ID",
        }
        widths = {"status": 90, "item": 330, "woo_id": 80, "old": 105, "new": 105, "delta": 100, "created": 160, "proposal_id": 260}
        for col in columns:
            tree.heading(col, text=headings[col])
            tree.column(col, width=widths[col], anchor=tk.W)
        tree.pack(fill=tk.BOTH, expand=True)
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=tree.yview)
        y_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        tree.configure(yscrollcommand=y_scroll.set)

        row_by_iid: dict[str, dict] = {}

        def selected_proposal_id() -> str | None:
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("Propuestas", "Selecciona una propuesta primero.", parent=win)
                return None
            return str(row_by_iid.get(sel[0], {}).get("id") or "")

        def reload_rows() -> None:
            try:
                rows = list_real_price_proposals(self._cloud_session, status=status_var.get(), limit=100)
            except Exception as exc:
                messagebox.showerror("Propuestas", f"No se pudieron cargar propuestas.\n\n{exc}", parent=win)
                return
            tree.delete(*tree.get_children())
            row_by_iid.clear()
            for row in rows:
                old = row.get("old_price")
                newp = row.get("new_price")
                try:
                    delta = "" if old in (None, "") or newp in (None, "") else f"{float(newp) - float(old):.2f}"
                except Exception:
                    delta = ""
                iid = tree.insert("", tk.END, values=(
                    row.get("status"),
                    row.get("name"),
                    row.get("item_woo_id"),
                    old,
                    newp,
                    delta,
                    row.get("created_at"),
                    row.get("id"),
                ))
                row_by_iid[iid] = row

        def show_proposal_preview() -> None:
            pid = selected_proposal_id()
            if not pid:
                return
            try:
                preview = preview_existing_price_proposal(self._cloud_session, pid, load_settings())
            except Exception as exc:
                messagebox.showerror("Preview propuesta", f"No se pudo generar preview de propuesta.\n\n{exc}", parent=win)
                return
            self._show_text_window("Preview propuesta", format_existing_price_proposal_preview(preview))

        def review_selected(decision: str) -> None:
            pid = selected_proposal_id()
            if not pid:
                return
            try:
                preview = preview_existing_price_proposal(self._cloud_session, pid, load_settings())
            except Exception as exc:
                messagebox.showerror("Revisar propuesta", f"No se pudo generar preview.\n\n{exc}", parent=win)
                return
            action = "APROBAR" if decision == "approved" else "RECHAZAR"
            preview_text = format_existing_price_proposal_preview(preview)
            if not messagebox.askyesno(
                f"Confirmar {action.lower()}",
                preview_text + f"\n\n¿Confirmas {action} esta propuesta?",
                parent=win,
            ):
                return
            self._cloud_review_real_price_proposal(decision, pid)
            reload_rows()

        def preview_selected() -> None:
            if not self._require_admin_session():
                return
            pid = selected_proposal_id()
            if not pid:
                return
            try:
                result = preview_woocommerce_publish(self._cloud_session, proposal_id=pid, limit=1, settings=load_settings())
            except Exception as exc:
                messagebox.showerror("Preview WooCommerce", f"No se pudo generar preview.\n\n{exc}", parent=win)
                return
            self._show_text_window("Preview WooCommerce", format_woocommerce_publish_preview(result))

        def publish_selected() -> None:
            if not self._require_admin_session():
                return
            pid = selected_proposal_id()
            if not pid:
                return
            try:
                preview = preview_woocommerce_publish(self._cloud_session, proposal_id=pid, limit=1, settings=load_settings())
            except Exception as exc:
                messagebox.showerror("Publicar WooCommerce", f"No se pudo generar preview previo.\n\n{exc}", parent=win)
                return
            rows = preview.get("rows") or []
            if not rows:
                messagebox.showwarning("Publicar WooCommerce", "No hay propuesta approved para publicar con ese ID.", parent=win)
                return
            row = rows[0]
            if row.get("status") == "ERROR":
                self._show_text_window("Publicación bloqueada", format_woocommerce_publish_preview(preview))
                return
            ack = False
            if row.get("status") == "WARNING":
                if not messagebox.askyesno(
                    "Warnings amarillos",
                    "La propuesta tiene warnings amarillos. Revisa el preview.\n\n¿Confirmas que quieres continuar con publicación protegida?",
                    parent=win,
                ):
                    return
                ack = True
            confirm = simpledialog.askstring(
                "Confirmación requerida",
                "Escribe PUBLICAR para cambiar el precio real en WooCommerce:",
                parent=win,
            )
            if (confirm or "").strip().upper() != "PUBLICAR":
                messagebox.showinfo("Publicación cancelada", "No se publicó nada en WooCommerce.", parent=win)
                return
            try:
                result = publish_woocommerce_price(
                    self._cloud_session,
                    proposal_id=pid,
                    confirm="PUBLICAR",
                    acknowledge_warnings=ack,
                    settings=load_settings(),
                )
            except Exception as exc:
                messagebox.showerror("Publicar WooCommerce", f"No se pudo publicar.\n\n{exc}", parent=win)
                return
            self._show_text_window("Publicación WooCommerce", format_woocommerce_publish_result(result))
            reload_rows()

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(buttons, text="Preview propuesta", command=show_proposal_preview).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Aprobar", command=lambda: review_selected("approved")).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Rechazar", command=lambda: review_selected("rejected")).pack(side=tk.LEFT, padx=(0, 8))
        if self._is_authenticated_admin():
            ttk.Button(buttons, text="Preview Woo", command=preview_selected).pack(side=tk.LEFT, padx=(18, 8))
            ttk.Button(buttons, text="Publicar Woo", command=publish_selected).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(buttons, text="Cerrar", command=win.destroy).pack(side=tk.RIGHT)
        status_combo.bind("<<ComboboxSelected>>", lambda _e: reload_rows())
        reload_rows()

    def _cloud_price_heart_attack_tests(self) -> None:
        """Prueba de estrés de validaciones de precio desde la UI.

        No crea propuestas, no modifica Supabase y no toca WooCommerce.
        """
        if not self._ensure_cloud_session():
            return
        item_kind = simpledialog.askstring(
            "Test estrés precios",
            "Tipo de item: product o variation",
            initialvalue="variation",
            parent=self,
        )
        if not item_kind:
            return
        item_kind = item_kind.strip().lower()
        if item_kind not in {"product", "variation"}:
            messagebox.showerror("Test estrés precios", "Tipo de item inválido. Usa product o variation.", parent=self)
            return
        woo_id_text = simpledialog.askstring(
            "Test estrés precios",
            "Woo ID del producto/variación en Supabase:",
            parent=self,
        )
        if not woo_id_text:
            return
        try:
            woo_id = int(woo_id_text.strip())
        except ValueError:
            messagebox.showerror("Test estrés precios", "Woo ID debe ser numérico.", parent=self)
            return
        try:
            result = price_heart_attack_tests(self._cloud_session, item_kind, woo_id, load_settings())
        except Exception as exc:
            messagebox.showerror("Test estrés precios", f"No se pudieron ejecutar las pruebas.\n\n{exc}", parent=self)
            return
        self._show_text_window("Test estrés precios", format_price_heart_attack_tests(result))
