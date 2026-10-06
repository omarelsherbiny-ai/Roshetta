# tests/test_proposal_money.py
"""Proposal money is rounded exactly as confirmation books it (Waiting item 108).

Deterministic checks only: no database, no external services.
"""

import unittest

from agents.agents.verification import _round2, verification_agent
from server.app.db.money import round_money


INVENTORY = [{
    "id": 7,
    "name_ar": "بنادول",
    "name_en": "Panadol",
    "stock_qty": 50.0,
    "unit_sell_price": 35.0,
    "unit_buy_price": 28.0,
}]


def propose(items, intent="log_sale", inventory=None):
    return verification_agent({
        "intent": intent,
        "extracted_items": items,
        "inventory_data": INVENTORY if inventory is None else inventory,
        "language": "en",
    })["proposal"]


class ProposalMoneyTests(unittest.TestCase):
    def test_half_up_rounding_of_a_typed_price(self):
        # Python's round(10.005, 2) is 10.0; confirmation rounds half-up to 10.01.
        proposal = propose([{"item_name": "Panadol", "quantity": 1, "unit_price": 10.005}])
        self.assertEqual(proposal["items"][0]["unit_price"], 10.01)
        self.assertEqual(proposal["items"][0]["subtotal"], 10.01)
        self.assertEqual(proposal["total_amount"], 10.01)

    def test_fractional_quantity_line_is_rounded_half_up(self):
        proposal = propose([{"item_name": "Panadol", "quantity": 0.5, "unit_price": 25.01}])
        self.assertEqual(proposal["items"][0]["subtotal"], 12.51)
        self.assertEqual(proposal["total_amount"], 12.51)

    def test_total_is_the_sum_of_rounded_subtotals(self):
        # Unrounded: 12.505 + 12.505 = 25.01. Booked: 12.51 + 12.51 = 25.02.
        proposal = propose([
            {"item_name": "Panadol", "quantity": 0.5, "unit_price": 25.01},
            {"item_name": "Panadol", "quantity": 0.5, "unit_price": 25.01},
        ])
        self.assertEqual([line["subtotal"] for line in proposal["items"]], [12.51, 12.51])
        self.assertEqual(proposal["total_amount"], 25.02)

    def test_averaged_fifo_price_is_a_two_place_price(self):
        inventory = [{**INVENTORY[0], "price_batches": [
            {"quantity": 1.0, "unit_sell_price": 20.0},
            {"quantity": 2.0, "unit_sell_price": 25.0},
        ]}]
        proposal = propose(
            [{"item_name": "Panadol", "quantity": 3, "unit_price": 0.0}], inventory=inventory
        )
        line = proposal["items"][0]
        # (20 + 25 + 25) / 3 = 23.3333...; confirmation books the 2-place price.
        self.assertEqual(line["unit_price"], 23.33)
        self.assertEqual(line["subtotal"], 69.99)
        self.assertEqual(proposal["total_amount"], 69.99)

    def test_restock_and_expense_totals_are_rounded_too(self):
        restock = propose(
            [{"item_name": "Panadol", "quantity": 3, "unit_price": 9.995}], intent="log_restock"
        )
        self.assertEqual(restock["items"][0]["unit_price"], 10.0)
        self.assertEqual(restock["total_amount"], 30.0)
        expense = propose(
            [{"item_name": "Rent", "quantity": 1, "unit_price": 100.004}], intent="log_expense"
        )
        self.assertEqual(expense["total_amount"], 100.0)

    def test_summary_text_uses_the_rounded_total(self):
        proposal = propose([{"item_name": "Panadol", "quantity": 0.5, "unit_price": 25.01}])
        self.assertIn("12.51", proposal["summary_en"])

    def test_non_finite_price_is_left_for_confirmation_to_reject(self):
        self.assertTrue(_round2(float("inf")) == float("inf"))
        self.assertNotEqual(_round2(float("nan")), _round2(float("nan")))  # nan stays nan

    def test_local_rounding_matches_the_server_helper(self):
        samples = [
            10.005, 0.5 * 25.01, 12.505, 23.333333333, 3 * 23.33, 0.004, 0.005, 0.0,
            1e-7, 99999999.995, 100000000.005, 1.0, 2.675, 1.005, 0.015, 0.025,
        ]
        for value in samples:
            with self.subTest(value=value):
                self.assertEqual(_round2(value), round_money(value))


if __name__ == "__main__":
    unittest.main()