from __future__ import annotations

from tkinter import messagebox, simpledialog

from futonhub.core.config import load_settings
from futonhub.cloud.audit import (
    CloudAuditError,
    create_test_audit_event,
    create_test_snapshot,
    format_audit_rows,
    format_snapshot_rows,
    list_audit_logs,
    list_operation_snapshots,
    write_audit_event,
    write_snapshot,
)
from futonhub.cloud.operational import (
    clean_worker_feedback_constant,
    clean_worker_simulated_inventory,
    clean_worker_simulated_order,
    clean_worker_simulated_price_proposal,
    collect_operational_cloud_status,
    execute_rollback_from_snapshot,
    format_rollback_candidates,
    format_rollback_preview,
    list_rollback_candidates,
    preview_rollback_from_snapshot,
    review_worker_simulated_price_proposal,
    test_business_constant_change,
    test_worker_feedback_constant_change,
    test_worker_simulated_inventory_change,
    test_worker_simulated_order,
    test_worker_simulated_price_proposal,
)


class CloudAdminToolsMixin:
    def _cloud_test_log(self) -> None:
        if not self._require_admin_session():
            return
        try:
            settings = load_settings()
            event = create_test_audit_event(self._cloud_session, settings)
            row = write_audit_event(self._cloud_session, event, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Caja negra cloud", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Caja negra cloud", f"No se pudo crear el log de prueba.\n\n{exc}")
            return
        messagebox.showinfo(
            "Caja negra cloud",
            "Audit log de prueba creado correctamente.\n\n"
            f"Operacion: {row.get('operation_id', event.operation_id)}",
        )

    def _cloud_test_snapshot(self) -> None:
        if not self._require_admin_session():
            return
        try:
            settings = load_settings()
            snapshot = create_test_snapshot(self._cloud_session, settings)
            write_snapshot(self._cloud_session, snapshot)
            event = create_test_audit_event(self._cloud_session, settings)
            event = event.__class__(
                operation_id=snapshot.operation_id,
                module="blackbox",
                action="cloud_test_snapshot",
                status="TEST",
                severity="INFO",
                entity_type=snapshot.entity_type,
                entity_id=snapshot.entity_id,
                before_data=snapshot.before_data,
                after_data={"snapshot_created": True},
                message="Prueba manual de snapshot logico creada correctamente desde el HUB.",
            )
            write_audit_event(self._cloud_session, event, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Caja negra cloud", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Caja negra cloud", f"No se pudo crear el snapshot de prueba.\n\n{exc}")
            return
        messagebox.showinfo(
            "Caja negra cloud",
            "Snapshot de prueba creado correctamente.\n\n"
            f"Operacion: {snapshot.operation_id}\nTambien se registro un audit_log asociado.",
        )

    def _show_cloud_logs(self) -> None:
        if not self._require_admin_session():
            return
        try:
            rows = list_audit_logs(self._cloud_session, limit=50)
        except CloudAuditError as exc:
            messagebox.showerror("Logs cloud", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Logs cloud", f"No se pudieron leer los logs.\n\n{exc}")
            return
        self._show_text_window("Logs y auditoria cloud", format_audit_rows(rows))

    def _show_cloud_snapshots(self) -> None:
        if not self._require_admin_session():
            return
        try:
            rows = list_operation_snapshots(self._cloud_session, limit=50)
        except CloudAuditError as exc:
            messagebox.showerror("Snapshots cloud", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Snapshots cloud", f"No se pudieron leer los snapshots.\n\n{exc}")
            return
        self._show_text_window("Snapshots / puntos de restauracion cloud", format_snapshot_rows(rows))

    def _cloud_rollback_snapshot(self) -> None:
        """Admin: preview y rollback interno desde un operation_snapshot.

        Revertir usa before_data del snapshot y no toca WooCommerce.
        """
        if not self._require_admin_session():
            return
        try:
            candidates = list_rollback_candidates(self._cloud_session, limit=30)
            candidates_text = format_rollback_candidates(candidates)
        except Exception as exc:
            candidates_text = f"No se pudieron cargar candidatos automaticamente.\n\n{exc}"

        operation_id = simpledialog.askstring(
            "Rollback snapshot",
            "Pega el operation_id del snapshot a revertir.\n\n"
            "Candidatos recientes:\n"
            + candidates_text[:2500],
            parent=self,
        )
        if not operation_id:
            return
        operation_id = operation_id.strip()
        try:
            preview = preview_rollback_from_snapshot(self._cloud_session, operation_id)
            preview_text = format_rollback_preview(preview)
        except Exception as exc:
            messagebox.showerror("Rollback snapshot", f"No se pudo generar preview.\n\n{exc}", parent=self)
            return
        if not messagebox.askyesno(
            "Confirmar rollback interno",
            preview_text + "\n\nQuieres continuar con el rollback",
            parent=self,
        ):
            return
        typed = simpledialog.askstring(
            "Confirmacion requerida",
            "Escribe REVERTIR para ejecutar el rollback interno.\n\nWooCommerce no se toca.",
            parent=self,
        )
        if (typed or "").strip().upper() != "REVERTIR":
            messagebox.showinfo("Rollback snapshot", "Cancelado. No se aplico rollback.", parent=self)
            return
        try:
            result = execute_rollback_from_snapshot(self._cloud_session, operation_id, load_settings())
        except Exception as exc:
            messagebox.showerror("Rollback snapshot", f"No se pudo ejecutar rollback.\n\n{exc}", parent=self)
            return
        messagebox.showinfo(
            "Rollback completado",
            "Rollback interno completado correctamente.\n\n"
            f"Operacion rollback: {result.get('operation_id')}\n"
            f"Snapshot origen: {result.get('source_operation_id')}\n"
            f"Tabla: {result.get('table')} - {result.get('key')}={result.get('key_value')}\n\n"
            "Supabase fue revertido. WooCommerce no fue tocado.\n"
            "Caja negra: audit_log + operation_snapshot generados.",
            parent=self,
        )

    def _cloud_test_constant(self) -> None:
        if not self._ensure_cloud_session():
            return
        try:
            settings = load_settings()
            result = test_business_constant_change(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Constantes cloud", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Constantes cloud", f"No se pudo probar la constante cloud.\n\n{exc}")
            return
        messagebox.showinfo(
            "Constantes cloud",
            "Prueba operativa creada/actualizada correctamente.\n\n"
            f"Operacion: {result.get('operation_id')}\n"
            "Tabla: business_constants\n"
            "Clave: TEST_FACTOR_SEGURIDAD\n\n"
            "Se registro audit_log y, si habia valor previo, snapshot.",
        )

    def _cloud_worker_feedback_test(self) -> None:
        if not self._ensure_cloud_session():
            return
        try:
            settings = load_settings()
            result = test_worker_feedback_constant_change(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Prueba worker", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Prueba worker", f"No se pudo ejecutar la prueba worker.\n\n{exc}")
            return
        messagebox.showinfo(
            "Prueba worker",
            "Prueba worker creada/actualizada correctamente.\n\n"
            f"Operacion: {result.get('operation_id')}\n"
            "Tabla: business_constants\n"
            "Clave: TEST_WORKER_FEEDBACK\n\n"
            "Admin podra ver el cambio en Logs cloud y Snapshots cloud.",
        )

    def _cloud_worker_order_test(self) -> None:
        if not self._ensure_cloud_session():
            return
        settings = load_settings()
        try:
            result = test_worker_simulated_order(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Pedido simulado", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Pedido simulado", f"No se pudo crear el pedido simulado.\n\n{exc}")
            return
        messagebox.showinfo(
            "Pedido simulado",
            "Pedido simulado creado/actualizado correctamente.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Accion: {result['action']}\n"
            f"Order file: {result['order_file']}\n\n"
            "Admin podra ver el cambio en Logs cloud y Snapshots cloud.",
        )

    def _cloud_clean_worker_order_test(self) -> None:
        if not self._require_admin_session():
            return
        if not messagebox.askyesno(
            "Limpiar pedido simulado",
            "Esto limpiara/cancelara TEST_WORKER_ORDER y dejara log/snapshot.\n\nContinuar",
        ):
            return
        settings = load_settings()
        try:
            result = clean_worker_simulated_order(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Limpiar pedido simulado", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Limpiar pedido simulado", f"No se pudo limpiar el pedido simulado.\n\n{exc}")
            return
        messagebox.showinfo(
            "Limpiar pedido simulado",
            "Limpieza/cancelacion completada.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Borrado: {result['deleted']}\n"
            f"Marcado cancelado: {result['marked_cancelled']}",
        )

    def _cloud_worker_inventory_test(self) -> None:
        if not self._ensure_cloud_session():
            return
        settings = load_settings()
        try:
            result = test_worker_simulated_inventory_change(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Inventario simulado", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Inventario simulado", f"No se pudo crear el inventario simulado.\n\n{exc}")
            return
        messagebox.showinfo(
            "Inventario simulado",
            "Inventario simulado creado/actualizado correctamente.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Accion: {result['action']}\n"
            f"Item ID: {result['item_id']}\n"
            f"Stock tienda: {result['store_stock']}\n"
            f"Stock almacen: {result['warehouse_stock']}\n\n"
            "Admin podra ver el cambio en Logs cloud y Snapshots cloud.",
        )

    def _cloud_clean_worker_inventory_test(self) -> None:
        if not self._require_admin_session():
            return
        if not messagebox.askyesno(
            "Limpiar inventario simulado",
            "Esto limpiara/cancelara TEST_WORKER_INVENTORY_ITEM y dejara log/snapshot.\n\nContinuar",
        ):
            return
        settings = load_settings()
        try:
            result = clean_worker_simulated_inventory(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Limpiar inventario simulado", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Limpiar inventario simulado", f"No se pudo limpiar el inventario simulado.\n\n{exc}")
            return
        messagebox.showinfo(
            "Limpiar inventario simulado",
            "Limpieza/cancelacion completada.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Borrado: {result['deleted']}\n"
            f"Marcado cancelado: {result['marked_inactive']}",
        )

    def _cloud_worker_price_test(self) -> None:
        if not self._ensure_cloud_session():
            return
        settings = load_settings()
        try:
            result = test_worker_simulated_price_proposal(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Propuesta precio simulada", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Propuesta precio simulada", f"No se pudo crear la propuesta simulada.\n\n{exc}")
            return
        messagebox.showinfo(
            "Propuesta precio simulada",
            "Propuesta de precio simulada creada/actualizada correctamente.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Accion: {result['action']}\n"
            f"Precio anterior: {result['old_price']}\n"
            f"Precio propuesto: {result['new_price']}\n\n"
            "Admin podra ver el cambio en Logs cloud y Snapshots cloud.",
        )

    def _cloud_review_worker_price_test(self, decision: str) -> None:
        if not self._require_admin_session():
            return
        label = "aprobar" if decision == "approved" else "rechazar"
        if not messagebox.askyesno(
            "Revisar propuesta precio test",
            f"Esto va a {label} TEST_WORKER_PRICE_PROPOSAL.\n\n"
            "No se publicara nada en WooCommerce. Se generara snapshot y log.\n\nContinuar",
        ):
            return
        settings = load_settings()
        try:
            result = review_worker_simulated_price_proposal(self._cloud_session, decision, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Revisar propuesta precio test", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Revisar propuesta precio test", f"No se pudo revisar la propuesta simulada.\n\n{exc}")
            return
        messagebox.showinfo(
            "Revisar propuesta precio test",
            "Propuesta simulada revisada correctamente.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Decision: {result['decision']}\n"
            f"Item Woo test: {result['item_woo_id']}\n\n"
            "No se publico nada en WooCommerce.",
        )

    def _cloud_clean_worker_price_test(self) -> None:
        if not self._require_admin_session():
            return
        if not messagebox.askyesno(
            "Limpiar propuesta precio simulada",
            "Esto limpiara/cancelara TEST_WORKER_PRICE_PROPOSAL y dejara log/snapshot.\n\nContinuar",
        ):
            return
        settings = load_settings()
        try:
            result = clean_worker_simulated_price_proposal(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Limpiar propuesta precio simulada", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Limpiar propuesta precio simulada", f"No se pudo limpiar la propuesta simulada.\n\n{exc}")
            return
        messagebox.showinfo(
            "Limpiar propuesta precio simulada",
            "Limpieza/cancelacion completada.\n\n"
            f"Operacion: {result['operation_id']}\n"
            f"Borrado: {result['deleted']}\n"
            f"Marcado cancelado: {result['marked_cancelled']}",
        )

    def _cloud_clean_worker_feedback_test(self) -> None:
        if not self._require_admin_session():
            return
        if not messagebox.askyesno(
            "Limpiar prueba worker",
            "Se borrara TEST_WORKER_FEEDBACK de business_constants y se dejara log/snapshot.\n\nContinuar",
        ):
            return
        try:
            settings = load_settings()
            result = clean_worker_feedback_constant(self._cloud_session, settings)
        except CloudAuditError as exc:
            messagebox.showerror("Limpiar prueba worker", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Limpiar prueba worker", f"No se pudo limpiar la prueba.\n\n{exc}")
            return
        messagebox.showinfo(
            "Limpiar prueba worker",
            "Limpieza completada.\n\n"
            f"Operacion: {result.get('operation_id')}\n"
            f"Borrado: {result.get('deleted')}",
        )

    def _show_cloud_operational_status(self) -> None:
        if not self._require_admin_session():
            return
        try:
            body = collect_operational_cloud_status(self._cloud_session)
        except Exception as exc:
            messagebox.showerror("Estado operativo cloud", f"No se pudo leer el estado operativo.\n\n{exc}")
            return
        self._show_text_window("Estado operativo Supabase", body)
