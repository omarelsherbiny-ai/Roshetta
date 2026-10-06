# tests/test_emergency_routing.py
"""Session 126 emergency fixes: a new product goes to the agent, and a sell-price phrase is not a sale."""
import unittest

from agents.agents.intake import _asks_sales_today, _is_sale_request, intake_agent
from server.app.services.agent_routing import should_use_agent

KW = dict(tools_enabled=True, can_view_inventory=True, can_view_reports=True, is_cashier=False)


class NewProductRoutingTests(unittest.TestCase):
    def test_new_product_goes_to_the_agent_even_with_a_local_card(self):
        self.assertTrue(should_use_agent("create_product", local_card_missing=False, **KW))

    def test_new_product_goes_to_the_agent_when_the_local_card_is_missing(self):
        self.assertTrue(should_use_agent("create_product", local_card_missing=True, **KW))

    def test_denied_new_product_stays_local(self):
        self.assertFalse(should_use_agent("create_product", write_denied=True, **KW))

    def test_tools_off_keeps_everything_local(self):
        kw = dict(KW, tools_enabled=False)
        self.assertFalse(should_use_agent("create_product", **kw))
        self.assertFalse(should_use_agent("log_restock", **kw))

    def test_sale_and_expense_stay_local(self):
        self.assertFalse(should_use_agent("log_sale", **KW))
        self.assertFalse(should_use_agent("log_expense", **KW))

    def test_restock_still_goes_to_the_agent(self):
        self.assertTrue(should_use_agent("log_restock", **KW))


class SellPricePhraseTests(unittest.TestCase):
    def test_price_phrases_are_not_sales(self):
        for text in ["اضبط سعر بيع بنادول 20", "خلي بسعر بيع 25 للبنادول", "set sell price of aa to 20",
                     "sale price 30 for aa", "غير سعر بيع aa ل 12"]:
            with self.subTest(text=text):
                self.assertFalse(_is_sale_request(text.lower()))

    def test_real_sales_still_count(self):
        for text in ["بعت 2 بنادول", "سجل بيع 3 بنادول", "sold 2 panadol", "بيع 3 بنادول"]:
            with self.subTest(text=text):
                self.assertTrue(_is_sale_request(text.lower()))

    def test_price_phrase_does_not_make_a_sales_question(self):
        self.assertFalse(_asks_sales_today("كام سعر بيع بنادول النهاردة"))

    def test_sell_price_message_is_not_log_sale(self):
        out = intake_agent({"user_query": "غير سعر بيع aa ل 12", "language": "ar"})
        self.assertNotEqual(out["intent"], "log_sale")


if __name__ == "__main__":
    unittest.main()