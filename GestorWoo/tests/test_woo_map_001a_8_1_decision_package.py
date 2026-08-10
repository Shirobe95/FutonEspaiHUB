from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))

from auditoria.woo_map_001a_8_1_decision_package import missing_classification


class WooMap001A81DecisionPackageTests(unittest.TestCase):
    def test_historical_signal_stays_business_confirmation(self) -> None:
        evidence, cause, category, action = missing_classification([{
            "historical_signals": "OUTLET", "rejection_reason": "", "family_gate": "PASS",
            "model_gate": "MODEL_GATE_PASS", "kind_gate": "PASS",
        }])
        self.assertEqual(evidence, "HISTORICAL_WOO_SIGNAL_WITHOUT_SAFE_DIRECT_ENTITY")
        self.assertEqual(cause, "LIKELY_LEGACY_PRODUCT")
        self.assertEqual(category, "NEEDS_BUSINESS_CONFIRMATION")
        self.assertIn("Confirm", action)

    def test_unqualified_historical_noise_does_not_make_a_legacy_claim(self) -> None:
        evidence, cause, _category, _action = missing_classification([{
            "historical_signals": "OUTLET", "rejection_reason": "FAMILY_GATE_FAIL", "family_gate": "FAIL",
            "model_gate": "MODEL_GATE_FAIL", "kind_gate": "PASS",
        }])
        self.assertEqual(evidence, "NO_COMPATIBLE_DIRECT_ENTITY_AFTER_FAMILY_OR_MODEL_GATE")
        self.assertEqual(cause, "LIKELY_CATALOG_GAP")

    def test_strict_model_or_family_failure_never_becomes_relation(self) -> None:
        evidence, cause, category, _action = missing_classification([{"family_gate": "FAIL", "model_gate": "MODEL_GATE_FAIL", "rejection_reason": "FAMILY_GATE_FAIL"}])
        self.assertEqual(evidence, "NO_COMPATIBLE_DIRECT_ENTITY_AFTER_FAMILY_OR_MODEL_GATE")
        self.assertEqual(cause, "LIKELY_CATALOG_GAP")
        self.assertEqual(category, "NEEDS_BUSINESS_CONFIRMATION")

    def test_size_or_variant_gate_is_not_auto_equivalence(self) -> None:
        evidence, cause, category, _action = missing_classification([{"family_gate": "PASS", "model_gate": "MODEL_GATE_PASS", "kind_gate": "PASS"}])
        self.assertEqual(evidence, "DIRECT_ENTITY_FAILED_SIZE_OR_VARIANT_GATE")
        self.assertEqual(cause, "LIKELY_CATALOG_GAP")
        self.assertEqual(category, "NEEDS_BUSINESS_CONFIRMATION")


if __name__ == "__main__":
    unittest.main()
