# tests/test_flow.py
"""Safe unit checks for inventory-grounded action proposals.

These tests exercise the deterministic verification stage only. They never
connect to the configured pharmacy database or call external services.
"""

import unittest

from agents.agents.verification import verification_agent
from agents.agents.intake import intake_agent
from agents.agents.inventory import inventory_agent
from server.app.services.stock import overdrawn_inventory_quantities


class VerificationAgentTests(unittest.TestCase):
    def setUp(self):
        self.inventory = [
            {
                "id": 7,
                "name_ar": "بنادول",
                "name_en": "Panadol",
                "stock_qty": 5.0,
                "unit_sell_price": 35.0,
                "unit_buy_price": 28.0,
            }
        ]

    def run_verification(self, *, intent, name, quantity, unit_price=0.0, language="en"):
        return verification_agent({
            "intent": intent,
            "extracted_items": [{
                "item_name": name,
                "quantity": quantity,
                "unit_price": unit_price,
            }],
            "inventory_data": self.inventory,
            "language": language,
        })

    def test_sale_proposal_uses_inventory_identity_and_price(self):
        result = self.run_verification(
            intent="log_sale",
            name="Panadol",
            quantity=2,
        )

        proposal = result["proposal"]
        self.assertEqual(proposal["action_type"], "log_sale")
        self.assertEqual(proposal["status"], "pending_confirmation")
        self.assertEqual(proposal["total_amount"], 70.0)
        self.assertEqual(proposal["items"][0]["matched_inventory_id"], 7)
        self.assertEqual(proposal["items"][0]["unit_price"], 35.0)

    def test_sale_price_uses_fifo_lot_prices_and_weights_a_multi_lot_line(self):
        inventory = [{
            **self.inventory[0],
            "price_batches": [
                {"quantity": 2.0, "unit_sell_price": 20.0},
                {"quantity": 3.0, "unit_sell_price": 30.0},
            ],
        }]
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [{"item_name": "Panadol", "quantity": 4, "unit_price": 0.0}],
            "inventory_data": inventory,
            "language": "en",
        })
        line = result["proposal"]["items"][0]
        self.assertEqual(line["unit_price"], 25.0)
        self.assertEqual(line["subtotal"], 100.0)

    def test_duplicate_sale_lines_consume_fifo_lots_without_repricing_older_units(self):
        inventory = [{
            **self.inventory[0],
            "price_batches": [
                {"quantity": 2.0, "unit_sell_price": 20.0},
                {"quantity": 3.0, "unit_sell_price": 30.0},
            ],
        }]
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [
                {"item_name": "Panadol", "quantity": 2, "unit_price": 0.0},
                {"item_name": "Panadol", "quantity": 2, "unit_price": 0.0},
            ],
            "inventory_data": inventory,
            "language": "en",
        })
        self.assertEqual([line["unit_price"] for line in result["proposal"]["items"]], [20.0, 30.0])
        self.assertEqual(result["proposal"]["total_amount"], 100.0)

    def test_missing_product_returns_actionable_block_without_proposal(self):
        result = self.run_verification(
            intent="log_sale",
            name="Unknown medicine",
            quantity=1,
        )

        self.assertIsNone(result["proposal"])
        self.assertIn("cannot be processed", result["answer_text"])
        self.assertIn("manual inventory form", result["answer_text"])
        self.assertNotIn("box camera scan", result["answer_text"])

    def test_sale_above_available_stock_is_blocked(self):
        result = self.run_verification(
            intent="log_sale",
            name="Panadol",
            quantity=6,
        )

        self.assertIsNone(result["proposal"])
        self.assertIn("exceeds available stock", result["answer_text"])

    def test_restock_uses_inventory_purchase_price(self):
        result = self.run_verification(
            intent="log_restock",
            name="Panadol",
            quantity=3,
        )

        proposal = result["proposal"]
        self.assertEqual(proposal["action_type"], "log_restock")
        self.assertEqual(proposal["total_amount"], 84.0)
        self.assertEqual(proposal["items"][0]["unit_price"], 28.0)

    def test_blocked_copy_uses_requested_language(self):
        result = self.run_verification(
            intent="log_sale",
            name="دواء غير مسجل",
            quantity=1,
            language="ar",
        )

        self.assertIsNone(result["proposal"])
        self.assertIn("لا يمكن إتمام هذه العملية", result["answer_text"])
        self.assertIn("الإدخال اليدوي", result["answer_text"])

    def test_duplicate_sale_lines_are_checked_as_one_stock_total(self):
        overdrawn = overdrawn_inventory_quantities(
            [(7, 3.0), (7, 3.0)],
            {7: 5.0},
        )

        self.assertEqual(overdrawn, {7: 6.0})

    def test_duplicate_sale_lines_at_available_stock_are_allowed(self):
        overdrawn = overdrawn_inventory_quantities(
            [(7, 2.0), (7, 3.0)],
            {7: 5.0},
        )

        self.assertEqual(overdrawn, {})

    def test_english_restock_is_not_misclassified_as_inventory_lookup(self):
        result = intake_agent({"user_query": "restock 3 Panadol Extra"})
        self.assertEqual(result["intent"], "log_restock")
        self.assertEqual(result["extracted_items"][0]["quantity"], 3)

        lookup = intake_agent({"user_query": "show stock"})
        self.assertEqual(lookup["intent"], "query_stock")

    def test_general_chat_fallback_is_localized_and_truthful_about_ocr(self):
        english = intake_agent({"user_query": "hello", "language": "en"})["answer_text"]
        arabic = intake_agent({"user_query": "مرحبا", "language": "ar"})["answer_text"]
        self.assertIn("Document extraction is currently unavailable", english)
        self.assertNotIn("camera", english.lower())
        self.assertIn("غير متاح", arabic)
        self.assertNotIn("الكاميرا", arabic)

    def test_inventory_answers_are_localized_and_distinguish_empty_from_in_stock(self):
        empty = inventory_agent({"inventory_data": [], "language": "en"})["answer_text"]
        self.assertIn("No inventory products are recorded", empty)
        self.assertNotIn("at or below", empty)

        low_stock = inventory_agent({
            "language": "en",
            "inventory_data": [{
                "name_ar": "بنادول",
                "name_en": "Panadol",
                "stock_qty": 2,
                "min_threshold": 5,
            }],
        })["answer_text"]
        self.assertIn("Panadol", low_stock)
        self.assertIn("current stock: 2 units", low_stock)

        arabic = inventory_agent({"inventory_data": [], "language": "ar"})["answer_text"]
        self.assertIn("لا توجد أصناف مسجلة", arabic)

    def test_proposal_id_is_a_full_uuid_and_never_repeats(self):
        first = self.run_verification(intent="log_sale", name="Panadol", quantity=1)["proposal"]["id"]
        second = self.run_verification(intent="log_sale", name="Panadol", quantity=1)["proposal"]["id"]

        # "prop-" plus a 32-hex uuid4 (128 bits); a shorter id could collide across pharmacies.
        self.assertRegex(first, r"^prop-[0-9a-f]{32}$")
        self.assertRegex(second, r"^prop-[0-9a-f]{32}$")
        self.assertNotEqual(first, second)

    def test_same_product_on_two_sale_lines_is_blocked_when_the_sum_exceeds_stock(self):
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [
                {"item_name": "Panadol", "quantity": 3, "unit_price": 0.0},
                {"item_name": "Panadol", "quantity": 3, "unit_price": 0.0},
            ],
            "inventory_data": self.inventory,
            "language": "en",
        })

        # Each line alone fits the stock of 5; together they ask for 6.
        self.assertIsNone(result["proposal"])
        self.assertIn("quantity (6", result["answer_text"])
        self.assertIn("exceeds available stock", result["answer_text"])

    def test_same_product_on_two_sale_lines_at_exactly_the_stock_is_allowed(self):
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [
                {"item_name": "Panadol", "quantity": 2, "unit_price": 0.0},
                {"item_name": "Panadol", "quantity": 3, "unit_price": 0.0},
            ],
            "inventory_data": self.inventory,
            "language": "en",
        })

        self.assertIsNotNone(result["proposal"])
        self.assertEqual(result["proposal"]["total_amount"], 175.0)

    def test_arabic_and_english_names_of_one_product_count_together(self):
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [
                {"item_name": "Panadol", "quantity": 3, "unit_price": 0.0},
                {"item_name": "بنادول", "quantity": 3, "unit_price": 0.0},
            ],
            "inventory_data": self.inventory,
            "language": "en",
        })

        self.assertIsNone(result["proposal"])
        self.assertIn("exceeds available stock", result["answer_text"])

    def test_different_products_do_not_share_one_stock_total(self):
        inventory = self.inventory + [{
            "id": 8,
            "name_ar": "بروفين",
            "name_en": "Brufen",
            "stock_qty": 5.0,
            "unit_sell_price": 40.0,
            "unit_buy_price": 30.0,
        }]
        result = verification_agent({
            "intent": "log_sale",
            "extracted_items": [
                {"item_name": "Panadol", "quantity": 4, "unit_price": 0.0},
                {"item_name": "Brufen", "quantity": 4, "unit_price": 0.0},
            ],
            "inventory_data": inventory,
            "language": "en",
        })

        self.assertIsNotNone(result["proposal"])
        self.assertEqual(result["proposal"]["total_amount"], 300.0)

    def test_restock_quantity_is_never_limited_by_current_stock(self):
        result = self.run_verification(intent="log_restock", name="Panadol", quantity=100)

        self.assertIsNotNone(result["proposal"])
        self.assertEqual(result["proposal"]["total_amount"], 2800.0)


if __name__ == "__main__":
    unittest.main()