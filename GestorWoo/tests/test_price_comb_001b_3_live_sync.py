from __future__ import annotations

import sys
import unittest
import inspect
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "GestorWoo" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from futonhub.cloud.services import price_proposals  # noqa: E402
from futonhub.cloud.services.price_proposals import ensure_woo_variations_synced  # noqa: E402
from futonhub.services.combination_price_impact import CombinationPriceImpactService  # noqa: E402
from futonhub.services.price_proposal_live_context import prepare_price_addition  # noqa: E402
from futonhub.ui.erp.prototype import FutonHubErpPrototype  # noqa: E402


class Response:
    def __init__(self, data):
        self.data = data

    def execute(self):
        return SimpleNamespace(data=self.data)


class Query:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self.filters = {}
        self.pending_update = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters[key] = value
        return self

    def limit(self, _value):
        return self

    def insert(self, payload):
        self.store.setdefault(self.table, []).append(dict(payload))
        return Response([payload])

    def update(self, payload):
        self.pending_update = dict(payload)
        return self

    def execute(self):
        rows = self.store.setdefault(self.table, [])
        selected = [
            dict(row) for row in rows
            if all(row.get(key) == value for key, value in self.filters.items())
        ]
        if self.pending_update is not None:
            for row in rows:
                if all(row.get(key) == value for key, value in self.filters.items()):
                    row.update(self.pending_update)
            selected = [dict(row) for row in rows if all(row.get(key) == value for key, value in self.filters.items())]
        return Response(selected)


class Client:
    def __init__(self, store=None):
        self.store = store if store is not None else {"product_variations": []}

    def table(self, name):
        return Query(self.store, name)


class Session:
    def __init__(self, store=None, *, user_id="u-7", user_name="Ana"):
        self.client = Client(store)
        self.user_id = user_id
        self.user_name = user_name


class Woo:
    def __init__(self, payloads):
        self.payloads = {
            key: value if isinstance(value, Exception) else dict(value)
            for key, value in payloads.items()
        }
        self.reads = []

    def get(self, endpoint, params=None):
        self.reads.append(endpoint)
        if endpoint == "products" and params and params.get("sku"):
            sku = str(params["sku"])
            matches = [
                value
                for key, value in self.payloads.items()
                if key.startswith("products/")
                and isinstance(value, dict)
                and value.get("sku") == sku
            ]
            return SimpleNamespace(json=lambda: [dict(value) for value in matches])
        value = self.payloads.get(endpoint)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise RuntimeError(f"unexpected Woo endpoint {endpoint}")
        return SimpleNamespace(json=lambda: dict(value))


def variation(*, variation_id=13092, parent_id=3658, sku="0201001|0201001|1249001|1249001|0619007|0619007", price="749.90"):
    return {
        "id": variation_id,
        "parent_id": parent_id,
        "name": "Combinacion",
        "sku": sku,
        "regular_price": "950.00",
        "sale_price": price,
        "price": price,
        "on_sale": True,
        "date_on_sale_from": "2026-08-01T00:00:00",
        "date_on_sale_to": None,
        "status": "publish",
        "stock_status": "instock",
        "manage_stock": False,
        "stock_quantity": None,
        "attributes": [{"name": "Color", "option": "Natural"}],
        "date_modified_gmt": "2026-08-05T09:00:00",
    }


class FixedImpact:
    def impact_for_changes(self, _changes):
        return {
            "included_combinations": [{
                "combination_woo_id": "13092",
                "combination_parent_woo_id": "3658",
                "combination_sku": "0201001|0201001|1249001|1249001|0619007|0619007",
                "combination_name": "Combinacion",
                "effective_current_price": "749.90",
                "component_delta": "2.00",
                "simulated_effective_price": "751.90",
                "modified_components": [{
                    "component_item_id": "201001",
                    "component_sku": "0201001",
                    "proposal_trace_key": "line-1",
                    "quantity": "2",
                }],
                "proposal_trace_keys": ["line-1"],
                "excluded": "NO",
            }],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "counts": {},
        }


class AccumulatingImpact:
    """Minimal exact destination graph used to test popup delta accumulation."""

    def impact_for_changes(self, changes):
        components = []
        total = Decimal("0")
        for change in changes:
            old_price = Decimal(str(change["old_price"]))
            new_price = Decimal(str(change["new_price"]))
            delta = new_price - old_price
            total += delta
            components.append({
                "component_item_id": str(change["physical_item_id"]),
                "component_sku": str(change["physical_sku"]),
                "proposal_trace_key": str(change["proposal_key"]),
                "quantity": "1",
            })
        return {
            "included_combinations": [{
                "combination_woo_id": "13092",
                "combination_parent_woo_id": "3658",
                "combination_sku": "0201001|0201001|1249001|1249001|0619007|0619007",
                "combination_name": "Combinacion",
                "effective_current_price": "749.90",
                "component_delta": f"{total:.2f}",
                "simulated_effective_price": f"{Decimal('749.90') + total:.2f}",
                "modified_components": components,
                "proposal_trace_keys": [row["proposal_trace_key"] for row in components],
                "excluded": "NO",
            }],
            "excluded_combinations": [],
            "unmatched_changes": [],
            "counts": {},
        }


class LiveVariationSynchronizationTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = "products/3658/variations/13092"
        self.payload = variation()

    def test_missing_13092_is_inserted_from_exact_woo_variation(self):
        session = Session()
        woo = Woo({self.endpoint: self.payload})
        with patch("futonhub.cloud.services.price_proposals.write_audit_event"), patch(
            "futonhub.cloud.services.price_proposals.write_snapshot"
        ):
            result = ensure_woo_variations_synced(
                session,
                [{"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]}],
                woo_client=woo,
                reason="PROPOSAL_ITEM_ADDED",
                replica_write=True,
            )
        row = result["results"][0]
        self.assertEqual(row["woo_live_status"], "FOUND")
        self.assertEqual(row["supabase_replica_status"], "SYNCED")
        self.assertEqual(row["sync_action"], "INSERT")
        self.assertEqual(row["proposal_line_status"], "READY")
        self.assertEqual(row["price_context"]["price"], "749.90")
        self.assertEqual(session.client.store["product_variations"][0]["woo_id"], 13092)
        self.assertEqual(woo.reads, [self.endpoint])

    def test_outdated_replica_is_updated_without_changing_woo_identity(self):
        session = Session({"product_variations": [{
            "woo_id": 13092,
            "parent_woo_id": 3658,
            "parent_name": "Anterior",
            "sku": self.payload["sku"],
            "status": "publish",
            "regular_price": "100.00",
            "sale_price": "",
            "price": "100.00",
            "stock_status": "instock",
            "stock_quantity": None,
            "attributes_json": [],
            "attributes_label": "",
            "raw_json": {},
        }]})
        with patch("futonhub.cloud.services.price_proposals.write_audit_event"), patch(
            "futonhub.cloud.services.price_proposals.write_snapshot"
        ):
            result = ensure_woo_variations_synced(
                session,
                [{"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]}],
                woo_client=Woo({self.endpoint: self.payload}),
                reason="PRE_APPLY_REVALIDATION",
                replica_write=True,
            )
        self.assertEqual(result["results"][0]["sync_action"], "UPDATE")
        saved = session.client.store["product_variations"][0]
        self.assertEqual(saved["woo_id"], 13092)
        self.assertEqual(saved["parent_woo_id"], 3658)
        self.assertEqual(saved["price"], "749.90")

    def test_live_read_error_blocks_apply_and_never_inserts(self):
        session = Session()
        result = ensure_woo_variations_synced(
            session,
            [{"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]}],
            woo_client=Woo({self.endpoint: RuntimeError("Woo unavailable")}),
            reason="PROPOSAL_ITEM_ADDED",
        )
        self.assertEqual(result["results"][0]["woo_live_status"], "READ_ERROR")
        self.assertEqual(result["results"][0]["proposal_line_status"], "BLOCKED_SYNC_ERROR")
        self.assertEqual(result["results"][0]["apply_allowed"], "NO")
        self.assertEqual(session.client.store["product_variations"], [])

    def test_duplicate_destination_uses_one_woo_read(self):
        session = Session()
        woo = Woo({self.endpoint: self.payload})
        result = ensure_woo_variations_synced(
            session,
            [
                {"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]},
                {"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]},
            ],
            woo_client=woo,
            reason="PROPOSAL_ITEM_ADDED",
        )
        self.assertEqual(result["variations_requested"], 1)
        self.assertEqual(woo.reads, [self.endpoint])
        self.assertEqual(result["results"][0]["sync_action"], "INSERT")
        self.assertEqual(result["results"][0]["supabase_replica_status"], "PENDING_SYNC")

    def test_missing_authenticated_actor_is_blocked(self):
        with self.assertRaisesRegex(Exception, "sesion de usuario"):
            ensure_woo_variations_synced(
                Session(user_id="", user_name=""),
                [{"woo_id": 13092, "woo_parent_id": 3658}],
                woo_client=Woo({self.endpoint: self.payload}),
                reason="PROPOSAL_ITEM_ADDED",
            )

    def test_live_price_overrides_cached_price_and_populates_derived_context(self):
        product = {
            "id": 9001,
            "sku": "0201001",
            "regular_price": "155.00",
            "sale_price": "",
            "price": "155.00",
            "on_sale": False,
            "date_on_sale_from": None,
            "date_on_sale_to": None,
            "status": "publish",
            "stock_status": "instock",
            "manage_stock": False,
            "stock_quantity": None,
            "attributes": [],
            "date_modified_gmt": "2026-08-05T09:00:00",
        }
        session = Session()
        prepared = prepare_price_addition(
            [{
                "code": "0201001",
                "name": "Tatami 80 x 200",
                "cached_price": "128.00",
                "source": {
                    "physical_item_id": "201001",
                    "physical_sku": "0201001",
                    "woo_id": 9001,
                    "woo_item_kind": "product",
                    "woo_sku": "0201001",
                },
            }],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=FixedImpact(),
            woo_client=Woo({"products/9001": product, self.endpoint: self.payload}),
            session=session,
        )
        direct = prepared["direct_rows"][0]
        derived = prepared["combination_plan"]["derived_lines"][0]
        self.assertEqual(direct["old_price_value"], 155.0)
        self.assertEqual(direct["new_price_value"], 156.0)
        self.assertEqual(direct["price_source"], "WOO_LIVE")
        self.assertEqual(derived["status"], "READY")
        self.assertEqual(derived["effective_current_price"], "749.90")
        self.assertEqual(derived["simulated_effective_price"], "751.90")

    def test_woo_error_uses_cache_only_as_stale_and_blocks_apply(self):
        prepared = prepare_price_addition(
            [{
                "code": "0201001",
                "cached_price": "128.00",
                "source": {
                    "physical_item_id": "201001",
                    "physical_sku": "0201001",
                    "woo_id": 9001,
                    "woo_item_kind": "product",
                },
            }],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=FixedImpact(),
            woo_client=Woo({"products/9001": RuntimeError("offline")}),
            session=Session(),
        )
        row = prepared["direct_rows"][0]
        self.assertEqual(row["price_source"], "WOO_LIVE_UNAVAILABLE")
        self.assertEqual(row["price_stale"], "NO")
        self.assertEqual(row["apply_allowed"], "NO")

    def test_tatami_0201001_returns_its_known_exact_variations(self):
        service = CombinationPriceImpactService(ROOT / "auditoria" / "out")
        prepared = prepare_price_addition(
            [{
                "code": "0201001",
                "cached_price": "128.00",
                "source": {
                    "physical_item_id": "201001",
                    "physical_sku": "0201001",
                    "woo_id": 9001,
                    "woo_item_kind": "product",
                    "woo_sku": "0201001",
                    "primary_supplier_price": "3.00",
                },
            }],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=service,
            woo_client=Woo({"products/9001": {
                "id": 9001, "sku": "0201001", "regular_price": "155.00", "sale_price": "", "price": "155.00",
                "on_sale": False, "date_on_sale_from": None, "date_on_sale_to": None, "status": "publish",
                "stock_status": "instock", "manage_stock": False, "stock_quantity": None, "attributes": [],
                "date_modified_gmt": "2026-08-05T09:00:00",
            }}),
            session=None,
        )
        impact = prepared["combination_impact"]
        self.assertEqual(len(impact["included_combinations"]), 18)
        self.assertEqual(prepared["direct_rows"][0]["old_price_value"], 155.0)
        target = next(row for row in impact["included_combinations"] if row["combination_woo_id"] == "13092")
        self.assertEqual(target["combination_parent_woo_id"], "3658")
        self.assertEqual(target["modified_components"][0]["component_sku"], "0201001")

    def test_both_tatamis_deduplicate_exact_woo_destinations(self):
        service = CombinationPriceImpactService(ROOT / "auditoria" / "out")
        product = lambda woo_id, sku: {
            "id": woo_id, "sku": sku, "regular_price": "150.00", "sale_price": "", "price": "150.00",
            "on_sale": False, "date_on_sale_from": None, "date_on_sale_to": None, "status": "publish",
            "stock_status": "instock", "manage_stock": False, "stock_quantity": None, "attributes": [],
            "date_modified_gmt": "2026-08-05T09:00:00",
        }
        prepared = prepare_price_addition(
            [
                {"code": "0201001", "source": {"physical_item_id": "201001", "physical_sku": "0201001", "woo_id": 9001, "woo_item_kind": "product", "woo_sku": "0201001"}},
                {"code": "0201002", "source": {"physical_item_id": "201002", "physical_sku": "0201002", "woo_id": 9002, "woo_item_kind": "product", "woo_sku": "0201002"}},
            ],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=service,
            woo_client=Woo({"products/9001": product(9001, "0201001"), "products/9002": product(9002, "0201002")}),
            session=None,
        )
        destination_ids = [row["combination_woo_id"] for row in prepared["combination_impact"]["included_combinations"]]
        self.assertEqual(len(destination_ids), len(set(destination_ids)))
        self.assertIn("13092", destination_ids)

    def test_popup_reports_incremental_and_accumulated_impact(self):
        product = {
            "id": 9002, "sku": "0201002", "regular_price": "120.00", "sale_price": "", "price": "120.00",
            "on_sale": False, "date_on_sale_from": None, "date_on_sale_to": None, "status": "publish",
            "stock_status": "instock", "manage_stock": False, "stock_quantity": None, "attributes": [],
            "date_modified_gmt": "2026-08-05T09:00:00",
        }
        prepared = prepare_price_addition(
            [{
                "code": "0201002",
                "name": "Tatami 90 x 200",
                "source": {
                    "physical_item_id": "201002", "physical_sku": "0201002", "woo_id": 9002,
                    "woo_item_kind": "product", "woo_sku": "0201002",
                },
            }],
            adjustment_mode="amount",
            adjustment_value="1.00",
            impact_service=AccumulatingImpact(),
            woo_client=Woo({"products/9002": product, self.endpoint: self.payload}),
            session=Session(),
            existing_changes=[{
                "physical_item_id": "201001", "physical_sku": "0201001",
                "old_price": "155.00", "new_price": "156.00", "proposal_key": "product:9001",
            }],
        )
        line = prepared["combination_plan"]["derived_lines"][0]
        self.assertEqual(line["incremental_component_delta"], "+1.00")
        self.assertEqual(line["previous_accumulated_delta"], "+1.00")
        self.assertEqual(line["new_accumulated_delta"], "+2.00")
        self.assertEqual(line["impact_display_status"], "UPDATED_ACCUMULATED_IMPACT")
        self.assertEqual(len(line["modified_components"]), 2)

    def test_popup_is_opened_before_model_mutation_and_cancel_path_is_separate(self):
        add_source = inspect.getsource(FutonHubErpPrototype._price_add_rows_to_proposal)
        popup_source = inspect.getsource(FutonHubErpPrototype._open_price_item_impact_popup)
        confirm_source = inspect.getsource(FutonHubErpPrototype._confirm_price_item_impact_add)
        self.assertIn("prepare_price_addition(", add_source)
        self.assertIn("_open_price_item_impact_popup(prepared)", add_source)
        self.assertIn('if self.__dict__.get("_cloud_session") is None:', add_source)
        self.assertIn("Cancelar", popup_source)
        self.assertIn("Anadir articulo y sus impactos", popup_source)
        self.assertIn("Delta anterior", popup_source)
        self.assertIn("Componentes / cantidad", popup_source)
        self.assertIn("impact_display_status", popup_source)
        self.assertIn("_price_model_put(", confirm_source)

    def test_ui_adapter_sends_physical_and_woo_identities_separately(self):
        source = inspect.getsource(FutonHubErpPrototype._price_combination_change_from_preview_row)
        self.assertIn('"physical_item_id"', source)
        self.assertIn('"physical_sku"', source)
        self.assertIn('"woo_parent_id"', source)
        self.assertIn('"woo_sku"', source)
        self.assertNotIn('"target_keys"', source)

    def test_live_variation_snapshot_allows_draft_validation_when_replica_is_missing(self):
        snapshot = {
            "woo_id": 13092,
            "woo_parent_id": 3658,
            "woo_item_kind": "variation",
            "name": "Combinacion",
            "sku": self.payload["sku"],
            "effective_price": "749.90",
            "regular_price": "950.00",
            "sale_price": "749.90",
            "price_source": "WOO_LIVE",
        }
        item = price_proposals._fetch_cloud_item_for_price(
            Session(),
            "variation",
            13092,
            item_snapshot=snapshot,
        )
        self.assertEqual(item["woo_id"], 13092)
        self.assertEqual(item["price"], "749.90")
        self.assertEqual(item["sku"], "0201001|0201001|1249001|1249001|0619007|0619007")

    def test_sync_audit_keeps_the_identified_actor(self):
        session = Session(user_id="u-99", user_name="Marta")
        with patch("futonhub.cloud.services.price_proposals.write_audit_event") as audit, patch(
            "futonhub.cloud.services.price_proposals.write_snapshot"
        ):
            ensure_woo_variations_synced(
                session,
                [{"woo_id": 13092, "woo_parent_id": 3658, "woo_sku": self.payload["sku"]}],
                woo_client=Woo({self.endpoint: self.payload}),
                reason="PROPOSAL_ITEM_ADDED",
                replica_write=True,
            )
        event = audit.call_args.args[1]
        self.assertEqual(event.after_data["actor"], {"user_id": "u-99", "user_name": "Marta"})


if __name__ == "__main__":
    unittest.main()
