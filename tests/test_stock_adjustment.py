# tests/test_stock_adjustment.py
import unittest

from agents.agents.stock_adjustment import build_stock_adjustment_proposal, clean_reason

PANADOL = {"id": 8, "name_ar": "بنادول", "name_en": "Panadol", "stock_qty": 5.0, "unit_buy_price": 10.0}


class StockAdjustmentCardTests(unittest.TestCase):
    def test_new_stock_works_out_the_difference(self):
        card = build_stock_adjustment_proposal(PANADOL, new_stock=15, language="en")
        adj = card["adjustment"]
        self.assertEqual((adj["stock_before"], adj["stock_after"], adj["stock_change"]), (5.0, 15.0, 10.0))
        self.assertEqual(card["action_type"], "adjust_stock")
        self.assertEqual(card["target_item_id"], 8)
        self.assertEqual(card["items"], [])
        self.assertEqual(card["status"], "pending_confirmation")

    def test_change_adds_to_the_stock_now(self):
        card = build_stock_adjustment_proposal(PANADOL, change=10)
        self.assertEqual(card["adjustment"]["stock_after"], 15.0)

    def test_decrease_needs_a_reason(self):
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, new_stock=2))
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, change=-3, reason="   "))
        card = build_stock_adjustment_proposal(PANADOL, change=-3, reason="  damaged   boxes ", language="en")
        self.assertEqual(card["adjustment"]["stock_after"], 2.0)
        self.assertEqual(card["adjustment"]["reason"], "damaged boxes")
        self.assertTrue(any("without a sale" in w for w in card["warnings"]))

    def test_refuses_bad_input(self):
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL))                       # neither
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, new_stock=1, change=1))  # both
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, new_stock=5))          # no change
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, change=-9, reason="x"))  # below zero
        self.assertIsNone(build_stock_adjustment_proposal(PANADOL, new_stock=2_000_000))  # above limit
        self.assertIsNone(build_stock_adjustment_proposal({**PANADOL, "id": None}, new_stock=9))

    def test_zero_stock_warns_out_of_stock(self):
        card = build_stock_adjustment_proposal(PANADOL, new_stock=0, reason="stocktake", language="en")
        self.assertTrue(any("out of stock" in w for w in card["warnings"]))

    def test_increase_warns_no_purchase_and_missing_buy_price(self):
        card = build_stock_adjustment_proposal({**PANADOL, "unit_buy_price": 0.0}, new_stock=9, language="en")
        self.assertTrue(any("without recording a purchase" in w for w in card["warnings"]))
        self.assertTrue(any("no buy price" in w for w in card["warnings"]))
        with_price = build_stock_adjustment_proposal(PANADOL, new_stock=9, language="en")
        self.assertFalse(any("no buy price" in w for w in with_price["warnings"]))

    def test_arabic_and_english_text_and_no_buy_price_in_card(self):
        ar = build_stock_adjustment_proposal(PANADOL, new_stock=15, language="ar")
        en = build_stock_adjustment_proposal(PANADOL, new_stock=15, language="en")
        self.assertIn("بنادول", ar["summary_ar"])
        self.assertIn("Panadol", en["summary_en"])
        self.assertNotIn("unit_buy_price", str(ar))

    def test_float_drift_is_rounded(self):
        card = build_stock_adjustment_proposal({**PANADOL, "stock_qty": 0.1}, change=0.2)
        self.assertEqual(card["adjustment"]["stock_after"], 0.3)

    def test_clean_reason(self):
        self.assertEqual(clean_reason(None), "")
        self.assertEqual(len(clean_reason("x" * 500)), 200)


if __name__ == "__main__":
    unittest.main()