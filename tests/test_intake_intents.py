# tests/test_intake_intents.py
import unittest

from agents.agents.intake import intake_agent


def _intent(text: str, language: str = "en") -> str:
    return intake_agent({"user_query": text, "language": language})["intent"]


class IntakeIntentTests(unittest.TestCase):
    def test_summary_phrases_are_finance(self):
        for text, lang in [
            ("Show today's summary", "en"),
            ("today's summary", "en"),
            ("daily financial summary", "en"),
            ("show me the revenue", "en"),
            ("ملخص اليوم", "ar"),
            ("الملخص المالي", "ar"),
            ("الايرادات", "ar"),
            ("أرباح اليوم", "ar"),
            ("profit", "en"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(_intent(text, lang), "query_finance")

    def test_sales_today_questions_are_finance(self):
        for text, lang in [
            ("how many i sell today", "en"),
            ("How much did I sell today?", "en"),
            ("بعت كام النهاردة", "ar"),
            ("كم بعنا اليوم؟", "ar"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(_intent(text, lang), "query_finance")

    def test_sale_commands_stay_sales(self):
        for text, lang in [
            ("بعت 3 علب بنادول اليوم", "ar"),
            ("بعت كمية بنادول اليوم", "ar"),
            ("sold 3 panadol today", "en"),
        ]:
            with self.subTest(text=text):
                self.assertEqual(_intent(text, lang), "log_sale")

    def test_stock_summary_stays_inventory(self):
        for text in ["stock summary", "ملخص المخزون", "low stock"]:
            with self.subTest(text=text):
                self.assertEqual(_intent(text), "query_stock")

    def test_other_intents_unchanged(self):
        self.assertEqual(_intent("بعت 3 علب بنادول", "ar"), "log_sale")
        self.assertEqual(_intent("restock panadol 10", "en"), "log_restock")
        self.assertEqual(_intent("مصاريف كهرباء 500", "ar"), "log_expense")
        self.assertEqual(_intent("hello there"), "general_chat")


if __name__ == "__main__":
    unittest.main()