# tests/test_assistant_scope.py
"""Assistant and /ai scope checks (Session 109, W6 a and W8 a): the chat endpoint passes pharmacy data
to the assistant only to members whose role holds the matching scope and refuses action proposals
without the scope; the /ai read tools follow the same scopes, tenant isolation and cashier scoping;
the short-lived AI token works on /ai only. In-memory SQLite database."""

import os
import secrets
import unittest
from unittest.mock import patch

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["AI_TOOLS_ENABLED"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app
from server.app.services.security import create_ai_access_token

ACCEPT = "/api/pharmacies/invitations/accept"
NO_ACTION = "Your account does not have permission for this action."
NO_STOCK = "Your account does not have permission to view inventory."
NO_FINANCE = "Your account does not have permission to view financial summaries."


def proposal_stub() -> dict:
    return {
        "id": "prop-" + "a" * 32, "action_type": "log_sale", "title": "t", "summary_ar": "a",
        "summary_en": "e", "items": [], "total_amount": 1.0, "payment_method": "cash",
        "confidence": 1.0, "status": "pending_confirmation", "created_at": None,
    }


class AssistantScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def phone(self) -> str:
        return f"09{secrets.randbelow(100_000_000):08d}"

    def owner(self, name: str) -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Scope Owner", "phone": self.phone(), "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def join(self, owner: dict, **invite_body) -> dict:
        invitation = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations",
            headers=self.auth(owner["token"]), json=invite_body,
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account = self.client.post("/api/auth/register-user", json={
            "name": "Scope Member", "phone": self.phone(), "pin": "2468", "language_pref": "ar",
        }).json()
        accepted = self.client.post(
            ACCEPT, headers=self.auth(account["token"]), json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return {"headers": self.auth(accepted.json()["token"]), "user_id": account["user"]["id"]}

    def custom(self, owner: dict, name: str, scopes: list[str]) -> dict:
        role = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/roles",
            headers=self.auth(owner["token"]), json={"name": name, "scopes": scopes},
        )
        self.assertEqual(role.status_code, 200, role.text)
        return self.join(owner, custom_role_id=role.json()["role"]["id"])

    def product(self, headers: dict, name_en: str = "Panadol Extra (Red)", name_ar: str = "بنادول اكسترا (أحمر)") -> int:
        created = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": name_ar, "name_en": name_en, "stock_qty": 4, "min_threshold": 1,
            "unit_buy_price": 28, "unit_sell_price": 35,
        })
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    def chat(self, headers: dict, result: dict):
        """Calls /api/chat with the orchestration replaced by a fixed result; returns (response, state it received)."""
        captured: dict = {}

        async def runner(state):
            captured["state"] = state
            return dict(result)

        with patch("server.app.api.chat.run_orchestration", new=runner):
            response = self.client.post("/api/chat", headers=headers, json={"text": "scope probe", "language": "en"})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json(), captured["state"]

    def test_chat_passes_data_to_the_assistant_only_when_the_scope_allows(self):
        owner = self.owner("Assistant State Pharmacy")
        owner_headers = self.auth(owner["token"])
        self.product(owner_headers, name_en="State Probe Product", name_ar="منتج اختبار الحالة")
        viewer = self.join(owner, fixed_role="viewer")
        stock_look = self.custom(owner, "Stock Look", ["view_inventory"])
        seller = self.custom(owner, "Seller Only", ["log_sale"])
        neutral = {"intent": "scope_probe", "answer_text": "ok", "proposal": None}

        _, state = self.chat(owner_headers, neutral)
        self.assertEqual([item["name_en"] for item in state["inventory_data"]], ["State Probe Product"])
        self.assertIsNotNone(state["financial_data"])

        _, state = self.chat(viewer["headers"], neutral)  # view_reports only
        self.assertEqual(state["inventory_data"], [])
        self.assertIsNotNone(state["financial_data"])

        _, state = self.chat(stock_look["headers"], neutral)  # view_inventory only
        self.assertEqual(len(state["inventory_data"]), 1)
        self.assertIsNone(state["financial_data"])

        _, state = self.chat(seller["headers"], neutral)  # log_sale only
        self.assertEqual(state["inventory_data"], [])
        self.assertIsNone(state["financial_data"])

    def test_chat_replaces_query_answers_when_the_scope_is_missing(self):
        owner = self.owner("Assistant Query Pharmacy")
        viewer = self.join(owner, fixed_role="viewer")
        stock_look = self.custom(owner, "Stock Look", ["view_inventory"])
        seller = self.custom(owner, "Seller Only", ["log_sale"])
        stock = {"intent": "query_stock", "answer_text": "SECRET-STOCK", "proposal": None}
        finance = {"intent": "query_finance", "answer_text": "SECRET-FIN", "proposal": None}

        self.assertEqual(self.chat(self.auth(owner["token"]), stock)[0]["text"], "SECRET-STOCK")
        self.assertEqual(self.chat(stock_look["headers"], stock)[0]["text"], "SECRET-STOCK")
        self.assertEqual(self.chat(viewer["headers"], stock)[0]["text"], NO_STOCK)
        self.assertEqual(self.chat(seller["headers"], stock)[0]["text"], NO_STOCK)

        self.assertEqual(self.chat(self.auth(owner["token"]), finance)[0]["text"], "SECRET-FIN")
        self.assertEqual(self.chat(viewer["headers"], finance)[0]["text"], "SECRET-FIN")
        self.assertEqual(self.chat(stock_look["headers"], finance)[0]["text"], NO_FINANCE)
        self.assertEqual(self.chat(seller["headers"], finance)[0]["text"], NO_FINANCE)

    def test_chat_drops_action_proposals_without_the_scope(self):
        owner = self.owner("Assistant Action Pharmacy")
        viewer = self.join(owner, fixed_role="viewer")
        stock_look = self.custom(owner, "Stock Look", ["view_inventory"])
        seller = self.custom(owner, "Seller No Stock", ["log_sale"])
        restocker = self.custom(owner, "Restocker No Stock", ["log_restock"])

        cases = [
            ("log_sale", viewer),       # no log_sale scope
            ("log_expense", viewer),    # no log_expense scope
            ("log_expense", stock_look),
            ("log_sale", seller),       # has log_sale but may not view inventory
            ("log_restock", restocker), # has log_restock but may not view inventory
        ]
        for intent, member in cases:
            body, _ = self.chat(member["headers"], {"intent": intent, "answer_text": "proposal ready", "proposal": proposal_stub()})
            self.assertIsNone(body["proposal"], intent)
            self.assertEqual(body["text"], NO_ACTION, intent)

    def test_ai_routes_follow_the_members_scopes(self):
        owner = self.owner("AI Scope Pharmacy")
        item_id = self.product(self.auth(owner["token"]))
        viewer = self.join(owner, fixed_role="viewer")  # view_reports only
        stock_look = self.custom(owner, "Stock Look", ["view_inventory"])
        seller = self.custom(owner, "Seller Only", ["log_sale"])

        def status(member: dict, method: str, path: str) -> int:
            if method == "POST":
                return self.client.post(path, headers=member["headers"], json={"query_name": "pana"}).status_code
            return self.client.get(path, headers=member["headers"]).status_code

        stock_paths = [("GET", "/ai/items"), ("POST", "/ai/match"), ("GET", f"/ai/items/{item_id}/batches")]
        report_paths = [("GET", "/ai/entries"), ("GET", "/ai/payables"), ("GET", "/ai/payables/summary")]
        for method, path in stock_paths:
            self.assertEqual(status(viewer, method, path), 403, path)
            self.assertEqual(status(stock_look, method, path), 200, path)
            self.assertEqual(status(seller, method, path), 403, path)
        for method, path in report_paths:
            self.assertEqual(status(viewer, method, path), 200, path)
            self.assertEqual(status(stock_look, method, path), 403, path)
            self.assertEqual(status(seller, method, path), 403, path)
        listed = self.client.get("/ai/items", headers=stock_look["headers"]).json()
        self.assertEqual([row["id"] for row in listed], [item_id])
        self.assertNotIn("unit_buy_price", listed[0])
        self.assertEqual(self.client.get("/ai/items").status_code, 401)

    def test_ai_entries_are_cashier_scoped_and_tenants_are_isolated(self):
        owner = self.owner("AI Entries Pharmacy")
        owner_headers = self.auth(owner["token"])
        item_id = self.product(owner_headers)
        proposal = self.client.post("/api/chat", headers=owner_headers, json={"text": "sold panadol extra", "language": "en"})
        confirmed = self.client.post(f"/api/actions/{proposal.json()['proposal']['id']}/confirm", headers=owner_headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        cashier = self.join(owner, fixed_role="cashier")

        owner_entries = self.client.get("/ai/entries", headers=owner_headers)
        self.assertEqual(owner_entries.status_code, 200, owner_entries.text)
        self.assertGreaterEqual(len(owner_entries.json()), 1)
        for row in owner_entries.json():
            self.assertNotIn("notes", row)
            self.assertNotIn("confirmed_by_name", row)
        self.assertEqual(self.client.get("/ai/entries", headers=cashier["headers"]).json(), [])

        other = self.owner("AI Entries Other Pharmacy")
        other_headers = self.auth(other["token"])
        self.assertEqual(self.client.get("/ai/items", headers=other_headers).json(), [])
        self.assertEqual(self.client.get("/ai/entries", headers=other_headers).json(), [])
        self.assertEqual(self.client.get(f"/ai/items/{item_id}/batches", headers=other_headers).status_code, 404)

    def test_ai_token_works_on_ai_only_and_keeps_the_members_scopes(self):
        owner = self.owner("AI Token Pharmacy")
        self.product(self.auth(owner["token"]))
        pharmacy_id = owner["pharmacy"]["id"]
        token = create_ai_access_token(owner["user"]["id"], pharmacy_id)

        self.assertIn(self.client.get("/api/inventory/items", headers=self.auth(token)).status_code, (401, 403))
        self.assertEqual(self.client.get("/ai/items", headers=self.auth(token)).status_code, 200)

        viewer = self.join(owner, fixed_role="viewer")
        viewer_token = create_ai_access_token(viewer["user_id"], pharmacy_id)
        self.assertEqual(self.client.get("/ai/items", headers=self.auth(viewer_token)).status_code, 403)
        self.assertEqual(self.client.get("/ai/entries", headers=self.auth(viewer_token)).status_code, 200)


if __name__ == "__main__":
    unittest.main()