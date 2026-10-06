# tests/test_restock_card.py
"""propose_restock (Session 126, Omar: the model prepares the restock card, no local hint).

The /ai tool only STORES a pending `log_restock` card (the same card the local path made);
the stock changes only when a person confirms it through the main API. In-memory SQLite,
no external calls (same helpers as tests/test_ai_agent_tools.py).
"""
import os
import secrets
import unittest
from unittest.mock import AsyncMock, patch

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app
from server.app.services.security import create_ai_access_token, decode_access_token


class RestockCardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    # ---- helpers ----
    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def register_owner(self, name: str) -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Restock Owner", "phone": f"09{secrets.randbelow(100_000_000):08d}",
            "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def ai(self, session: dict) -> dict:
        identity = decode_access_token(session["token"])
        return self.auth(create_ai_access_token(identity["user_id"], identity["pharmacy_id"]))

    def make_product(self, owner: dict, stock: float = 3, **extra) -> int:
        body = {
            "name_ar": "صنف توريد", "name_en": f"Restock Product {secrets.token_hex(3)}",
            "stock_qty": stock, "min_threshold": 1, "unit_buy_price": 10.25, "unit_sell_price": 12.5,
        }
        body.update(extra)
        created = self.client.post("/api/inventory/create", headers=self.auth(owner["token"]), json=body)
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    def stock_of(self, owner: dict, item_id: float) -> float:
        response = self.client.get("/api/inventory/items", headers=self.auth(owner["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        rows = response.json()
        rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        return next(r["stock_qty"] for r in rows if r["id"] == item_id)

    def propose(self, owner: dict, **body):
        return self.client.post("/ai/propose-restock", headers=self.ai(owner), json=body)

    # ---- the tool ----
    def test_propose_stores_a_pending_card_and_changes_no_stock(self):
        owner = self.register_owner("Restock Card Pharmacy")
        item_id = self.make_product(owner, stock=3)
        response = self.propose(owner, item_id=item_id, quantity=5)
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertEqual(body["status"], "pending_review")
        self.assertTrue(body["proposal_id"])
        # The answer never names a price or a total (the buy price stays out of the model).
        self.assertNotIn("10.25", response.text)
        self.assertNotIn("EGP", response.text)
        self.assertEqual(self.stock_of(owner, item_id), 3)

    def test_confirm_adds_the_units_once(self):
        owner = self.register_owner("Restock Confirm Pharmacy")
        item_id = self.make_product(owner, stock=3)
        card_id = self.propose(owner, item_id=item_id, quantity=5).json()["proposal_id"]
        headers = self.auth(owner["token"])
        first = self.client.post(f"/api/actions/{card_id}/confirm", headers=headers, json={})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(self.stock_of(owner, item_id), 8)
        second = self.client.post(f"/api/actions/{card_id}/confirm", headers=headers, json={})
        self.assertGreaterEqual(second.status_code, 400)
        self.assertEqual(self.stock_of(owner, item_id), 8)

    def test_card_pins_the_line_to_the_chosen_id_even_when_two_products_share_a_name(self):
        owner = self.register_owner("Restock Twin Pharmacy")
        first_id = self.make_product(owner, stock=1, name_en="Twin A")
        second_id = self.make_product(owner, stock=1, name_en="Twin B")
        card_id = self.propose(owner, item_id=first_id, quantity=2).json()["proposal_id"]
        self.client.post(f"/api/actions/{card_id}/confirm", headers=self.auth(owner["token"]), json={})
        self.assertEqual(self.stock_of(owner, first_id), 3)
        self.assertEqual(self.stock_of(owner, second_id), 1)

    def test_unknown_id_and_another_pharmacys_id_make_no_card(self):
        owner = self.register_owner("Restock Own Pharmacy")
        other = self.register_owner("Restock Other Pharmacy")
        foreign_id = self.make_product(other)
        for item_id in (999_999, foreign_id):
            response = self.propose(owner, item_id=item_id, quantity=1)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["status"], "not_created")
            self.assertIsNone(response.json()["proposal_id"])

    def test_bad_arguments_answer_422(self):
        owner = self.register_owner("Restock Bad Args Pharmacy")
        item_id = self.make_product(owner)
        for body in (
            {"item_id": item_id, "quantity": 0},
            {"item_id": item_id, "quantity": -2},
            {"item_id": 0, "quantity": 1},
            {"item_id": item_id},
            {"item_id": item_id, "quantity": 1, "unit_buy_price": 5},
            {"item_id": item_id, "quantity": 1, "pharmacy_id": 1},
        ):
            self.assertEqual(self.propose(owner, **body).status_code, 422, body)

    def test_a_member_without_log_restock_gets_403(self):
        owner = self.register_owner("Restock Scope Pharmacy")
        item_id = self.make_product(owner)
        viewer_invite = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations",
            headers=self.auth(owner["token"]), json={"fixed_role": "viewer", "max_uses": 1},
        )
        account = self.client.post("/api/auth/register-user", json={
            "name": "Viewer", "phone": f"09{secrets.randbelow(100_000_000):08d}", "pin": "2468", "language_pref": "ar",
        })
        joined = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account.json()["token"]), json={"token": viewer_invite.json()["token"]},
        )
        self.assertEqual(joined.status_code, 200, joined.text)
        response = self.propose(joined.json(), item_id=item_id, quantity=1)
        self.assertEqual(response.status_code, 403, response.text)

    def test_at_most_five_cards_wait(self):
        owner = self.register_owner("Restock Limit Pharmacy")
        item_id = self.make_product(owner)
        statuses = [self.propose(owner, item_id=item_id, quantity=1).json()["status"] for _ in range(6)]
        self.assertEqual(statuses, ["pending_review"] * 5 + ["not_created"])

    # ---- chat: the model decides, nothing local ----
    def test_chat_restock_message_goes_to_the_agent_and_shows_its_card(self):
        owner = self.register_owner("Restock Chat Pharmacy")
        item_id = self.make_product(owner, stock=3)
        headers = self.auth(owner["token"])

        async def fake_agent(question, token, **kwargs):
            # What the flow does: call the tool with the per-message token.
            card = self.client.post(
                "/ai/propose-restock", headers=self.auth(token), json={"item_id": item_id, "quantity": 5},
            )
            assert card.status_code == 200, card.text
            return {"text": "Review the card and confirm."}

        with patch("server.app.api.chat.settings.AI_TOOLS_ENABLED", True), \
                patch("server.app.api.chat.settings.USE_MICROMIND", True), \
                patch("server.app.services.micromind.micromind_client.query_agent", new=AsyncMock(side_effect=fake_agent)) as agent:
            response = self.client.post("/api/chat", headers=headers, json={"text": "add 5 صنف توريد", "language": "en"})
        self.assertEqual(response.status_code, 200, response.text)
        agent.assert_awaited()
        body = response.json()
        self.assertEqual(body["text"], "Review the card and confirm.")
        self.assertEqual(body["proposal"]["action_type"], "log_restock")
        self.assertEqual(body["proposal"]["items"][0]["matched_inventory_id"], item_id)
        self.assertEqual(self.stock_of(owner, item_id), 3)

    def test_chat_restock_with_tools_off_keeps_the_local_card(self):
        owner = self.register_owner("Restock Local Pharmacy")
        self.make_product(owner, stock=3)
        with patch("server.app.api.chat.settings.AI_TOOLS_ENABLED", False), \
                patch("server.app.api.chat.settings.USE_MICROMIND", False):
            response = self.client.post(
                "/api/chat", headers=self.auth(owner["token"]), json={"text": "add 5 صنف توريد", "language": "en"},
            )
        self.assertEqual(response.status_code, 200, response.text)


if __name__ == "__main__":
    unittest.main()