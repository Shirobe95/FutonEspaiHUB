from __future__ import annotations

import argparse
import runpy
import sys
from pathlib import Path

from gestorwoo.backup import run_backup_app
from gestorwoo.cloud.diagnostics import print_cloud_diagnostics, collect_cloud_diagnostics, print_cloud_login_diagnostics
from gestorwoo.cloud.blackbox_cli import run_cloud_logs, run_cloud_snapshots, run_cloud_test_log, run_cloud_test_snapshot
from gestorwoo.cloud.operational import run_cloud_operational_status, run_cloud_test_constant, run_cloud_worker_feedback_test, run_cloud_clean_worker_feedback_test, run_cloud_worker_order_test, run_cloud_clean_worker_order_test, run_cloud_worker_inventory_test, run_cloud_clean_worker_inventory_test, run_cloud_worker_price_test, run_cloud_clean_worker_price_test, run_cloud_review_worker_price_test, run_migrate_sqlite_to_supabase_dry_run, run_cloud_search_products, run_cloud_real_price_proposal, run_cloud_review_real_price_proposal, run_cloud_import_woocommerce_product, run_cloud_woocommerce_publish_preview, run_cloud_woocommerce_publish_execute, run_cloud_list_real_price_proposals, run_cloud_price_heart_attack_tests, run_cloud_search_inventory, run_cloud_inventory_update_internal, run_cloud_rollback_candidates, run_cloud_rollback_snapshot, run_cloud_supplier_prices_migration_preview, run_cloud_supplier_prices_migration_execute, run_cloud_supplier_prices_diagnostic, run_cloud_import_inventory_items_csv_preview, run_cloud_import_inventory_items_csv_execute, run_cloud_upsert_inventory_items_csv_preview, run_cloud_upsert_inventory_items_csv_execute
from gestorwoo.cloud.migration import run_migration_preview, run_migration_execute
from gestorwoo.config import load_settings
from gestorwoo.diagnostics import print_diagnostics
from gestorwoo.guard import active_locks, clear_stale_locks, stale_locks
from futonhub.app.hub import run_hub
from futonhub.ui.erp.prototype import run_erp_prototype
from gestorwoo.inventory import run_inventory_app
from gestorwoo.security import run_logs_app, log_event
from gestorwoo.storage import ProductStore
from gestorwoo.sync import sync_products
from gestorwoo.ui import run_app
from gestorwoo.woocommerce import WooCommerceError


def main() -> int:
    parser = argparse.ArgumentParser(prog="gestorwoo")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("sync-products", help="Carga productos desde WooCommerce.")
    subparsers.add_parser("ui", help="Abre la interfaz de articulos.")
    subparsers.add_parser("woocommerce-inventory", help="Abre la gestion visual del catalogo WooCommerce.")
    subparsers.add_parser("price-changes", help="Abre el modulo de cambio de precios seguro.")
    subparsers.add_parser("hub", help="Abre el panel central Futon Espai.")
    subparsers.add_parser("erp-prototype", help="Abre el prototipo aislado de UI ERP.")
    subparsers.add_parser("inventory", help="Abre la gestion de inventario.")
    subparsers.add_parser("backup", help="Abre backups y restauracion.")
    subparsers.add_parser("logs", help="Abre el visor de logs de seguridad.")
    subparsers.add_parser("diagnostic", help="Muestra rutas, base activa y estado del sistema.")
    subparsers.add_parser("cloud-diagnostic", help="Comprueba configuración y tablas Supabase sin login. RLS puede ocultar filas.")
    subparsers.add_parser("cloud-login-diagnostic", help="Comprueba Supabase con login real y lectura RLS autenticada.")
    subparsers.add_parser("cloud-status", help="Resumen corto del estado online/Supabase.")
    subparsers.add_parser("cloud-test-log", help="Crea un audit_log cloud de prueba con login real.")
    subparsers.add_parser("cloud-test-snapshot", help="Crea un snapshot cloud de prueba con login real.")
    subparsers.add_parser("cloud-operational-status", help="Comprueba tablas operativas Supabase v7 con login real.")
    subparsers.add_parser("cloud-test-constant", help="Prueba segura de escritura en business_constants con snapshot/log.")
    subparsers.add_parser("cloud-worker-feedback-test", help="Prueba real worker: modifica TEST_WORKER_FEEDBACK con log/snapshot.")
    subparsers.add_parser("cloud-clean-worker-feedback-test", help="Admin: borra TEST_WORKER_FEEDBACK y deja log/snapshot.")
    subparsers.add_parser("cloud-worker-order-test", help="Prueba worker: crea/actualiza pedido simulado TEST_WORKER_ORDER con log/snapshot.")
    subparsers.add_parser("cloud-clean-worker-order-test", help="Admin: limpia/cancela TEST_WORKER_ORDER y deja log/snapshot.")
    subparsers.add_parser("cloud-worker-inventory-test", help="Prueba worker: crea/actualiza inventario simulado TEST_WORKER_INVENTORY_ITEM con log/snapshot.")
    subparsers.add_parser("cloud-clean-worker-inventory-test", help="Admin: limpia inventario simulado TEST_WORKER_INVENTORY_ITEM y deja log/snapshot.")
    subparsers.add_parser("cloud-worker-price-test", help="Prueba worker: crea/actualiza propuesta de precio simulada TEST_WORKER_PRICE_PROPOSAL con log/snapshot.")
    subparsers.add_parser("cloud-clean-worker-price-test", help="Admin: limpia propuesta de precio simulada TEST_WORKER_PRICE_PROPOSAL y deja log/snapshot.")
    review_price_parser = subparsers.add_parser("cloud-review-worker-price-test", help="Admin: aprueba/rechaza propuesta de precio simulada. No publica en WooCommerce.")
    review_price_parser.add_argument("decision", choices=["approved", "rejected"], help="Decisión de revisión admin.")
    search_products_parser = subparsers.add_parser("cloud-search-products", help="Busca productos/variaciones reales migrados en Supabase. No consulta WooCommerce.")
    search_products_parser.add_argument("--query", required=True, help="Texto a buscar en nombre de producto.")
    search_products_parser.add_argument("--limit", type=int, default=15)
    import_woo_parser = subparsers.add_parser("cloud-import-woocommerce-product", help="Admin: importa un producto WooCommerce concreto y sus variaciones a Supabase. No publica WooCommerce.")
    import_group = import_woo_parser.add_mutually_exclusive_group(required=True)
    import_group.add_argument("--woo-id", type=int, help="ID del producto padre WooCommerce a importar.")
    import_group.add_argument("--query", help="Texto para buscar el producto en WooCommerce, por ejemplo: Test Product + Var.")
    real_price_parser = subparsers.add_parser("cloud-real-price-proposal", help="Crea/actualiza propuesta real interna sobre producto Supabase. No publica WooCommerce.")
    real_price_parser.add_argument("--item-kind", choices=["product", "variation"], required=True)
    real_price_parser.add_argument("--woo-id", type=int, required=True)
    real_price_parser.add_argument("--new-price", type=float, required=True)
    real_price_parser.add_argument("--notes", default="")
    real_price_parser.add_argument("--ack-price-warning", action="store_true", help="Confirmación explícita para avisos amarillos por bajada grande. No evita bloqueos rojos.")
    heart_parser = subparsers.add_parser("cloud-price-heart-attack-tests", help="Prueba 3 casos críticos de precio sin escribir propuestas ni tocar WooCommerce.")
    heart_parser.add_argument("--item-kind", choices=["product", "variation"], required=True)
    heart_parser.add_argument("--woo-id", type=int, required=True)
    inv_search_parser = subparsers.add_parser("cloud-search-inventory", help="Busca inventario interno Supabase. No toca WooCommerce.")
    inv_search_parser.add_argument("--query", required=True)
    inv_search_parser.add_argument("--limit", type=int, default=25)
    inv_update_parser = subparsers.add_parser("cloud-inventory-update-internal", help="Preview/aplica cambio interno de inventario en Supabase. No toca WooCommerce.")
    inv_update_parser.add_argument("--item-id", type=int, required=True)
    inv_update_parser.add_argument("--store-stock", default="")
    inv_update_parser.add_argument("--warehouse-stock", default="")
    inv_update_parser.add_argument("--notes", default="")
    inv_update_parser.add_argument("--execute", action="store_true", help="Aplica el cambio tras confirmación escrita APLICAR.")

    rollback_list_parser = subparsers.add_parser("cloud-rollback-candidates", help="Admin: lista snapshots internos candidatos a rollback. No toca WooCommerce.")
    rollback_list_parser.add_argument("--limit", type=int, default=30)
    rollback_parser = subparsers.add_parser("cloud-rollback-snapshot", help="Admin: preview/ejecución de rollback desde operation_snapshot. No toca WooCommerce.")
    rollback_parser.add_argument("--operation-id", required=True, help="operation_id del snapshot origen a revertir.")
    rollback_parser.add_argument("--execute", action="store_true", help="Ejecuta rollback tras preview y confirmación escrita.")
    rollback_parser.add_argument("--confirm", default="", help="Debe ser REVERTIR para ejecutar.")
    list_real_parser = subparsers.add_parser("cloud-list-real-price-proposals", help="Lista propuestas reales internas. No toca WooCommerce.")
    list_real_parser.add_argument("--status", default="pending", help="pending, approved, publishing, rejected, published, error, cancelled o all.")
    list_real_parser.add_argument("--limit", type=int, default=50)
    real_review_parser = subparsers.add_parser("cloud-review-real-price-proposal", help="Aprueba/rechaza propuesta real interna. Admin y worker. No publica WooCommerce.")
    real_review_parser.add_argument("decision", choices=["approved", "rejected"])
    real_review_parser.add_argument("--proposal-id", default="", help="Opcional. Si se omite, revisa la última propuesta pendiente no TEST.")
    publish_preview_parser = subparsers.add_parser("cloud-woocommerce-publish-preview", help="Admin: preview de publicación WooCommerce para propuestas aprobadas. NO publica cambios.")
    publish_preview_parser.add_argument("--proposal-id", default="", help="Opcional: propuesta aprobada concreta.")
    publish_preview_parser.add_argument("--limit", type=int, default=20, help="Máximo de propuestas aprobadas a evaluar.")
    publish_execute_parser = subparsers.add_parser("cloud-woocommerce-publish-execute", help="Admin: PUBLICA una propuesta aprobada en WooCommerce con confirmación escrita.")
    publish_execute_parser.add_argument("--proposal-id", required=True, help="ID exacto de la propuesta aprobada a publicar. Solo una por operación.")
    publish_execute_parser.add_argument("--confirm", default="", help="Debe ser PUBLICAR para ejecutar el cambio real en WooCommerce.")
    publish_execute_parser.add_argument("--ack-woo-warning", action="store_true", help="Confirma warnings amarillos del preview. No evita errores rojos.")
    subparsers.add_parser("migrate-sqlite-to-supabase-dry-run", help="Revisa la base SQLite local para futura migracion a Supabase sin subir datos.")
    subparsers.add_parser("migrate-sqlite-to-supabase-preview", help="Preview con login: compara conteos SQLite local vs Supabase sin subir datos.")
    migrate_exec_parser = subparsers.add_parser("migrate-sqlite-to-supabase-execute", help="Ejecuta migracion SQLite -> Supabase. Requiere --confirm MIGRAR.")
    migrate_exec_parser.add_argument("--confirm", default="", help="Debe ser MIGRAR para ejecutar.")
    migrate_exec_parser.add_argument("--tables", default="", help="Opcional: lista separada por comas de tablas a migrar.")
    subparsers.add_parser("cloud-supplier-prices-diagnostic", help="Diagnóstico de precios proveedor local vs Supabase inventory_items.")
    subparsers.add_parser("cloud-migrate-supplier-prices-preview", help="Preview: migra supplier_prices SQLite local -> Supabase sin escribir.")
    supplier_prices_exec_parser = subparsers.add_parser("cloud-migrate-supplier-prices-execute", help="Ejecuta migración supplier_prices SQLite local -> Supabase.")
    supplier_prices_exec_parser.add_argument("--confirm", default="", help="Debe ser MIGRAR_PRECIOS_PROVEEDOR para ejecutar.")
    import_items_preview_parser = subparsers.add_parser("cloud-import-inventory-items-csv-preview", help="Preview: importa items faltantes desde CSV generado de Excel.")
    import_items_preview_parser.add_argument("--csv", required=True, help="Ruta al CSV de items a importar.")
    import_items_execute_parser = subparsers.add_parser("cloud-import-inventory-items-csv-execute", help="Ejecuta importación de items faltantes desde CSV.")
    import_items_execute_parser.add_argument("--csv", required=True, help="Ruta al CSV de items a importar.")
    import_items_execute_parser.add_argument("--confirm", default="", help="Debe ser IMPORTAR_ITEMS para ejecutar.")
    upsert_items_preview_parser = subparsers.add_parser("cloud-upsert-inventory-items-csv-preview", help="Preview: inserta/actualiza items desde CSV.")
    upsert_items_preview_parser.add_argument("--csv", required=True, help="Ruta al CSV de items a importar/actualizar.")
    upsert_items_execute_parser = subparsers.add_parser("cloud-upsert-inventory-items-csv-execute", help="Ejecuta inserción/actualización de items desde CSV.")
    upsert_items_execute_parser.add_argument("--csv", required=True, help="Ruta al CSV de items a importar/actualizar.")
    upsert_items_execute_parser.add_argument("--confirm", default="", help="Debe ser IMPORTAR_ITEMS para ejecutar.")
    logs_cloud_parser = subparsers.add_parser("cloud-logs", help="Muestra audit_logs cloud visibles para el usuario autenticado.")
    logs_cloud_parser.add_argument("--limit", type=int, default=25)
    snapshots_cloud_parser = subparsers.add_parser("cloud-snapshots", help="Muestra snapshots cloud visibles para el usuario autenticado.")
    snapshots_cloud_parser.add_argument("--limit", type=int, default=25)
    subparsers.add_parser("safety-status", help="Muestra bloqueos de seguridad activos/caducados.")
    subparsers.add_parser("clear-stale-locks", help="Limpia bloqueos caducados de operaciones interrumpidas.")
    subparsers.add_parser("cost", help="Abre la calculadora de coste individual.")
    cost_pedido_parser = subparsers.add_parser("cost-pedido", help="Abre la calculadora de coste de pedido.")
    cost_pedido_parser.add_argument("--proveedor", choices=["ekomat", "pascal", "hemei", "heimei", "cipta"], default="ekomat")
    subparsers.add_parser("constantes", help="Abre el gestor de constantes del negocio.")

    list_parser = subparsers.add_parser("list-products", help="Muestra productos locales.")
    list_parser.add_argument("--limit", type=int, default=25)

    args = parser.parse_args()

    if args.command == "diagnostic":
        return print_diagnostics()

    if args.command == "cloud-diagnostic":
        return print_cloud_diagnostics()

    if args.command == "cloud-login-diagnostic":
        return print_cloud_login_diagnostics()

    if args.command == "cloud-status":
        result = collect_cloud_diagnostics(try_connect=False)
        print(result.text)
        return 0 if result.ok else 1

    if args.command == "cloud-test-log":
        return run_cloud_test_log()

    if args.command == "cloud-test-snapshot":
        return run_cloud_test_snapshot()

    if args.command == "cloud-operational-status":
        return run_cloud_operational_status()

    if args.command == "cloud-test-constant":
        return run_cloud_test_constant()

    if args.command == "cloud-worker-feedback-test":
        return run_cloud_worker_feedback_test()

    if args.command == "cloud-clean-worker-feedback-test":
        return run_cloud_clean_worker_feedback_test()

    if args.command == "cloud-worker-order-test":
        return run_cloud_worker_order_test()

    if args.command == "cloud-clean-worker-order-test":
        return run_cloud_clean_worker_order_test()

    if args.command == "cloud-worker-inventory-test":
        return run_cloud_worker_inventory_test()

    if args.command == "cloud-clean-worker-inventory-test":
        return run_cloud_clean_worker_inventory_test()

    if args.command == "cloud-worker-price-test":
        return run_cloud_worker_price_test()

    if args.command == "cloud-clean-worker-price-test":
        return run_cloud_clean_worker_price_test()

    if args.command == "cloud-review-worker-price-test":
        return run_cloud_review_worker_price_test(args.decision)

    if args.command == "cloud-search-products":
        return run_cloud_search_products(args.query, args.limit)

    if args.command == "cloud-import-woocommerce-product":
        return run_cloud_import_woocommerce_product(woo_id=args.woo_id, query=args.query)

    if args.command == "cloud-real-price-proposal":
        return run_cloud_real_price_proposal(args.item_kind, args.woo_id, args.new_price, args.notes, args.ack_price_warning)

    if args.command == "cloud-price-heart-attack-tests":
        return run_cloud_price_heart_attack_tests(args.item_kind, args.woo_id)

    if args.command == "cloud-search-inventory":
        return run_cloud_search_inventory(args.query, args.limit)

    if args.command == "cloud-inventory-update-internal":
        return run_cloud_inventory_update_internal(
            item_id=args.item_id,
            store_stock=args.store_stock,
            warehouse_stock=args.warehouse_stock,
            notes=args.notes,
            execute=args.execute,
        )

    if args.command == "cloud-list-real-price-proposals":
        return run_cloud_list_real_price_proposals(args.status, args.limit)

    if args.command == "cloud-rollback-candidates":
        return run_cloud_rollback_candidates(args.limit)

    if args.command == "cloud-rollback-snapshot":
        return run_cloud_rollback_snapshot(args.operation_id, args.execute, args.confirm)

    if args.command == "cloud-review-real-price-proposal":
        return run_cloud_review_real_price_proposal(args.decision, args.proposal_id)

    if args.command == "cloud-woocommerce-publish-preview":
        return run_cloud_woocommerce_publish_preview(limit=args.limit, proposal_id=args.proposal_id)

    if args.command == "cloud-woocommerce-publish-execute":
        return run_cloud_woocommerce_publish_execute(
            proposal_id=args.proposal_id,
            confirm=args.confirm,
            ack_woo_warning=args.ack_woo_warning,
        )

    if args.command == "migrate-sqlite-to-supabase-dry-run":
        return run_migrate_sqlite_to_supabase_dry_run()

    if args.command == "migrate-sqlite-to-supabase-preview":
        return run_migration_preview()

    if args.command == "migrate-sqlite-to-supabase-execute":
        return run_migration_execute(confirm=args.confirm, tables_csv=args.tables)

    if args.command == "cloud-supplier-prices-diagnostic":
        return run_cloud_supplier_prices_diagnostic, run_cloud_import_inventory_items_csv_preview, run_cloud_import_inventory_items_csv_execute, run_cloud_upsert_inventory_items_csv_preview, run_cloud_upsert_inventory_items_csv_execute()

    if args.command == "cloud-migrate-supplier-prices-preview":
        return run_cloud_supplier_prices_migration_preview()

    if args.command == "cloud-migrate-supplier-prices-execute":
        return run_cloud_supplier_prices_migration_execute(confirm=args.confirm)

    if args.command == "cloud-import-inventory-items-csv-preview":
        return run_cloud_import_inventory_items_csv_preview(args.csv)

    if args.command == "cloud-import-inventory-items-csv-execute":
        return run_cloud_import_inventory_items_csv_execute(args.csv, confirm=args.confirm)

    if args.command == "cloud-logs":
        return run_cloud_logs(limit=args.limit)

    if args.command == "cloud-snapshots":
        return run_cloud_snapshots(limit=args.limit)

    if args.command == "safety-status":
        settings = load_settings()
        expired = clear_stale_locks(settings.db_path)
        print(f"Modo: {settings.app_mode}")
        print(f"Maquina: {settings.machine_name}")
        print(f"Base: {settings.db_path}")
        print(f"Bloqueos caducados limpiados: {expired}")
        locks = active_locks(settings.db_path)
        if not locks:
            print("Bloqueos activos: ninguno")
        else:
            print("Bloqueos activos:")
            for lock in locks:
                print(f"- {lock.operation_key} · {lock.locked_by} · hasta {lock.expires_at} · {lock.details}")
        stale = stale_locks(settings.db_path)
        if stale:
            print("Bloqueos caducados aun visibles:")
            for lock in stale:
                print(f"- {lock.operation_key} · {lock.locked_by} · expiro {lock.expires_at}")
        return 0 if not locks else 1

    if args.command == "clear-stale-locks":
        settings = load_settings()
        cleaned = clear_stale_locks(settings.db_path)
        print(f"Bloqueos caducados limpiados: {cleaned}")
        return 0

    if args.command in {"cost", "cost-pedido", "constantes"}:
        return _run_calculo_coste_command(args.command, getattr(args, "proveedor", None))

    settings = load_settings()

    try:
        if args.command == "ui":
            run_app(settings, mode="inventory")
            return 0

        if args.command == "woocommerce-inventory":
            run_app(settings, mode="inventory")
            return 0

        if args.command == "price-changes":
            run_app(settings, mode="prices")
            return 0

        if args.command == "hub":
            run_hub()
            return 0

        if args.command == "erp-prototype":
            run_erp_prototype()
            return 0

        if args.command == "inventory":
            run_inventory_app(settings)
            return 0

        if args.command == "backup":
            run_backup_app(settings)
            return 0

        if args.command == "logs":
            run_logs_app(settings)
            return 0

        if args.command == "sync-products":
            result = sync_products(settings)
            print(f"Categorias importadas/actualizadas: {result.categories_imported}")
            print(f"Productos importados/actualizados: {result.imported}")
            print(
                "Variaciones importadas/actualizadas: "
                f"{result.variations_imported}"
            )
            print(f"Productos locales totales: {result.total_local}")
            print(f"Variaciones locales totales: {result.total_variations}")
            print(f"Categorias locales totales: {result.total_categories}")
            return 0

        if args.command == "list-products":
            store = ProductStore(settings.db_path)
            store.init_schema()
            print(f"Categorias locales: {store.count_categories()}")
            print(f"Productos locales: {store.count_products()}")
            print(f"Variaciones locales: {store.count_variations()}")
            print("Tipos:")
            for row in store.product_type_counts():
                print(f"  {row['type'] or '(sin tipo)'}: {row['total']}")
            print()
            for row in store.list_products(limit=args.limit):
                print(
                    f"{row['woo_id']} | {row['type']} | {row['sku'] or '-'} | "
                    f"{row['price'] or '-'} | {row['name']}"
                )
            return 0
    except WooCommerceError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    parser.print_help()
    return 1


def _project_root_for_exe() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path(__file__).resolve().parents[3].parent


def _run_calculo_coste_command(command: str, proveedor: str | None = None) -> int:
    if getattr(sys, "frozen", False):
        calculo_root = Path(sys.argv[0]).resolve().parent.parent / "CalculoCoste"
    else:
        # cli.py vive en GestorWoo/src/gestorwoo/. El proyecto raíz es parents[3].
        calculo_root = Path(__file__).resolve().parents[3] / "CalculoCoste"

    if command == "cost-pedido":
        script = calculo_root / "coste_pedido.py"
        sys.argv = [str(script)]
        if proveedor:
            sys.argv.extend(["--proveedor", proveedor])
    else:
        script = calculo_root / "coste_1.py"
        sys.argv = [str(script)]
        if command == "constantes":
            sys.argv.append("--constantes")

    if not script.exists():
        print(f"No se encontro el modulo de calculo: {script}", file=sys.stderr)
        return 2

    runpy.run_path(str(script), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
