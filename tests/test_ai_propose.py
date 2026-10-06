# tests/test_ai_propose.py
import unittest

from pydantic import ValidationError

from server.app.api.ai_propose import AIProductProposalRequest, build_product_card
from server.app.services.ai_prompt import allowed_tools, build_agent_question

PANADOL = {"id": 1, "name_ar": "بنادول", "name_en": "Panadol", "stock_qty": 12.0, "unit_sell_price": 20.0}


class ProposeProductTests(unittest.TestCase):
    def test_card_is_built_like_the_local_chat_card(self):
        req = AIProductProposalRequest(name="Cetal", unit_sell_price=15, unit_buy_price=10, language="en")
        card = build_product_card(req, [])
        self.assertEqual(card["action_type"], "create_product")
        self.assertEqual(card["status"], "pending_confirmation")
        self.assertTrue(card["id"].startswith("prop-"))
        self.assertEqual(card["title"], "Add New Product")
        self.assertEqual(card["items"], [])
        self.assertEqual(card["product"]["unit_sell_price"], 15.0)
        self.assertEqual(card["product"]["unit_buy_price"], 10.0)
        self.assertEqual(card["product"]["stock_qty"], 0.0)
        self.assertEqual(card["duplicates"], [])

    def test_arabic_language_gives_arabic_card_text(self):
        card = build_product_card(AIProductProposalRequest(name="Cetal", unit_sell_price=15, language="ar"), [])
        self.assertEqual(card["title"], "إضافة منتج جديد")

    def test_similar_existing_product_is_reported(self):
        card = build_product_card(AIProductProposalRequest(name="Pandol", unit_sell_price=15, language="en"), [PANADOL])
        self.assertTrue(card["duplicates"])

    def test_request_refuses_identity_fields_and_bad_prices(self):
        with self.assertRaises(ValidationError):
            AIProductProposalRequest(name="Cetal", unit_sell_price=15, pharmacy_id=2)
        with self.assertRaises(ValidationError):
            AIProductProposalRequest(name="Cetal", unit_sell_price=15, user_id=2)
        with self.assertRaises(ValidationError):
            AIProductProposalRequest(name="Cetal", unit_sell_price=0)
        with self.assertRaises(ValidationError):
            AIProductProposalRequest(name="", unit_sell_price=5)
        with self.assertRaises(ValidationError):
            AIProductProposalRequest(name="Cetal", unit_sell_price=float("inf"))

    def test_only_members_who_manage_inventory_get_the_tool(self):
        self.assertIn("propose_product", allowed_tools("owner", None))
        self.assertNotIn("propose_product", allowed_tools("viewer", None))
        # Session 126: the user message is only the question; the tool list is
        # the imported spec and the rules live in the MicroMind website, not in code.
        question = build_agent_question("add product Cetal sell 15", "English", "owner", None)
        self.assertEqual(question, "add product Cetal sell 15")


if __name__ == "__main__":
    unittest.main()