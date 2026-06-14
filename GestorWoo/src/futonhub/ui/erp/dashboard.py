from __future__ import annotations

import tkinter as tk
from datetime import datetime, timezone
from tkinter import ttk
from typing import Any

from futonhub.cloud.services.orders import list_cloud_supplier_orders, order_display_name as cloud_order_display_name
from futonhub.cloud.services.price_proposals import list_real_price_proposals
from futonhub.cloud.services.security_logs import list_audit_logs as list_security_audit_logs
from futonhub.ui.erp.shared_ui import AMBER, AMBER_SOFT, BG, CARD, GREEN, GREEN_SOFT, MUTED, TEXT
from futonhub.ui.windowing import center_window


class ErpDashboardMixin:
    def _build_dashboard(self, parent: tk.Frame) -> None:
        self._page_header(
            parent,
            "Principal",
            "Dashboard",
            "Cabina de mando: atenciÃ³n diaria, actividad reciente y estado del sistema.",
        )

        data = self._dashboard_collect_data()
        kpis = data.get("kpis", {})
        errors = data.get("errors", [])
        if errors:
            tk.Label(
                parent,
                text=" Â· ".join(errors[:3]),
                bg=AMBER_SOFT,
                fg=AMBER,
                anchor=tk.W,
                justify=tk.LEFT,
                padx=12,
                pady=9,
                wraplength=980,
            ).pack(fill=tk.X, pady=(0, 14))

        metrics = tk.Frame(parent, bg=BG)
        metrics.pack(fill=tk.X, pady=(0, 18))
        metric_data = [
            ("Pedidos abiertos", str(kpis.get("open_orders", 0)), "Info", "Pedidos abiertos", data.get("open_order_items", []), "calcular"),
            ("En validaciÃ³n", str(kpis.get("validation_orders", 0)), "Warning" if kpis.get("validation_orders", 0) else "OK", "Pedidos en validaciÃ³n", data.get("validation_order_items", []), "calcular"),
            ("Recepciones parciales", str(kpis.get("partial_receipts", 0)), "Warning" if kpis.get("partial_receipts", 0) else "OK", "Recepciones parciales", data.get("partial_receipt_items", []), "calcular"),
            ("Propuestas pendientes", str(kpis.get("pending_proposals", 0)), "Warning" if kpis.get("pending_proposals", 0) else "OK", "Propuestas pendientes", data.get("proposal_items", []), "precios"),
            ("Errores hoy", str(kpis.get("errors_today", 0)), "Error" if kpis.get("errors_today", 0) else "OK", "Errores hoy", data.get("error_items", []), "seguridad"),
        ]
        for i, (label, value, status, title, items, target) in enumerate(metric_data):
            metrics.columnconfigure(i, weight=1)
            self._metric(
                metrics,
                label,
                value,
                status,
                command=lambda title=title, items=items, target=target: self._dashboard_show_attention(title, items, target),
            ).grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 8, 0))

        # Dashboard responsive:
        # el admin puede tener mucha actividad reciente; por eso el cuerpo va
        # dentro de un canvas con scroll vertical. AsÃ­ ninguna tarjeta queda
        # "fuera del mapa" cuando los logs crecen.
        viewport = tk.Frame(parent, bg=BG)
        viewport.pack(fill=tk.BOTH, expand=True)
        viewport.columnconfigure(0, weight=1)
        viewport.rowconfigure(0, weight=1)

        canvas = tk.Canvas(viewport, bg=BG, highlightthickness=0)
        yscroll = ttk.Scrollbar(viewport, orient=tk.VERTICAL, command=canvas.yview)
        body = tk.Frame(canvas, bg=BG)
        body.columnconfigure(0, weight=3, minsize=580)
        body.columnconfigure(1, weight=2, minsize=390)

        body_window = canvas.create_window((0, 0), window=body, anchor="nw")
        canvas.configure(yscrollcommand=yscroll.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        yscroll.grid(row=0, column=1, sticky="ns")

        def _sync_dashboard_scroll(_event: object | None = None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            try:
                canvas.itemconfigure(body_window, width=canvas.winfo_width())
            except Exception:
                pass

        body.bind("<Configure>", _sync_dashboard_scroll)
        canvas.bind("<Configure>", _sync_dashboard_scroll)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(int(-1 * (event.delta / 120)), "units") if self._current_key == "dashboard" else None)

        activity = self._dashboard_activity_card(body, data.get("activity", []))
        activity.grid(row=0, column=0, sticky="nsew", padx=(0, 14), pady=(0, 14))

        alerts = self._dashboard_attention_card(
            body,
            "Bloques de atenciÃ³n",
            [
                ("Pedidos que necesitan revisiÃ³n", data.get("validation_order_items", []), "calcular", "Warning"),
                ("Propuestas pendientes", data.get("proposal_items", []), "precios", "Warning"),
                ("Ãšltimos errores", data.get("error_items", []), "seguridad", "Error"),
            ],
        )
        alerts.grid(row=0, column=1, sticky="nsew", pady=(0, 14))

        orders = self._dashboard_compact_list_card(body, "Pedidos recientes", data.get("recent_order_items", []), "calcular")
        orders.grid(row=1, column=0, sticky="nsew", padx=(0, 14), pady=(0, 8))

        systems = self._dashboard_system_card(body, data)
        systems.grid(row=1, column=1, sticky="nsew", pady=(0, 8))

    def _dashboard_collect_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "kpis": {
                "open_orders": 0,
                "validation_orders": 0,
                "partial_receipts": 0,
                "pending_proposals": 0,
                "errors_today": 0,
            },
            "open_order_items": [],
            "validation_order_items": [],
            "partial_receipt_items": [],
            "recent_order_items": [],
            "proposal_items": [],
            "error_items": [],
            "activity": [],
            "systems": [],
            "errors": [],
        }
        if self._cloud_session is None:
            data["systems"] = [
                ("Supabase", "Sin sesiÃ³n activa", "Warning"),
                ("WooCommerce", "Pendiente de validar desde mÃ³dulo Woo", "Info"),
                ("Seguridad", "Sin logs hasta iniciar sesiÃ³n", "Info"),
            ]
            return data

        try:
            orders_rows = list_cloud_supplier_orders(self._cloud_session, limit=80)
            open_orders = []
            validation_orders = []
            partial_orders = []
            recent_orders = []
            for row in orders_rows:
                status = str(row.get("status") or "").strip().lower()
                name = cloud_order_display_name(row)
                provider = str(row.get("provider") or "-")
                updated = self._format_datetime_short(row.get("updated_at") or row.get("created_at"))
                detail = f"{provider} Â· {str(row.get('status') or '-')} Â· {updated}"
                item = (name, detail, "Warning" if "valid" in status or "parcial" in status else "Info")
                if status not in {"recibido completo", "received_full", "cancelled", "canceled", "cancelado"}:
                    open_orders.append(item)
                if "valid" in status:
                    validation_orders.append((name, detail, "Warning"))
                if "parcial" in status:
                    partial_orders.append((name, detail, "Warning"))
                recent_orders.append(item)
            data["open_order_items"] = open_orders[:6]
            data["validation_order_items"] = validation_orders[:6]
            data["partial_receipt_items"] = partial_orders[:6]
            data["recent_order_items"] = recent_orders[:8]
            data["kpis"]["open_orders"] = len(open_orders)
            data["kpis"]["validation_orders"] = len(validation_orders)
            data["kpis"]["partial_receipts"] = len(partial_orders)
        except Exception as exc:
            data["errors"].append(f"Pedidos no cargados: {exc}")

        try:
            proposals = list_real_price_proposals(self._cloud_session, status="pending", limit=80)
            proposal_items = []
            for row in proposals:
                name = str(row.get("name") or row.get("proposal_name") or row.get("item_woo_id") or row.get("id") or "Propuesta")
                created = self._format_datetime_short(row.get("created_at"))
                detail = f"{row.get('status') or 'pending'} Â· {created}"
                proposal_items.append((name, detail, "Warning"))
            data["proposal_items"] = proposal_items[:6]
            data["kpis"]["pending_proposals"] = len(proposal_items)
        except Exception as exc:
            data["errors"].append(f"Propuestas no cargadas: {exc}")

        try:
            logs = list_security_audit_logs(self._cloud_session, filters={}, limit=80)
            activity = []
            error_items = []
            errors_today = 0
            today = datetime.now(timezone.utc).date()
            for row in logs:
                module = row.get("visual_module") or row.get("module") or "-"
                action = row.get("visual_action") or row.get("action") or "-"
                user = row.get("user_email") or "-"
                time = self._format_datetime_short(row.get("created_at"))
                status_raw = str(row.get("status") or row.get("severity") or "INFO").upper()
                status = self._normalize_security_level(status_raw)
                activity.append((f"{time} Â· {user}", f"{module} Â· {action}", status))
                is_error = status_raw in {"ERROR", "CRITICAL", "BLOCKED"} or str(row.get("severity") or "").upper() in {"ERROR", "CRITICAL"}
                if is_error:
                    error_items.append((f"{module} Â· {action}", str(row.get("message") or row.get("error_detail") or row.get("operation_id") or "-")[:120], "Error"))
                    try:
                        dt = datetime.fromisoformat(str(row.get("created_at")).replace("Z", "+00:00"))
                        if dt.date() == today:
                            errors_today += 1
                    except Exception:
                        pass
            data["activity"] = activity[:10]
            data["error_items"] = error_items[:6]
            data["kpis"]["errors_today"] = errors_today
        except Exception as exc:
            data["errors"].append(f"Actividad reciente no cargada: {exc}")

        data["systems"] = [
            ("Supabase", "SesiÃ³n activa y lectura operativa", "OK"),
            ("WooCommerce", "Pendiente de sincronizaciÃ³n completa v48", "Info"),
            ("Seguridad", "Logs y rollback activos", "OK"),
        ]
        return data

    def _dashboard_show_attention(self, title: str, items: list[tuple[str, str, str]], target: str) -> None:
        win = tk.Toplevel(self)
        win.title(title)
        win.configure(bg=BG)
        win.transient(self)
        win.grab_set()
        center_window(win, 700, 520)
        win.columnconfigure(0, weight=1)
        win.rowconfigure(1, weight=1)
        tk.Label(win, text=title, bg=BG, fg=TEXT, font=("Segoe UI", 18, "bold")).grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
        card = self._card(win)
        card.grid(row=1, column=0, sticky="nsew", padx=18, pady=(0, 12))
        card.columnconfigure(0, weight=1)
        if not items:
            self._status_row(card, "Sin pendientes", "No hay elementos que requieran atenciÃ³n en este bloque.", "OK").pack(fill=tk.X, padx=16, pady=16)
        for index, (label, detail, status) in enumerate(items[:12]):
            self._status_row(card, label, detail, status).pack(fill=tk.X, padx=16, pady=(16 if index == 0 else 6, 0))
        footer = tk.Frame(win, bg=BG)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 18))
        self._button(footer, "Ir al mÃ³dulo", primary=True, command=lambda: (win.destroy(), self._show_view(target))).pack(side=tk.RIGHT)
        self._button(footer, "Cerrar", command=win.destroy).pack(side=tk.RIGHT, padx=(0, 8))

    def _dashboard_activity_card(self, parent: tk.Misc, activity: list[tuple[str, str, str]]) -> tk.Frame:
        card = self._card(parent)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text="Actividad reciente", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        tk.Label(card, text="Ãšltimas acciones auditadas, en formato reducido.", bg=CARD, fg=MUTED).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 8))
        if not activity:
            self._status_row(card, "Sin actividad visible", "TodavÃ­a no hay logs recientes o el rol actual no puede leerlos.", "Info").grid(row=2, column=0, sticky="ew", padx=16, pady=12)
            return card
        for index, (headline, detail, status) in enumerate(activity[:8], start=2):
            self._status_row(card, headline, detail, status).grid(row=index, column=0, sticky="ew", padx=16, pady=(4 if index > 2 else 8, 0))
        return card

    def _dashboard_attention_card(self, parent: tk.Misc, title: str, sections: list[tuple[str, list[tuple[str, str, str]], str, str]]) -> tk.Frame:
        card = self._card(parent)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 10))
        row = 1
        for section_title, items, target, status in sections:
            frame = tk.Frame(card, bg=CARD)
            frame.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 10))
            frame.columnconfigure(0, weight=1)
            tk.Label(frame, text=section_title, bg=CARD, fg=TEXT, font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
            self._button(frame, "Ver", command=lambda t=target: self._show_view(t)).grid(row=0, column=1, sticky="e")
            if not items:
                tk.Label(frame, text="Sin elementos pendientes.", bg=GREEN_SOFT, fg=GREEN, anchor=tk.W, padx=10, pady=7).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            else:
                for idx, (label, detail, item_status) in enumerate(items[:2], start=1):
                    self._status_row(frame, label, detail, item_status or status).grid(row=idx, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            row += 1
        return card

    def _dashboard_compact_list_card(self, parent: tk.Misc, title: str, items: list[tuple[str, str, str]], target: str) -> tk.Frame:
        card = self._card(parent)
        card.columnconfigure(0, weight=1)
        head = tk.Frame(card, bg=CARD)
        head.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        head.columnconfigure(0, weight=1)
        tk.Label(head, text=title, bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        self._button(head, "Ver mÃ³dulo", command=lambda: self._show_view(target)).grid(row=0, column=1, sticky="e")
        if not items:
            self._status_row(card, "Sin datos", "No hay elementos recientes para este bloque.", "Info").grid(row=1, column=0, sticky="ew", padx=16, pady=10)
            return card
        for index, (label, detail, status) in enumerate(items[:5], start=1):
            self._status_row(card, label, detail, status).grid(row=index, column=0, sticky="ew", padx=16, pady=(5, 0))
        return card

    def _dashboard_system_card(self, parent: tk.Misc, data: dict[str, Any]) -> tk.Frame:
        card = self._card(parent)
        card.columnconfigure(0, weight=1)
        tk.Label(card, text="Estado de sistemas", bg=CARD, fg=TEXT, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 8))
        systems = data.get("systems") or []
        for index, (label, detail, status) in enumerate(systems, start=1):
            self._status_row(card, label, detail, status).grid(row=index, column=0, sticky="ew", padx=16, pady=(6, 0))
        self._status_row(card, "PrÃ³ximo frente", "WooCommerce completo: lectura, autoclasificaciÃ³n y preview de incidencias.", "Info").grid(row=len(systems) + 1, column=0, sticky="ew", padx=16, pady=(12, 16))
        return card
