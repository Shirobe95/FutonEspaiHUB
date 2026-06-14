from __future__ import annotations

"""Compatibilidad publica para operaciones cloud.

La logica de dominio vive en `futonhub.cloud.services`. Este modulo conserva los
nombres que ya usan CLI y UI mientras se completa la migracion del HUB a mini ERP.
"""

from gestorwoo.cloud.operational_legacy import (  # noqa: F401,F403
    clean_worker_feedback_constant,
    clean_worker_simulated_inventory,
    clean_worker_simulated_order,
    clean_worker_simulated_price_proposal,
    collect_operational_cloud_status,
    format_local_sqlite_dry_run,
    format_price_heart_attack_tests,
    import_single_woocommerce_product_to_supabase,
    inspect_local_sqlite,
    price_heart_attack_tests,
    run_cloud_clean_worker_feedback_test,
    run_cloud_clean_worker_inventory_test,
    run_cloud_clean_worker_order_test,
    run_cloud_clean_worker_price_test,
    run_cloud_import_woocommerce_product,
    run_cloud_operational_status,
    run_cloud_price_heart_attack_tests,
    run_cloud_review_worker_price_test,
    run_cloud_test_constant,
    run_cloud_worker_feedback_test,
    run_cloud_worker_inventory_test,
    run_cloud_worker_order_test,
    run_cloud_worker_price_test,
    run_migrate_sqlite_to_supabase_dry_run,
    review_worker_simulated_price_proposal,
    test_business_constant_change,
    test_worker_feedback_constant_change,
    test_worker_simulated_inventory_change,
    test_worker_simulated_order,
    test_worker_simulated_price_proposal,
)
from futonhub.cloud.services.inventory import (  # noqa: F401
    format_cloud_inventory_search,
    format_internal_inventory_preview,
    preview_internal_inventory_update,
    search_cloud_inventory_items,
    update_internal_inventory_item,
)
from futonhub.cloud.services.price_proposals import (  # noqa: F401
    create_real_price_proposal,
    format_cloud_product_search,
    format_existing_price_proposal_preview,
    format_real_price_proposal_preview,
    format_real_price_proposals,
    get_real_price_proposal,
    list_real_price_proposals,
    preview_existing_price_proposal,
    preview_real_price_proposal,
    review_latest_real_price_proposal,
    search_cloud_products,
)
from futonhub.cloud.services.prices import (  # noqa: F401
    PRICE_PROPOSAL_STATUSES,
    current_price_from_item as _current_price_from_item,
    format_price_safety_for_search as _format_price_safety_for_search,
    money_or_none as _money_or_none,
    price_safety_preview as _price_safety_preview,
    product_type as _product_type,
    short_row_value as _short_row_value,
)
from futonhub.cloud.services.rollback import (  # noqa: F401
    ROLLBACK_ENTITY_SPECS,
    rollback_target_from_snapshot as _rollback_target_from_snapshot,
    rollback_update_payload as _rollback_update_payload,
    short_json_diff as _short_json_diff,
)
from futonhub.cloud.services.woocommerce_publish import (  # noqa: F401
    fetch_approved_price_proposals as _fetch_approved_price_proposals,
    fetch_cloud_item_for_proposal as _fetch_cloud_item_for_proposal,
    fetch_woo_item_readonly as _fetch_woo_item_readonly,
    format_publish_row_for_confirm as _format_publish_row_for_confirm,
    format_woocommerce_publish_preview,
    format_woocommerce_publish_result,
    proposal_item_snapshot as _proposal_item_snapshot,
    publish_woocommerce_price,
    preview_woocommerce_publish,
)
from gestorwoo.cloud.operational_legacy import (  # noqa: F401
    execute_rollback_from_snapshot,
    format_rollback_candidates,
    format_rollback_preview,
    list_rollback_candidates,
    preview_rollback_from_snapshot,
    run_cloud_inventory_update_internal,
    run_cloud_list_real_price_proposals,
    run_cloud_real_price_proposal,
    run_cloud_review_real_price_proposal,
    run_cloud_rollback_candidates,
    run_cloud_rollback_snapshot,
    run_cloud_search_inventory,
    run_cloud_search_products,
    run_cloud_woocommerce_publish_execute,
    run_cloud_woocommerce_publish_preview,
)


# Supplier prices migration wrappers for UI ERP / Pedidos.
from gestorwoo.cloud.operational_legacy import _login_from_console as _supplier_prices_login_from_console  # noqa: E402
from futonhub.cloud.services.supplier_prices import migrate_supplier_prices_to_supabase as _migrate_supplier_prices_to_supabase  # noqa: E402


def run_cloud_supplier_prices_migration_preview() -> int:
    session, settings = _supplier_prices_login_from_console()
    result = _migrate_supplier_prices_to_supabase(session, settings=settings, execute=False)
    print("Preview supplier_prices SQLite -> Supabase inventory_items")
    print(f"Filas supplier_prices locales: {result.get('local_supplier_price_rows')}")
    print(f"Inventory_items Supabase visibles: {result.get('cloud_inventory_items')}")
    print("Por proveedor:")
    for supplier, count in sorted((result.get("by_supplier") or {}).items()):
        print(f"  - {supplier}: {count}")
    print(f"Items a actualizar: {result.get('inventory_items_to_update')}")
    print(f"Conflictos detectados: {result.get('conflict_count')}")
    print(f"Items locales no encontrados en inventory_items Supabase: {result.get('missing_inventory_items_count', 0)}")
    if result.get("missing_inventory_items_sample"):
        print("Muestra no encontrados:", result.get("missing_inventory_items_sample"))
    print("Muestra de updates:")
    for row in result.get("sample_updates", [])[:10]:
        print(f"  - {row.get('item_id')} | principal={row.get('primary_supplier_price')} | pascal={row.get('pascal_price')}")
    return 0


def run_cloud_supplier_prices_migration_execute(confirm: str = "") -> int:
    if confirm != "MIGRAR_PRECIOS_PROVEEDOR":
        print("Para ejecutar usa --confirm MIGRAR_PRECIOS_PROVEEDOR")
        return 2
    session, settings = _supplier_prices_login_from_console()
    result = _migrate_supplier_prices_to_supabase(session, settings=settings, execute=True)
    print("Migración supplier_prices SQLite -> inventory_items Supabase")
    print(f"Operation ID: {result.get('operation_id')}")
    print(f"Local: {result.get('local_supplier_price_rows')}")
    print(f"Migrados: {result.get('migrated')}")
    print(f"Saltados por no existir en inventory_items: {result.get('skipped_missing_count', 0)}")
    if result.get("skipped_missing_sample"):
        print("Muestra saltados:", result.get("skipped_missing_sample"))
    if result.get("errors"):
        print("Errores:")
        for err in result.get("errors", []):
            print(f"  - {err}")
        return 1
    print("OK")
    return 0


from futonhub.cloud.services.supplier_prices import diagnose_supplier_price_columns as _diagnose_supplier_price_columns  # noqa: E402


def run_cloud_supplier_prices_diagnostic() -> int:
    session, settings = _supplier_prices_login_from_console()
    result = _diagnose_supplier_price_columns(session, settings=settings)
    print("Diagnóstico precios proveedor para Pedidos")
    print(f"OK: {result.get('ok')}")
    if not result.get("ok"):
        print(f"Error: {result.get('error')}")
        return 1
    print(f"Filas supplier_prices locales: {result.get('local_supplier_price_rows')}")
    print(f"Items locales a mapear: {result.get('local_items_to_map')}")
    print("Por proveedor local:")
    for supplier, count in sorted((result.get("local_by_supplier") or {}).items()):
        print(f"  - {supplier}: {count}")
    print(f"Items encontrados en inventory_items Supabase: {result.get('supabase_matching_items')}")
    print(f"Items locales NO encontrados en Supabase: {result.get('missing_in_supabase_count')}")
    if result.get("missing_in_supabase_sample"):
        print("Muestra no encontrados:", result.get("missing_in_supabase_sample"))
    print(f"Conflictos detectados: {result.get('conflict_count')}")
    if result.get("conflict_sample"):
        print("Muestra conflictos:")
        for row in result.get("conflict_sample", [])[:5]:
            print(f"  - {row}")
    print("Muestra Supabase:")
    for row in result.get("cloud_sample", [])[:10]:
        print(f"  - {row.get('item_id')} | {row.get('name')} | primary={row.get('primary_supplier_price')} | pascal={row.get('pascal_price')}")
    return 0


from futonhub.cloud.services.inventory_item_import import import_inventory_items_csv as _import_inventory_items_csv, upsert_inventory_items_csv as _upsert_inventory_items_csv  # noqa: E402


def run_cloud_import_inventory_items_csv_preview(csv_path: str) -> int:
    session, _settings = _supplier_prices_login_from_console()
    result = _import_inventory_items_csv(session, csv_path, execute=False)
    print("Preview import inventory_items desde CSV")
    print(f"CSV: {result.get('csv_path')}")
    print(f"Filas CSV: {result.get('total_rows')}")
    print(f"Ya existen en Supabase: {result.get('existing_count')}")
    print(f"Faltan / se insertarían: {result.get('missing_count')}")
    print("Muestra faltantes:")
    for row in result.get("missing_sample", [])[:20]:
        print(f"  - {row.get('item_id')} | {row.get('name')} | precio={row.get('primary_supplier_price')} | m3={row.get('cubic_meters')} | rot={row.get('rotation_c')}")
    return 0


def run_cloud_import_inventory_items_csv_execute(csv_path: str, confirm: str = "") -> int:
    if confirm != "IMPORTAR_ITEMS":
        print("Para ejecutar usa --confirm IMPORTAR_ITEMS")
        return 2
    session, _settings = _supplier_prices_login_from_console()
    result = _import_inventory_items_csv(session, csv_path, execute=True, confirm=confirm)
    print("Import inventory_items desde CSV")
    print(f"Operation ID: {result.get('operation_id')}")
    print(f"Filas CSV: {result.get('total_rows')}")
    print(f"Ya existían: {result.get('existing_count')}")
    print(f"Objetivo insertar: {result.get('insert_target')}")
    print(f"Insertados: {result.get('inserted')}")
    if result.get("errors"):
        print("Errores:")
        for error in result.get("errors", []):
            print(f"  - {error}")
        return 1
    print("OK")
    return 0



def run_cloud_upsert_inventory_items_csv_preview(csv_path: str) -> int:
    session, _settings = _supplier_prices_login_from_console()
    result = _upsert_inventory_items_csv(session, csv_path, execute=False)
    print("Preview UPSERT inventory_items desde CSV")
    print(f"CSV: {result.get('csv_path')}")
    print(f"Filas CSV: {result.get('total_rows')}")
    print("Muestra:")
    for row in result.get("sample", [])[:20]:
        print(f"  - {row.get('item_id')} | {row.get('name')} | precio={row.get('primary_supplier_price')} | m3={row.get('cubic_meters')} | rot={row.get('rotation_c')}")
    return 0


def run_cloud_upsert_inventory_items_csv_execute(csv_path: str, confirm: str = "") -> int:
    if confirm != "IMPORTAR_ITEMS":
        print("Para ejecutar usa --confirm IMPORTAR_ITEMS")
        return 2
    session, _settings = _supplier_prices_login_from_console()
    result = _upsert_inventory_items_csv(session, csv_path, execute=True, confirm=confirm)
    print("UPSERT inventory_items desde CSV")
    print(f"Operation ID: {result.get('operation_id')}")
    print(f"Filas CSV: {result.get('total_rows')}")
    print(f"Procesados: {result.get('upserted')}")
    if result.get("errors"):
        print("Errores:")
        for error in result.get("errors", []):
            print(f"  - {error}")
        return 1
    print("OK")
    return 0
