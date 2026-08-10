from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_woo_catalog_index import build_woo_read_only_index  # noqa: E402
from futonhub.services.woo_map_001a_7_1_candidate_reconciliation import (  # noqa: E402
    FROZEN_STATUSES,
    _rejection_reason,
    evaluate_candidate,
    reconcile_residual_candidates,
    resolve_effective_physical_variant,
)


class ReadOnlyWoo:
    def __init__(self, products: list[dict[str, object]], variations: dict[int, list[dict[str, object]]] | None = None) -> None:
        self.products = products
        self.variations = variations or {}

    def iter_products(self):
        yield from self.products

    def iter_product_variations(self, product_id: int):
        yield from self.variations.get(product_id, [])


def product(woo_id: int, name: str, *, kind: str = "simple", sku: str = "", status: str = "publish") -> dict[str, object]:
    return {
        "id": woo_id,
        "name": name,
        "sku": sku,
        "type": kind,
        "status": status,
        "catalog_visibility": "visible",
        "date_modified": "2026-08-09T00:00:00",
        "attributes": [],
        "categories": [],
        "images": [],
        "description": "",
    }


def variation(woo_id: int, parent_id: int, *, size: str, color: str, sku: str = "", status: str = "publish") -> dict[str, object]:
    return {
        "id": woo_id,
        "parent_id": parent_id,
        "name": "",
        "sku": sku,
        "type": "variation",
        "status": status,
        "catalog_visibility": "visible",
        "date_modified": "2026-08-09T00:00:00",
        "attributes": [{"name": "Tamano", "option": size}, {"name": "Color", "option": color}],
        "images": [],
    }


def physical(item_id: str, sku: str, **overrides: str) -> dict[str, str]:
    row = {
        "item_id": item_id,
        "hub_item_code": sku,
        "heca_reference": sku,
        "name": "Futon Algodon 140x200x14 Natural",
        "family": "Futones",
        "filter_family": "Futones",
        "filter_group": "Algodon",
        "filter_size": "140x200x14",
        "filter_gama": "Natural",
        "item_record_type": "simple",
        "is_pack": "false",
    }
    row.update(overrides)
    return row


def entity(index, woo_id: int):
    key = str(woo_id)
    return index.products_by_id.get(key) or index.variations_by_id[key]


class WooMap001A71CandidateReconciliationTests(unittest.TestCase):
    def setUp(self) -> None:
        eko_parent = product(3001, "Cama Eko-bed 160x200 Natural", kind="variable")
        okinawa_parent = product(3646, "Mesita Okinawa baja 45x45x25", kind="variable")
        self.index = build_woo_read_only_index(ReadOnlyWoo(
            [
                eko_parent,
                okinawa_parent,
                product(3002, "Sofa cama Zurich 160x200 Natural"),
                product(3003, "Cama Tokio 160x200 Natural"),
                product(3004, "Funda para futon 160x200 Natural"),
                product(3005, "Tatami plegable 160x200 Natural", kind="variable"),
                product(3006, "Futon Algodon 140x200x14,5 Natural"),
                product(3007, "Sofa cama Luna 140x200 Natural"),
                product(3008, "Base para Tatami Macao 180x200 Natural"),
                product(3009, "Futon Algodon Natural"),
                product(3010, "Tatami plegable 90x200x1,2 Verde oscuro"),
                product(3631, "Funda para futon", kind="variable"),
            ],
            {
                3001: [variation(3101, 3001, size="160x200", color="Natural")],
                3646: [variation(11838, 3646, size="45x45x25", color="Crudo sin barniz")],
                3005: [variation(3105, 3005, size="160x200", color="Natural", sku="TAT|PACK")],
                3631: [
                    variation(3773, 3631, size="80x200x13", color="Crudo", sku="0608007"),
                    variation(3766, 3631, size="80x200x13", color="Rojo", sku="0607007"),
                    variation(3784, 3631, size="80x200x13", color="Azul", sku="0609007"),
                    variation(3811, 3631, size="80x200x13", color="Amarillo", sku="0615007"),
                ],
            },
        ))

    def assess(self, row: dict[str, str], woo_id: int):
        return evaluate_candidate(row, entity(self.index, woo_id), woo_index=self.index, claims={})

    def test_eko_bed_rejects_zurich_tokio_and_cover_before_human_review(self) -> None:
        row = physical("EKO", "EKO", name="Cama Eko-bed 160x200 Natural", family="Camas", filter_family="Camas", filter_group="Eko-bed", filter_size="160x200")
        zurich = self.assess(row, 3002)
        tokio = self.assess(row, 3003)
        cover = self.assess(row, 3004)
        self.assertEqual(zurich.family_gate, "FAIL")
        self.assertEqual(cover.family_gate, "FAIL")
        self.assertEqual(tokio.model_gate, "MODEL_GATE_INSUFFICIENT")
        self.assertFalse(any(candidate.identity_gates_pass for candidate in (zurich, tokio, cover)))

    def test_cover_never_uses_tatami_sofa_or_futon_candidate(self) -> None:
        row = physical("COVER", "COVER", name="Funda para futon 160x200 Natural", family="Fundas", filter_family="Fundas", filter_group="Funda futon", filter_size="160x200")
        tatami = self.assess(row, 3005)
        sofa = self.assess(row, 3007)
        futon = self.assess(row, 3006)
        self.assertTrue(all(candidate.family_gate == "FAIL" for candidate in (tatami, sofa, futon)))

    def test_futon_cotton_never_uses_cover_or_sofa_candidate(self) -> None:
        row = physical("FUT", "FUT")
        cover = self.assess(row, 3004)
        sofa = self.assess(row, 3007)
        self.assertTrue(all(candidate.family_gate == "FAIL" for candidate in (cover, sofa)))

    def test_macao_cama_never_matches_base_macao(self) -> None:
        row = physical("MAC", "0402014", name="Cama Macao 180x200 Natural", family="Camas", filter_family="Camas", filter_group="Macao", filter_size="180x200")
        candidate = self.assess(row, 3008)
        self.assertEqual(candidate.family_gate, "FAIL")
        self.assertNotEqual(candidate.model_gate, "MODEL_GATE_PASS")

    def test_luna_never_matches_tokio(self) -> None:
        row = physical("LUNA", "LUNA", name="Sofa cama Luna 160x200 Natural", family="Sofás Cama", filter_family="Sofás Cama", filter_group="Luna", filter_size="160x200")
        candidate = self.assess(row, 3003)
        self.assertEqual(candidate.family_gate, "FAIL")
        self.assertNotEqual(candidate.model_gate, "MODEL_GATE_PASS")

    def test_variable_parent_is_context_not_direct_candidate(self) -> None:
        row = physical("EKO", "EKO", name="Cama Eko-bed 160x200 Natural", family="Camas", filter_family="Camas", filter_group="Eko-bed", filter_size="160x200")
        candidate = self.assess(row, 3001)
        self.assertEqual(candidate.model_gate, "MODEL_GATE_PASS")
        self.assertEqual(candidate.kind_gate, "FAIL")
        self.assertEqual(candidate.kind_note, "CONTEXT_PARENT")
        self.assertFalse(candidate.identity_gates_pass)

    def test_okinawa_is_business_equivalence_not_direct_match(self) -> None:
        row = physical("OKI", "0902005", name="Mesita Okinawa baja 45x45x25 Natural", family="Complementos", filter_family="Complementos", filter_group="Mesitas", filter_size="45x45x25", filter_gama="Natural")
        parent = self.assess(row, 3646)
        child = self.assess(row, 11838)
        self.assertEqual(parent.kind_note, "CONTEXT_PARENT")
        self.assertTrue(child.business_equivalence_candidate)
        self.assertFalse(child.identity_gates_pass)
        self.assertEqual(child.variant_gate, "FAIL")

    def test_missing_entity_dimension_and_pack_dimension_cannot_pass(self) -> None:
        row = physical("MISS", "MISS", name="Futon Algodon 140x200x14 Natural")
        missing = self.assess(row, 3009)
        pack = self.assess(row, 3105)
        self.assertEqual(missing.size_gate, "INSUFFICIENT")
        self.assertFalse(missing.identity_gates_pass)
        self.assertEqual(pack.kind_gate, "FAIL")
        self.assertEqual(pack.kind_note, "PACK_INSTEAD_OF_DIRECT")
        self.assertFalse(pack.identity_gates_pass)

    def test_fourteen_never_equals_fourteen_point_five_and_verde_never_equals_oscuro(self) -> None:
        size = self.assess(physical("SIZE", "SIZE"), 3006)
        color = self.assess(physical("COLOR", "COLOR", name="Tatami plegable 90x200x1,2 Verde", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Verde"), 3010)
        self.assertEqual(size.size_gate, "FAIL")
        self.assertEqual(color.variant_gate, "FAIL")
        self.assertFalse(size.identity_gates_pass)
        self.assertFalse(color.identity_gates_pass)

    def test_no_gama_uses_catalog_range_amarilla_and_matches_amarillo_only(self) -> None:
        row = physical(
            "COVER-YELLOW", "0615007", name="Funda Futon Sesamo 80x200x13 Amarilla", family="Fundas",
            filter_family="Fundas", filter_group="Funda futon", filter_size="80x200x13", filter_gama="NO_GAMA",
            catalog_range="Amarilla",
        )
        effective = resolve_effective_physical_variant(row)
        self.assertEqual((effective.value, effective.source, effective.canonical), ("Amarilla", "CATALOG_RANGE", "AMARILLO"))
        for woo_id in (3773, 3766, 3784):
            candidate = self.assess(row, woo_id)
            self.assertEqual(candidate.variant_gate, "FAIL")
            self.assertFalse(candidate.identity_gates_pass)
            self.assertEqual(_rejection_reason(candidate, code="0615007"), "VARIANT_GATE_FAIL")
        yellow = self.assess(row, 3811)
        self.assertEqual(yellow.variant_gate, "PASS")
        self.assertTrue(yellow.identity_gates_pass)

    def test_no_gama_uses_catalog_range_negra_and_matches_negro(self) -> None:
        row = physical(
            "COVER-BLACK", "0616010", name="Funda Futon 120x200x14 Negra", family="Fundas",
            filter_family="Fundas", filter_group="Funda futon", filter_size="80x200x13", filter_gama="NO_GAMA",
            catalog_range="Negra",
        )
        effective = resolve_effective_physical_variant(row)
        self.assertEqual((effective.value, effective.source, effective.canonical), ("Negra", "CATALOG_RANGE", "NEGRO"))
        black = self.assess(row, 3773)
        self.assertEqual(black.variant_gate, "FAIL")
        black.entity["raw"]["attributes"][1]["option"] = "Negro"
        normalized = self.assess(row, 3773)
        self.assertEqual(normalized.variant_gate, "PASS")

    def test_catalog_range_empty_uses_explicit_name_and_name_without_variant_is_not_required(self) -> None:
        named = physical("NAME", "NAME", name="Funda Futon 80x200x13 Roja", filter_gama="NO_GAMA", catalog_range="")
        absent = physical("NONE", "NONE", name="Funda Futon 80x200x13", filter_gama="NO_GAMA", catalog_range="")
        self.assertEqual(resolve_effective_physical_variant(named).source, "CANONICAL_NAME_EXPLICIT")
        self.assertEqual(resolve_effective_physical_variant(named).canonical, "ROJO")
        self.assertEqual(resolve_effective_physical_variant(absent).source, "NOT_REQUIRED")

    def test_controlled_variant_normalization_keeps_distinct_colours_distinct(self) -> None:
        green = physical("GREEN", "GREEN", name="Tatami plegable 90x200x1,2 Verde", family="Tatamis", filter_family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="NO_GAMA", catalog_range="Verde")
        navy = physical("NAVY", "NAVY", name="Funda Futon 80x200x13 Azul", family="Fundas", filter_family="Fundas", filter_group="Funda futon", filter_size="80x200x13", filter_gama="NO_GAMA", catalog_range="Azul")
        self.assertEqual(self.assess(green, 3010).variant_gate, "FAIL")
        blue_navy = self.assess(navy, 3784)
        blue_navy.entity["raw"]["attributes"][1]["option"] = "Azul marino"
        self.assertEqual(self.assess(navy, 3784).variant_gate, "FAIL")

    def test_master_keeps_177_safe_rows_and_classifies_all_254(self) -> None:
        rows: list[dict[str, str]] = []
        prior: list[dict[str, str]] = []
        for index in range(174):
            row = physical(f"SAFE{index:03d}", f"SAFE{index:03d}")
            rows.append(row)
            prior.append({"physical_item_id": row["item_id"], "physical_sku": row["hub_item_code"], "woo_resolution_status": "ACTIVE_DIRECT_WOO_VERIFIED", "safe_to_persist": "YES", "woo_kind": "product", "woo_id": str(9000 + index), "woo_parent_id": "", "frozen_marker": "verified"})
        for code, item_id in (("0201013", "S1"), ("0208001", "S2"), ("0216001", "S3")):
            row = physical(item_id, code)
            rows.append(row)
            prior.append({"physical_item_id": item_id, "physical_sku": code, "woo_resolution_status": "ACTIVE_DIRECT_WOO_SAFE_PLAN", "safe_to_persist": "YES", "woo_kind": "variation", "woo_id": code, "woo_parent_id": "3657", "frozen_marker": "safe-plan"})
        for code in ("0406006", "0404017"):
            row = physical(f"R{code}", code)
            rows.append(row)
            prior.append({"physical_item_id": row["item_id"], "physical_sku": code, "woo_resolution_status": "RETIRED_CONFIRMED_BY_USER", "safe_to_persist": "NO", "frozen_marker": "retired"})
        for index in range(5):
            row = physical(f"COMP{index}", f"COMP{index}")
            rows.append(row)
            prior.append({"physical_item_id": row["item_id"], "physical_sku": row["hub_item_code"], "woo_resolution_status": "NO_DIRECT_WOO_ENTITY_SUPPORTED", "safe_to_persist": "NO", "frozen_marker": "component"})
        for index in range(70):
            row = physical(f"RES{index:03d}", f"RES{index:03d}")
            rows.append(row)
            prior.append({"physical_item_id": row["item_id"], "physical_sku": row["hub_item_code"], "woo_resolution_status": "REVIEW_USER_LINK", "safe_to_persist": "NO"})
        self.assertEqual(len(rows), 254)
        result = reconcile_residual_candidates(rows, previous_master_rows=prior, woo_index=self.index)
        master = {row["physical_item_id"]: row for row in result["master"]}
        self.assertEqual(len(master), 254)
        self.assertEqual(result["summary"]["unclassified"], 0)
        self.assertEqual(sum(1 for row in master.values() if row["woo_resolution_status"] == "ACTIVE_DIRECT_WOO_VERIFIED"), 174)
        self.assertEqual(sum(1 for row in master.values() if row["woo_resolution_status"] == "ACTIVE_DIRECT_WOO_SAFE_PLAN"), 3)
        self.assertEqual(master["SAFE000"]["frozen_marker"], "verified")
        self.assertEqual(sum(1 for row in master.values() if row["woo_resolution_status"] in FROZEN_STATUSES), 184)

    def test_service_has_no_woo_or_database_write_path(self) -> None:
        source = inspect.getsource(reconcile_residual_candidates)
        for forbidden in (".put(", ".post(", ".delete(", "INSERT ", "UPDATE ", "DELETE "):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
