# tests/test_inventory_prefetch.py
import unittest

from agents.agents.intake import intake_agent
from server.app.services.inventory_prefetch import (
    MAX_ALL_ROWS,
    build_inventory_question,
    prefetch_mode,
)


def _item(i, stock=5, floor=2, cat="Pain", buy=3.0):
    return {
        "id": i, "name_ar": f"دواء {i}", "name_en": f"Drug {i:03d}", "stock_qty": stock,
        "min_threshold": floor, "unit_sell_price": 12.5, "unit_buy_price": buy,
        "price_batches": [{"quantity": 1, "unit_sell_price": 9.0}], "category": cat,
    }


class IntakeInventoryWords(unittest.TestCase):
    def intent(self, text):
        return intake_agent({"user_query": text, "language": "en"})["intent"]

    def test_inventory_reads_are_query_stock(self):
        for text in (
            "give me all in inventory",
            "retrieve all products in inventory",
            "i need to retieve all inventory products",
            "what products do I have",
            "show inventory",
            "اعرض المنتجات",
            "وريني المخزن",
        ):
            self.assertEqual(self.intent(text), "query_stock", text)

    def test_writes_are_not_stolen(self):
        self.assertNotEqual(self.intent("add a new product panadol to inventory"), "query_stock")
        self.assertNotEqual(self.intent("edit the product pharma to be category is test"), "query_stock")
        self.assertNotEqual(self.intent("change the category of antinal_2 to test, all products"), "query_stock")
        self.assertEqual(self.intent("add 5 panadol to inventory"), "log_restock")

    def test_old_behaviour_kept(self):
        self.assertEqual(self.intent("low stock"), "query_stock")
        self.assertEqual(self.intent("Show today's summary"), "query_finance")
        self.assertEqual(self.intent("hello"), "general_chat")


class PrefetchMode(unittest.TestCase):
    def test_modes(self):
        self.assertEqual(prefetch_mode("give me all in inventory"), "all")
        self.assertEqual(prefetch_mode("stock summary"), "all")
        self.assertEqual(prefetch_mode("low stock"), "low")
        self.assertEqual(prefetch_mode("نواقص"), "low")
        self.assertEqual(prefetch_mode("what is out of stock"), "low")

    def test_specific_questions_keep_the_tools(self):
        self.assertIsNone(prefetch_mode("how much panadol stock do we have"))
        self.assertIsNone(prefetch_mode("show product 8"))
        self.assertIsNone(prefetch_mode("alternative for panadol in stock"))
        self.assertIsNone(prefetch_mode("بديل بنادول في المخزن"))
        self.assertIsNone(prefetch_mode("hello"))


class BuildQuestion(unittest.TestCase):
    def test_all_lists_every_product_in_the_answer_language(self):
        q = build_inventory_question("show all", "Arabic", [_item(1), _item(2)], "ar", "all")
        self.assertIn("1. دواء 1 | category: Pain | stock: 5 | sell price: 12.5 EGP", q)
        self.assertIn("2. دواء 2", q)
        self.assertIn("Answer in Arabic.", q)
        self.assertIn("All products: 2", q)

    def test_nothing_private_leaves(self):
        q = build_inventory_question("show all", "English", [_item(7, buy=3.0)], "en", "all")
        self.assertNotIn("buy", q.lower())
        self.assertNotIn("price_batches", q)
        self.assertNotIn("id", [w for w in q.split() if w == "id"])
        self.assertNotIn("| 7 |", q)
        self.assertNotIn("9.0", q)  # a batch price

    def test_low_keeps_only_products_at_or_below_the_minimum(self):
        items = [_item(1, stock=5, floor=2), _item(2, stock=2, floor=2), _item(3, stock=0, floor=0)]
        q = build_inventory_question("low stock", "English", items, "en", "low")
        self.assertNotIn("Drug 001", q)
        self.assertIn("Drug 002", q)
        self.assertIn("Drug 003", q)
        self.assertIn("2 of 3 products", q)

    def test_low_with_no_rows_says_so(self):
        q = build_inventory_question("low stock", "English", [_item(1)], "en", "low")
        self.assertIn("no rows", q)

    def test_big_inventory_goes_back_to_the_tools_for_all(self):
        items = [_item(i) for i in range(MAX_ALL_ROWS + 1)]
        self.assertIsNone(build_inventory_question("show all", "English", items, "en", "all"))
        self.assertIsNotNone(build_inventory_question("show all", "English", items[:MAX_ALL_ROWS], "en", "all"))

    def test_long_low_list_is_cut_and_says_so(self):
        items = [_item(i, stock=0, floor=1) for i in range(100)]
        q = build_inventory_question("low stock", "English", items, "en", "low")
        self.assertIn("100 of 100", q)
        self.assertIn("60 more are not shown", q)

    def test_missing_names_and_numbers_do_not_crash(self):
        q = build_inventory_question("x", "English", [{"stock_qty": None, "name_ar": None, "name_en": "A"}], "ar", "all")
        self.assertIn("1. A | category: - | stock: 0 | sell price: 0 EGP", q)


if __name__ == "__main__":
    unittest.main()