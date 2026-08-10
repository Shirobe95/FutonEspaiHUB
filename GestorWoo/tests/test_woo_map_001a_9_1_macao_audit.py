from __future__ import annotations

import sys
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "auditoria"))

from woo_map_001a_9_1_macao_audit import (  # noqa: E402
    FORBIDDEN_SHARED_WOO_ID,
    MACAO_SKU,
    classify_macao_relation,
)


def physical(code: str, item_id: str, woo_id: str = "") -> dict[str, str]:
    return {
        "item_id": item_id,
        "heca_reference": code,
        "hub_item_code": code,
        "woo_id": woo_id,
        "item_record_type": "simple",
        "is_pack": "false",
        "family": "Bases para Tatamis",
        "filter_family": "Bases para Tatamis",
        "filter_group": "Macao",
        "filter_size": "180x200",
        "filter_gama": "Natural",
    }


def candidate(*, sku: str, status: str = "publish", valid: bool = True, woo_id: str = "9999") -> dict[str, str]:
    return {
        "woo_id": woo_id,
        "parent_woo_id": "9000",
        "kind": "variation",
        "status": status,
        "sku": sku,
        "literal_sku_exact": "YES" if sku == MACAO_SKU else "NO",
        "model_exact": "YES" if valid else "NO",
        "kind_exact": "YES" if valid else "NO",
        "size_exact": "YES" if valid else "NO",
        "gama_exact": "YES" if valid else "NO",
        "excluded_reason": "",
    }


class WooMap001A91MacaoAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.macao = physical(MACAO_SKU, "402014")
        self.existing = physical("0302009", "302009", FORBIDDEN_SHARED_WOO_ID)

    def test_0402014_and_0302009_are_never_shareable(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [candidate(sku="0302009", woo_id=FORBIDDEN_SHARED_WOO_ID)])
        self.assertEqual("NO_DIRECT_WOO_ENTITY", result["classification"])
        self.assertEqual("NO", result["price_change_eligible"])

    def test_exact_publish_entity_is_eligible(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [candidate(sku=MACAO_SKU)])
        self.assertEqual("EXACT_EXISTING_WOO_ENTITY", result["classification"])
        self.assertEqual("YES", result["price_change_eligible"])

    def test_private_exact_entity_is_not_price_eligible(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [candidate(sku=MACAO_SKU, status="private")])
        self.assertEqual("EXACT_HISTORICAL_OR_PRIVATE_ENTITY", result["classification"])
        self.assertEqual("NO", result["price_change_eligible"])

    def test_literal_sku_with_invariant_mismatch_is_conflict(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [candidate(sku=MACAO_SKU, valid=False)])
        self.assertEqual("IDENTITY_CONFLICT", result["classification"])

    def test_multiple_exact_entities_are_dual_target_conflict(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [candidate(sku=MACAO_SKU, woo_id="9001"), candidate(sku=MACAO_SKU, woo_id="9002")])
        self.assertEqual("IDENTITY_CONFLICT", result["classification"])

    def test_no_exact_entity_keeps_macao_unlinked(self) -> None:
        result = classify_macao_relation(self.macao, self.existing, [])
        self.assertEqual("NO_DIRECT_WOO_ENTITY", result["classification"])
        self.assertEqual("NO", result["price_change_eligible"])

    def test_audit_has_no_fuzzy_or_mutation_client_path(self) -> None:
        source = (ROOT / "auditoria" / "woo_map_001a_9_1_macao_audit.py").read_text(encoding="utf-8")
        self.assertNotIn("rapidfuzz", source)
        self.assertNotIn("difflib", source)
        self.assertNotIn("woo_client.put(", source)
        self.assertNotIn(".table(\"inventory_items\").update(", source)


if __name__ == "__main__":
    unittest.main()
