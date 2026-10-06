# tests/test_intake_read_requests.py
import unittest

from agents.agents.intake import intake_agent


def intent_of(text):
    return intake_agent({"user_query": text, "language": "en"})["intent"]


class ReadRequestsAreNotSales(unittest.TestCase):
    def test_show_requests_are_not_sales(self):
        for text in (
            "show sales this week",
            "show me the sale records",
            "list what we sold",
            "show items sold",
            "طلعلي كل المنتجات",
            "اعرض المبيعات",
            "غير سعر البيع",
        ):
            self.assertNotEqual(intent_of(text), "log_sale", text)

    def test_real_sales_still_log(self):
        for text in (
            "sold 2 panadol",
            "sold panadol",
            "log sale 3 panadol",
            "بعت 2 بنادول",
            "بعت علبتين بنادول",
            "بيع 2 بنادول",
            "طلع 3 بنادول",
            "سجل بيع بنادول",
        ):
            self.assertEqual(intent_of(text), "log_sale", text)


class AddStockIsRestock(unittest.TestCase):
    def test_add_stock_words_are_a_restock(self):
        for text in ("add 5 stock to panadol", "add stock panadol 5", "add for panadol 5 items", "زود بنادول 10"):
            self.assertEqual(intent_of(text), "log_restock", text)

    def test_stock_questions_stay_stock_queries(self):
        for text in ("low stock", "show me the stock", "مخزون", "stock of panadol"):
            self.assertEqual(intent_of(text), "query_stock", text)


if __name__ == "__main__":
    unittest.main()