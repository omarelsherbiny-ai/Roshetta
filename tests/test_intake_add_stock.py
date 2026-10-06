# tests/test_intake_add_stock.py
import unittest

from agents.agents.intake import _parse_add_stock, intake_agent


def run(text: str) -> dict:
    return intake_agent({"user_query": text, "language": "en"})


class AddStockIntentTests(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(_parse_add_stock("add for panadol 5 items"), ("panadol", 5.0))
        self.assertEqual(_parse_add_stock("add 5 panadol"), ("panadol", 5.0))
        self.assertEqual(_parse_add_stock("زود بنادول ١٠"), ("بنادول", 10.0))
        self.assertIsNone(_parse_add_stock("add panadol"))
        self.assertIsNone(_parse_add_stock("this is an address 5"))
        self.assertIsNone(_parse_add_stock("add 5"))

    def test_add_to_existing_is_a_restock(self):
        result = run("add for panadol 5 items")
        self.assertEqual(result["intent"], "log_restock")
        self.assertEqual(result["extracted_items"][0]["item_name"], "panadol")
        self.assertEqual(result["extracted_items"][0]["quantity"], 5.0)

    def test_other_intents_unchanged(self):
        self.assertEqual(run("how many i sell today")["intent"], "query_finance")
        self.assertEqual(run("show low stock")["intent"], "query_stock")
        self.assertEqual(run("add expense electricity 100")["intent"], "log_expense")
        self.assertEqual(run("hello there")["intent"], "general_chat")


if __name__ == "__main__":
    unittest.main()