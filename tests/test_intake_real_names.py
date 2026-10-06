# tests/test_intake_real_names.py
import unittest

from agents.agents.intake import extract_product_name, intake_agent
from agents.agents.verification import verification_agent

INVENTORY = [
    {
        "id": 1, "name_ar": "بنادول اكسترا", "name_en": "Panadol Extra", "stock_qty": 20.0,
        "unit_sell_price": 40.0, "unit_buy_price": 30.0,
        "price_batches": [{"quantity": 20.0, "unit_sell_price": 40.0}],
    },
    {
        "id": 2, "name_ar": "بروفين", "name_en": "Brufen", "stock_qty": 5.0,
        "unit_sell_price": 25.0, "unit_buy_price": 18.0,
        "price_batches": [{"quantity": 5.0, "unit_sell_price": 25.0}],
    },
    {
        "id": 3, "name_ar": "بنادول ازرق", "name_en": "Panadol Blue", "stock_qty": 9.0,
        "unit_sell_price": 28.0, "unit_buy_price": 20.0,
        "price_batches": [{"quantity": 9.0, "unit_sell_price": 28.0}],
    },
]


def run(text: str, language: str = "en") -> dict:
    state = {"user_query": text, "language": language, "inventory_data": INVENTORY}
    return verification_agent(intake_agent(state))


class RealNamesTests(unittest.TestCase):
    def test_name_extraction(self):
        self.assertEqual(extract_product_name("sold 3 brufen today"), "brufen")
        self.assertEqual(extract_product_name("بعت 3 علب بروفين بسعر 30"), "بروفين")
        self.assertEqual(extract_product_name("restock brufen 10 for 15 egp"), "brufen")
        self.assertEqual(extract_product_name("sold 3"), "")

    def test_sale_priced_from_the_catalog_not_a_made_up_price(self):
        result = run("sold 2 Brufen")
        item = result["proposal"]["items"][0]
        self.assertEqual(item["item_name"], "بروفين")
        self.assertEqual(item["unit_price"], 25.0)
        self.assertEqual(result["proposal"]["total_amount"], 50.0)

    def test_one_close_spelling_resolves_to_the_real_product(self):
        result = run("sold 1 brufn")
        self.assertEqual(result["proposal"]["items"][0]["matched_inventory_id"], 2)

    def test_several_candidates_are_not_guessed(self):
        result = run("sold 1 panadol")
        self.assertIsNone(result["proposal"])
        self.assertIn("Did you mean", result["answer_text"])

    def test_unknown_product_is_refused_without_inventing_one(self):
        result = run("sold 1 zzzzzz")
        self.assertIsNone(result["proposal"])

    def test_missing_name_asks(self):
        result = run("sold 3")
        self.assertIsNone(result["proposal"])
        self.assertIn("Which product", result["answer_text"])

    def test_restock_uses_catalog_buy_price(self):
        result = run("restock brufen 10")
        self.assertEqual(result["proposal"]["items"][0]["unit_price"], 18.0)


if __name__ == "__main__":
    unittest.main()