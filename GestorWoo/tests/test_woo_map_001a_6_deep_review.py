from __future__ import annotations

import inspect
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from futonhub.services.price_woo_catalog_index import build_woo_read_only_index  # noqa: E402
from futonhub.services.woo_map_001a_6_deep_review import deep_review  # noqa: E402


class ReadOnlyWoo:
    def __init__(self, products: list[dict[str, object]], variations: dict[int, list[dict[str, object]]] | None = None) -> None:
        self.products = products
        self.variations = variations or {}

    def iter_products(self):
        yield from self.products

    def iter_product_variations(self, parent_id: int):
        yield from self.variations.get(parent_id, [])


def product(
    woo_id: int,
    name: str,
    *,
    sku: str = "",
    kind: str = "variable",
    status: str = "publish",
    visibility: str = "visible",
    categories: list[str] | None = None,
) -> dict[str, object]:
    return {
        "id": woo_id,
        "sku": sku,
        "name": name,
        "slug": name.lower().replace(" ", "-"),
        "type": kind,
        "status": status,
        "catalog_visibility": visibility,
        "date_created": "2019-01-01T00:00:00",
        "date_modified": "2026-08-08T00:00:00",
        "regular_price": "99.00",
        "sale_price": "",
        "price": "99.00",
        "attributes": [],
        "categories": [{"name": value} for value in categories or []],
        "images": [],
    }


def variation(
    woo_id: int,
    parent_id: int,
    *,
    sku: str = "",
    size: str = "",
    color: str = "",
    extra_sku: str = "",
) -> dict[str, object]:
    attributes = []
    if size:
        attributes.append({"name": "Tamano", "option": size})
    if color:
        attributes.append({"name": "Color", "option": color})
    return {
        "id": woo_id,
        "parent_id": parent_id,
        "sku": extra_sku or sku,
        "name": "",
        "status": "publish",
        "catalog_visibility": "visible",
        "date_created": "2022-01-01T00:00:00",
        "date_modified": "2026-08-08T00:00:00",
        "regular_price": "99.00",
        "sale_price": "",
        "price": "99.00",
        "attributes": attributes,
        "images": [],
    }


def review(code: str, item_id: str, **overrides: str) -> dict[str, str]:
    row = {
        "codigo": code,
        "item_id": item_id,
        "name": "Futon Basic 90x200 Natural",
        "family": "Futones",
        "filter_group": "Basic",
        "filter_size": "90x200",
        "filter_gama": "Natural",
        "item_record_type": "simple",
        "is_pack": "false",
    }
    row.update(overrides)
    return row


def research(row: dict[str, str], kind: str, woo_id: int, parent_id: int | str = "") -> dict[str, str]:
    return {
        "item_id": row["item_id"],
        "codigo": row["codigo"],
        "candidate_kind": kind,
        "candidate_woo_id": str(woo_id),
        "candidate_parent_woo_id": str(parent_id),
    }


def run(
    rows: list[dict[str, str]],
    research_rows: list[dict[str, str]],
    products: list[dict[str, object]],
    variations: dict[int, list[dict[str, object]]] | None = None,
    safe_rows: list[dict[str, str]] | None = None,
) -> dict[str, object]:
    index = build_woo_read_only_index(ReadOnlyWoo(products, variations))
    return deep_review(rows, research_rows, safe_rows or [], woo_index=index)


class WooMap001A6DeepReviewTests(unittest.TestCase):
    def test_sumatra_is_always_retired_confirmed_by_user(self) -> None:
        result = run([review("406006", "406006", name="Cama Sumatra 160x200 Natural", family="Camas", filter_group="Cama Sumatra", filter_size="160x200")], [], [])
        self.assertEqual(result["decisions"][0]["decision_status"], "RETIRED_CONFIRMED_BY_USER")

    def test_chalet_is_always_retired_confirmed_by_user(self) -> None:
        result = run([review("0404017", "404017", name="Cama Chalet Brus 160x200 Natural", family="Camas", filter_group="Chalet Brus", filter_size="160x200")], [], [])
        self.assertEqual(result["decisions"][0]["decision_status"], "RETIRED_CONFIRMED_BY_USER")

    def test_retired_is_not_safe_or_price_eligible(self) -> None:
        row = review("406006", "406006", name="Cama Sumatra 160x200 Natural", family="Camas", filter_group="Cama Sumatra", filter_size="160x200")
        result = run([row], [], [])
        human = result["human_rows"][0]
        self.assertEqual(human["current_commercial_eligibility"], "NO")
        self.assertEqual(human["price_change_eligible"], "NO")
        self.assertNotIn(human["decision_status"], {"READY_SAFE_AFTER_DEEP_REVIEW", "READY_USER_APPROVAL_SINGLE"})

    def test_retired_can_keep_historical_woo_evidence(self) -> None:
        row = review("406006", "406006", name="Cama Sumatra 160x200 Natural", family="Camas", filter_group="Cama Sumatra", filter_size="160x200", filter_gama="NO_GAMA")
        result = run([row], [research(row, "product", 3617)], [product(3617, "Cama Sumatra")])
        human = result["human_rows"][0]
        self.assertEqual(human["historical_woo_entity"], "YES")
        self.assertEqual(human["recommended_action"], "KEEP_HISTORY_ONLY")

    def test_hidden_product_is_not_automatically_retired(self) -> None:
        row = review("BASIC-HIDDEN", "1", filter_gama="NO_GAMA")
        result = run([row], [research(row, "product", 10)], [product(10, "Futon Basic 90x200", kind="simple", visibility="hidden")])
        self.assertEqual(result["decisions"][0]["decision_status"], "POSSIBLE_RETIRED_OR_LEGACY_ENTITY")

    def test_leading_zero_duo_code_is_not_promoted_when_woo_is_claimed(self) -> None:
        row = review("0078009", "78009", name="Duo Latex 140x200x16", filter_group="Duo Latex", filter_size="140x200x16", filter_gama="NO_GAMA")
        safe = {"codigo": "0780009", "woo_id": "11043", "woo_sku": "0780009"}
        result = run([row], [research(row, "variation", 11043, 11038)], [product(11038, "Futon Duo Latex")], {11038: [variation(11043, 11038, sku="0780009", size="140x200x16")]}, [safe])
        self.assertEqual(result["decisions"][0]["decision_status"], "PHYSICAL_IDENTITY_DUPLICATE_OR_LEGACY_REVIEW")

    def test_correct_tatami_set_parent_can_be_ready_safe(self) -> None:
        row = review("0201013", "201013", name="Tatami Plegable + Futon Portatil Azul", family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Azul")
        result = run([row], [research(row, "variation", 4556, 3657)], [product(3657, "Tatami plegable y futon portatil")], {3657: [variation(4556, 3657, size="90x200x1,2", color="Azul", extra_sku="0201011|0809001")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "READY_SAFE_AFTER_DEEP_REVIEW")

    def test_tatami_set_can_use_its_explicit_parent_description_dimension(self) -> None:
        row = review("0208001", "208001", name="Tatami Plegable + Futon Portatil Crudo", family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Crudo")
        parent = product(3657, "Tatami plegable y futon portatil")
        parent["description"] = "El tatami plegable mide 90x200x1,2 cm y el futon portatil varia por color."
        result = run([row], [research(row, "variation", 4558, 3657)], [parent], {3657: [variation(4558, 3657, color="Crudo", extra_sku="0201011|0808001")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "READY_SAFE_AFTER_DEEP_REVIEW")

    def test_wrong_tatami_parent_is_rejected(self) -> None:
        row = review("0201013", "201013", name="Tatami Plegable + Futon Portatil Azul", family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Azul")
        result = run([row], [research(row, "variation", 4555, 3656)], [product(3656, "Tatami plegable")], {3656: [variation(4555, 3656, size="90x200x1,2", color="Azul")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "NO_MATCH_AFTER_DEEP_REVIEW")
        self.assertIn("WRONG_PARENT", result["human_rows"][0]["evidence_against"])

    def test_size_mismatch_is_not_promoted(self) -> None:
        row = review("0780002", "780002", name="Futon Lana 120x200x14", filter_group="Lana", filter_size="120x200x14", filter_gama="NO_GAMA")
        result = run([row], [research(row, "variation", 3886, 3640)], [product(3640, "Futon de lana")], {3640: [variation(3886, 3640, size="120x200x14,5")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "NO_MATCH_AFTER_DEEP_REVIEW")
        self.assertIn("SIZE_MISMATCH", result["human_rows"][0]["evidence_against"])

    def test_colour_mismatch_does_not_treat_verde_as_verde_oscuro(self) -> None:
        row = review("0214001", "214001", name="Tatami Plegable + Futon Portatil Verde", family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Verde")
        result = run([row], [research(row, "variation", 4559, 3657)], [product(3657, "Tatami plegable y futon portatil")], {3657: [variation(4559, 3657, size="90x200x1,2", color="Verde oscuro")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "NO_MATCH_AFTER_DEEP_REVIEW")
        self.assertIn("COLOR_MISMATCH", result["human_rows"][0]["evidence_against"])

    def test_outlet_candidate_is_rejected_as_current_equivalent(self) -> None:
        row = review("0758087", "758087", name="Futon Premium 120x200x17", filter_group="Premium", filter_size="120x200x17", filter_gama="NO_GAMA")
        result = run([row], [research(row, "product", 10448)], [product(10448, "Futon Premium OUTLET 120x200x17", kind="simple")])
        self.assertIn("OUTLET_HISTORICAL_MISMATCH", result["human_rows"][0]["evidence_against"])

    def test_pack_instead_of_direct_is_rejected(self) -> None:
        row = review("0504015", "504015", name="Sofa cama Luna 120x200 Natural", family="Sofas Cama", filter_group="Luna", filter_size="120x200", filter_gama="Natural")
        result = run([row], [research(row, "variation", 4001, 3648)], [product(3648, "Sofa cama Luna")], {3648: [variation(4001, 3648, size="120x200", color="Natural", extra_sku="0504010|0724001")]})
        self.assertIn("PACK_INSTEAD_OF_DIRECT", result["human_rows"][0]["evidence_against"])

    def test_cama_macao_is_not_base_tatami_macao(self) -> None:
        row = review("0402014", "402014", name="Cama Macao 180x200 Natural", family="Camas", filter_group="Macao", filter_size="180x200", filter_gama="NO_GAMA")
        result = run([row], [research(row, "product", 3610)], [product(3610, "Base para tatami Macao 180x200", kind="simple")])
        self.assertEqual(result["decisions"][0]["decision_status"], "WOO_CATALOG_INCONSISTENCY")
        self.assertIn("WRONG_PRODUCT_KIND", result["human_rows"][0]["evidence_against"])

    def test_tatami_pledged_only_parent_is_not_set(self) -> None:
        row = review("0208001", "208001", name="Tatami Plegable + Futon Portatil Crudo", family="Tatamis", filter_group="Tatami plegable", filter_size="90x200x1,2", filter_gama="Crudo")
        result = run([row], [research(row, "variation", 4555, 3656)], [product(3656, "Tatami plegable")], {3656: [variation(4555, 3656, size="90x200x1,2", color="Crudo")]})
        self.assertIn("WRONG_PARENT", result["human_rows"][0]["evidence_against"])

    def test_fourteen_never_equals_fourteen_point_five(self) -> None:
        row = review("0780007", "780007", name="Futon Lana 200x200x14", filter_group="Lana", filter_size="200x200x14", filter_gama="NO_GAMA")
        result = run([row], [research(row, "variation", 3891, 3640)], [product(3640, "Futon de lana")], {3640: [variation(3891, 3640, size="200x200x14,5")]})
        self.assertNotIn(result["decisions"][0]["decision_status"], {"READY_SAFE_AFTER_DEEP_REVIEW", "READY_USER_APPROVAL_SINGLE"})

    def test_parent_option_list_does_not_prove_a_different_variation_size(self) -> None:
        row = review("SIZE-CHILD", "776", filter_gama="NO_GAMA", filter_size="140x200")
        parent = product(20, "Futon Basic")
        parent["attributes"] = [{"name": "Tamano", "options": ["90x200", "140x200"]}]
        result = run([row], [research(row, "variation", 21, 20)], [parent], {20: [variation(21, 20, size="90x200")]})
        self.assertEqual(result["decisions"][0]["decision_status"], "NO_MATCH_AFTER_DEEP_REVIEW")
        self.assertIn("SIZE_MISMATCH", result["human_rows"][0]["evidence_against"])

    def test_name_similarity_without_research_candidate_never_promotes(self) -> None:
        row = review("NO-FUZZY", "777", name="Futon Basic 90x200 Natural")
        result = run([row], [], [product(77, "Futon Basic 90x200 Natural", kind="simple")])
        self.assertEqual(result["decisions"][0]["decision_status"], "NO_DIRECT_WOO_ENTITY_SUPPORTED")

    def test_human_output_is_capped_at_three_candidates(self) -> None:
        row = review("BASIC-4", "4", filter_gama="NO_GAMA")
        products = [product(20, "Futon Basic")]
        variations = {20: [variation(21 + index, 20, size="90x200") for index in range(4)]}
        result = run([row], [research(row, "variation", 21 + index, 20) for index in range(4)], products, variations)
        self.assertEqual(len(result["human_rows"]), 3)
        self.assertEqual(result["decisions"][0]["decision_status"], "MULTIPLE_REAL_CANDIDATES")

    def test_service_has_no_write_path(self) -> None:
        source = inspect.getsource(deep_review)
        for forbidden in (".put(", ".post(", ".update(", ".insert(", ".delete("):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
