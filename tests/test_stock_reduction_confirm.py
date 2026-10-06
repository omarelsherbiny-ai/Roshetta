# tests/test_stock_reduction_confirm.py
"""propose_stock_reduction and its confirm (Session 126). In-memory SQLite, no external calls."""
import os
import secrets
import unittest

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app
from server.app.services.security import create_ai_access_token, decode_access_token


class StockReductionConfirmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def register_owner(self, name: str) -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Reduce Owner", "phone": f"09{secrets.randbelow(100_000_000):08d}",
            "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def ai(self, session: dict) -> dict:
        identity = decode_access_token(session["token"])
        return self.auth(create_ai_access_token(identity["user_id"], identity["pharmacy_id"]))

    def make_product(self, owner: dict, stock: float = 12) -> int:
        created = self.client.post("/api/inventory/create", headers=self.auth(owner["token"]), json={
            "name_ar": "صنف تقليل", "name_en": f"Reduce Product {secrets.token_hex(3)}",
            "stock_qty": stock, "min_threshold": 1, "unit_buy_price": 10.25, "unit_sell_price": 12.5,
        })
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    def stock_of(self, owner: dict, item_id: int) -> float:
        response = self.client.get("/api/inventory/items", headers=self.auth(owner["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        return next(r["stock_qty"] for r in rows if r["id"] == item_id)

    def propose(self, owner: dict, **body):
        return self.client.post("/ai/propose-stock-reduction", headers=self.ai(owner), json=body)

    def test_propose_writes_nothing_then_confirm_lowers_once(self):
        owner = self.register_owner("Reduce Confirm Pharmacy")
        item_id = self.make_product(owner, 12)
        response = self.propose(owner, item_id=item_id, new_quantity=8)
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["status"], "pending_review")
        self.assertEqual(self.stock_of(owner, item_id), 12)
        card_id = response.json()["proposal_id"]
        headers = self.auth(owner["token"])
        first = self.client.post(f"/api/actions/{card_id}/confirm", headers=headers, json={})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(first.json()["proposal"]["action_type"], "reduce_stock")
        self.assertEqual(self.stock_of(owner, item_id), 8)
        second = self.client.post(f"/api/actions/{card_id}/confirm", headers=headers, json={})
        self.assertGreaterEqual(second.status_code, 400)
        self.assertEqual(self.stock_of(owner, item_id), 8)

    def test_same_or_higher_count_makes_no_card_and_says_use_restock(self):
        owner = self.register_owner("Reduce Higher Pharmacy")
        item_id = self.make_product(owner, 12)
        for value in (12, 20):
            response = self.propose(owner, item_id=item_id, new_quantity=value)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "not_created")
            self.assertIn("propose_restock", response.json()["summary"])

    def test_stock_changed_after_the_card_gives_409_and_changes_nothing(self):
        owner = self.register_owner("Reduce Stale Pharmacy")
        item_id = self.make_product(owner, 12)
        card_id = self.propose(owner, item_id=item_id, new_quantity=8).json()["proposal_id"]
        # A restock confirmed meanwhile moves the stock the card was prepared against.
        restock = self.client.post("/ai/propose-restock", headers=self.ai(owner), json={"item_id": item_id, "quantity": 5})
        restock_id = restock.json()["proposal_id"]
        self.client.post(f"/api/actions/{restock_id}/confirm", headers=self.auth(owner["token"]), json={})
        self.assertEqual(self.stock_of(owner, item_id), 17)
        stale = self.client.post(f"/api/actions/{card_id}/confirm", headers=self.auth(owner["token"]), json={})
        self.assertEqual(stale.status_code, 409, stale.text)
        self.assertEqual(self.stock_of(owner, item_id), 17)

    def test_unknown_and_foreign_ids_make_no_card(self):
        owner = self.register_owner("Reduce Own Pharmacy")
        other = self.register_owner("Reduce Other Pharmacy")
        foreign = self.make_product(other, 12)
        for item_id in (999_999, foreign):
            response = self.propose(owner, item_id=item_id, new_quantity=1)
            self.assertEqual(response.json()["status"], "not_created")

    def test_bad_arguments_answer_422(self):
        owner = self.register_owner("Reduce Bad Args Pharmacy")
        item_id = self.make_product(owner)
        for body in (
            {"item_id": item_id, "new_quantity": -1},
            {"item_id": 0, "new_quantity": 1},
            {"item_id": item_id},
            {"item_id": item_id, "new_quantity": 1, "pharmacy_id": 1},
        ):
            self.assertEqual(self.propose(owner, **body).status_code, 422, body)

    def test_cancel_changes_nothing(self):
        owner = self.register_owner("Reduce Cancel Pharmacy")
        item_id = self.make_product(owner, 12)
        card_id = self.propose(owner, item_id=item_id, new_quantity=2).json()["proposal_id"]
        cancelled = self.client.post(f"/api/actions/{card_id}/cancel", headers=self.auth(owner["token"]))
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(self.stock_of(owner, item_id), 12)
        again = self.client.post(f"/api/actions/{card_id}/confirm", headers=self.auth(owner["token"]), json={})
        self.assertGreaterEqual(again.status_code, 400)


if __name__ == "__main__":
    unittest.main()