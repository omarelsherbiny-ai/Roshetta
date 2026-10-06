# tests/test_product_card_warnings.py
import unittest

from agents.agents.verification import _create_product_proposal

INVENTORY = [
    {"id": 1, "name_ar": "Panadol", "name_en": "Panadol", "stock_qty": 4, "unit_sell_price": 10, "category": "Pain"},
    {"id": 2, "name_ar": "Cetal", "name_en": "Cetal", "stock_qty": 1, "unit_sell_price": 8, "category": None},
]


def card(draft, language="en", inventory=INVENTORY):
    state = {"language": language, "product_draft": draft, "inventory_data": inventory}
    return _create_product_proposal(state)["proposal"]


class ProductCardWarnings(unittest.TestCase):
    def test_missing_buy_price_and_category_both_warn(self):
        warnings = card({"name": "Zinc", "unit_sell_price": 20})["warnings"]
        self.assertTrue(any("buy price" in w for w in warnings))
        self.assertIn("No category was given.", warnings)

    def test_known_category_gives_no_category_warning(self):
        warnings = card({"name": "Zinc", "unit_buy_price": 10, "unit_sell_price": 20, "category": "pain"})["warnings"]
        self.assertEqual(warnings, [])

    def test_unknown_category_warns_it_will_be_created(self):
        warnings = card({"name": "Zinc", "unit_buy_price": 10, "unit_sell_price": 20, "category": "Vitamins"})["warnings"]
        self.assertEqual(len(warnings), 1)
        self.assertIn("Vitamins", warnings[0])

    def test_category_text_is_stripped_and_kept(self):
        proposal = card({"name": "Zinc", "unit_buy_price": 10, "unit_sell_price": 20, "category": "  Pain "})
        self.assertEqual(proposal["product"]["category"], "Pain")
        self.assertEqual(proposal["warnings"], [])

    def test_arabic_warnings(self):
        warnings = card({"name": "زنك", "unit_sell_price": 20}, language="ar")["warnings"]
        self.assertIn("لم يتم تحديد القسم.", warnings)

    def test_missing_name_or_sell_price_gives_no_card(self):
        for draft in ({"unit_sell_price": 5}, {"name": "Zinc"}):
            self.assertIsNone(card(draft))


if __name__ == "__main__":
    unittest.main()