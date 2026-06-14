from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from gestorwoo.cloud.operational_legacy import _login_from_console  # noqa: E402
from futonhub.cloud.services.inventory_item_import import upsert_inventory_items_csv  # noqa: E402


DEFAULT_CSV = ROOT / "docs" / "imports" / "E-2026-03_12_items_faltantes_completos.csv"


def main() -> int:
    parser = argparse.ArgumentParser(description="Import directo 12 items faltantes E-2026-03.")
    parser.add_argument("--csv", default=str(DEFAULT_CSV), help="Ruta CSV.")
    parser.add_argument("--execute", action="store_true", help="Ejecutar import. Si no, solo preview.")
    parser.add_argument("--confirm", default="", help="Debe ser IMPORTAR_ITEMS para ejecutar.")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"[ERROR] No existe CSV: {csv_path}")
        print("Prueba con ruta absoluta o verifica GestorWoo/docs/imports.")
        return 1

    session, _settings = _login_from_console()

    if args.execute:
        if args.confirm != "IMPORTAR_ITEMS":
            print("Para ejecutar usa --confirm IMPORTAR_ITEMS")
            return 2
        result = upsert_inventory_items_csv(session, csv_path, execute=True, confirm=args.confirm)
        print("UPSERT inventory_items desde CSV")
        print(f"Operation ID: {result.get('operation_id')}")
        print(f"CSV: {result.get('csv_path')}")
        print(f"Filas CSV: {result.get('total_rows')}")
        print(f"Procesados: {result.get('upserted')}")
        if result.get("errors"):
            print("Errores:")
            for error in result.get("errors", []):
                print(f"  - {error}")
            return 1
        print("OK")
        return 0

    result = upsert_inventory_items_csv(session, csv_path, execute=False)
    print("Preview UPSERT inventory_items desde CSV")
    print(f"CSV: {result.get('csv_path')}")
    print(f"Filas CSV: {result.get('total_rows')}")
    print("Muestra:")
    for row in result.get("sample", [])[:20]:
        print(
            f"  - {row.get('item_id')} | {row.get('name')} | "
            f"precio={row.get('primary_supplier_price')} | "
            f"m3={row.get('cubic_meters')} | rot={row.get('rotation_c')}"
        )
    print("")
    print("Para ejecutar: IMPORTAR_12_ITEMS_E_2026_03.bat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
