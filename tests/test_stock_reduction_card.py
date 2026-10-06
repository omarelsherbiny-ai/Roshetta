# tests/test_stock_reduction_card.py
"""Pure builder of the reduce-stock card (Session 126). No database, no server."""
import unittest

from agents.agents.verification import build_stock_reduction_proposal

PRODUCT = {"id": 7, "name_ar": "اي اي", "name_en": "aa", "stock_qty": 12}


class StockReductionCardTests(unittest.TestCase):
    def test_a_lower_count_makes_a_card_without_lines_or_money(self):
        card = build_stock_reduction_proposal(PRODUCT, 8, None, "en")
        self.assertEqual(card["action_type"], "reduce_stock")
        self.assertEqual(card["items"], [])
        self.assertEqual(card["total_amount"], 0.0)
        self.assertEqual(card["target_item_id"], 7)
        self.assertEqual(card["stock_change"], {"item_name": "aa", "before": 12.0, "after": 8.0, "difference": 4.0, "reason": None})
        self.assertEqual(card["status"], "pending_confirmation")
        self.assertTrue(card["warnings"])

    def test_arabic_card_uses_the_arabic_name(self):
        card = build_stock_reduction_proposal(PRODUCT, 8, None, "ar")
        self.assertEqual(card["stock_change"]["item_name"], "اي اي")

    def test_same_higher_negative_or_bad_counts_make_no_card(self):
        for value in (12, 13, -1, "x", None, float("nan")):
            self.assertIsNone(build_stock_reduction_proposal(PRODUCT, value, None, "en"), value)

    def test_zero_is_allowed(self):
        self.assertEqual(build_stock_reduction_proposal(PRODUCT, 0, None, "en")["stock_change"]["after"], 0.0)

    def test_reason_is_trimmed_and_cut(self):
        card = build_stock_reduction_proposal(PRODUCT, 8, "  damaged   in   transit " + "x" * 200, "en")
        self.assertTrue(card["stock_change"]["reason"].startswith("damaged in transit"))
        self.assertLessEqual(len(card["stock_change"]["reason"]), 100)

    def test_each_card_has_its_own_id(self):
        first = build_stock_reduction_proposal(PRODUCT, 8, None, "en")
        second = build_stock_reduction_proposal(PRODUCT, 8, None, "en")
        self.assertNotEqual(first["id"], second["id"])


if __name__ == "__main__":
    unittest.main()