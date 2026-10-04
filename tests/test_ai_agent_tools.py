# tests/test_ai_agent_tools.py
"""W8 b to f (Session 109): the new /ai read tools, the fixed prompt and the agent fallback.

Every /ai call here uses an AI token (create_ai_access_token), the same kind the agent
flow receives. In-memory SQLite, no external calls.
"""

import os
import secrets
import unittest
from datetime import date
from unittest.mock import AsyncMock, patch

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app
from server.app.services.ai_prompt import (
    SYSTEM_PROMPT,
    TOOL_GUIDE,
    TOOL_SCOPES,
    allowed_tools,
    build_agent_question,
)
from server.app.services.security import create_ai_access_token, decode_access_token

NEW_KEYS = {
    "summary": {"date", "total_sales", "total_expenses", "sales_count", "expenses_count"},
    "inventory_summary": {"item_count", "total_units", "potential_sales_value"},
    "category": {"name", "item_count"},
    "price_change": {"previous_unit_sell_price", "unit_sell_price", "recorded_at"},
    "role": {"name", "scopes", "assigned_count"},
    "timeline": {"source", "kind", "occurred_at", "actor_role_name", "product_name", "amount"},
}
DENIED_NAMES = {
    "pharmacy_id", "user_id", "token", "authorization", "role", "scope", "scopes",
    "confirmed", "created_by", "confirmed_by",
}


class AiAgentToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    # ---- helpers (same style as tests/test_ai_api.py) ----
    @staticmethod
    def new_phone() -> str:
        return f"09{secrets.randbelow(100_000_000):08d}"

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def register_owner(self, name: str) -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Agent Owner", "phone": self.new_phone(), "pin": "1234",
            "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def join(self, owner: dict, invite_body: dict, who: str) -> dict:
        pharmacy_id = owner["pharmacy"]["id"]
        invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=self.auth(owner["token"]), json={**invite_body, "max_uses": 1},
        )
        self.assertEqual(invite.status_code, 200, invite.text)
        account = self.client.post("/api/auth/register-user", json={
            "name": who, "phone": self.new_phone(), "pin": "2468", "language_pref": "ar",
        })
        self.assertEqual(account.status_code, 200, account.text)
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account.json()["token"]), json={"token": invite.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return accepted.json()

    def custom_member(self, owner: dict, scopes: list, who: str) -> dict:
        pharmacy_id = owner["pharmacy"]["id"]
        role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles", headers=self.auth(owner["token"]),
            json={"name": f"Role {secrets.token_hex(3)}", "scopes": scopes},
        )
        self.assertEqual(role.status_code, 200, role.text)
        return self.join(owner, {"custom_role_id": role.json()["role"]["id"]}, who)

    def ai_headers(self, session: dict) -> dict:
        identity = decode_access_token(session["token"])
        return self.auth(create_ai_access_token(identity["user_id"], identity["pharmacy_id"]))

    def make_product(self, owner: dict, **extra) -> int:
        body = {
            "name_ar": "صنف وكيل", "name_en": f"Agent Product {secrets.token_hex(3)}",
            "stock_qty": 0, "min_threshold": 1, "unit_buy_price": 10.25, "unit_sell_price": 12.5,
        }
        body.update(extra)
        created = self.client.post("/api/inventory/create", headers=self.auth(owner["token"]), json=body)
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    # ---- the /ai spec itself ----
    def test_ai_spec_has_no_identity_argument_and_only_one_post(self):
        spec = self.client.get("/ai/openapi.json").json()
        operations = []
        for path, item in spec["paths"].items():
            for method, op in item.items():
                operations.append((method, path, op))
                for parameter in op.get("parameters", []):
                    self.assertNotIn(parameter["name"].lower(), DENIED_NAMES, f"{method} {path}")
        posts = [(m, p) for m, p, _ in operations if m != "get"]
        self.assertEqual(posts, [("post", "/match")])
        ids = {op["operationId"] for _, _, op in operations}
        for new_tool in ("get_sales_summary", "get_inventory_summary", "list_low_stock", "list_categories",
                         "get_item_price_history", "list_records_timeline", "list_roles"):
            self.assertIn(new_tool, ids)

    def test_prompt_tool_table_matches_every_ai_operation(self):
        spec = self.client.get("/ai/openapi.json").json()
        ids = {op["operationId"] for item in spec["paths"].values() for op in item.values()}
        self.assertEqual(set(TOOL_SCOPES), ids)
        self.assertEqual(set(TOOL_GUIDE), ids)

    # ---- the fixed prompt ----
    def test_prompt_states_the_fixed_rules(self):
        lowered = SYSTEM_PROMPT.lower()
        for needle in ("arabic", "egp", "cairo", "never invent", "at most three", "you never change data"):
            self.assertIn(needle, lowered)

    def test_question_lists_only_the_tools_the_member_may_use(self):
        owner = self.register_owner("Prompt Pharmacy")
        sales_only = self.custom_member(owner, ["log_sale"], "Sales Only")
        owner_tools = allowed_tools("owner", None)
        self.assertIn("list_roles", owner_tools)
        self.assertEqual(set(owner_tools), set(TOOL_SCOPES))
        identity_scopes = ["log_sale"]
        limited = allowed_tools("custom", identity_scopes)
        self.assertNotIn("list_roles", limited)
        self.assertNotIn("search_inventory", limited)
        self.assertNotIn("get_sales_summary", limited)
        self.assertIn("get_my_activity", limited)
        question = build_agent_question("how many?", "English", "custom", identity_scopes)
        self.assertTrue(question.startswith(SYSTEM_PROMPT))
        self.assertIn("- get_my_activity:", question)
        self.assertNotIn("- list_roles:", question)
        self.assertTrue(question.endswith("Answer in English.\nUser question:\nhow many?"))
        self.assertTrue(sales_only["token"])

    def test_every_tool_is_allowed_exactly_when_the_endpoint_answers_not_403(self):
        owner = self.register_owner("Scope Table Pharmacy")
        item_id = self.make_product(owner)
        day = date.today().isoformat()
        calls = {
            "search_inventory": ("get", "/ai/items", None),
            "match_product": ("post", "/ai/match", {"query_name": "Agent"}),
            "get_item_batches": ("get", f"/ai/items/{item_id}/batches", None),
            "get_item_price_history": ("get", f"/ai/items/{item_id}/price-history", None),
            "list_low_stock": ("get", "/ai/low-stock", None),
            "list_categories": ("get", "/ai/categories", None),
            "get_inventory_summary": ("get", "/ai/inventory/summary", None),
            "list_ledger_entries": ("get", "/ai/entries", None),
            "get_sales_summary": ("get", f"/ai/summary?day={day}", None),
            "list_supplier_payables": ("get", "/ai/payables", None),
            "get_payables_summary": ("get", "/ai/payables/summary", None),
            "list_records_timeline": ("get", "/ai/timeline", None),
            "get_my_activity": ("get", "/ai/activity", None),
            "list_roles": ("get", "/ai/roles", None),
        }
        self.assertEqual(set(calls), set(TOOL_SCOPES))
        members = {
            "owner": (owner, "owner", None),
            "cashier": (self.join(owner, {"fixed_role": "cashier"}, "Cashier"), "cashier", None),
            "viewer": (self.join(owner, {"fixed_role": "viewer"}, "Viewer"), "viewer", None),
            "sales_only": (self.custom_member(owner, ["log_sale"], "Sales Only"), "custom", ["log_sale"]),
            "inventory_only": (self.custom_member(owner, ["view_inventory"], "Stock Only"), "custom", ["view_inventory"]),
            "audit_only": (self.custom_member(owner, ["view_audit"], "Audit Only"), "custom", ["view_audit"]),
        }
        for label, (session, role, scopes) in members.items():
            allowed = set(allowed_tools(role, scopes))
            headers = self.ai_headers(session)
            for tool, (method, path, body) in calls.items():
                response = self.client.request(method.upper(), path, headers=headers, json=body)
                self.assertNotIn(response.status_code, (401, 404, 422, 500), f"{label} {tool}: {response.text}")
                self.assertEqual(response.status_code != 403, tool in allowed, f"{label} {tool}")
        # The owner gets every tool.
        self.assertEqual(set(allowed_tools("owner", None)), set(calls))

    # ---- tool results ----
    def test_new_tools_return_only_the_safe_fields_for_the_owner(self):
        owner = self.register_owner("Safe Fields Pharmacy")
        item_id = self.make_product(owner, category="Pain relief")
        headers = self.ai_headers(owner)
        day = date.today().isoformat()

        low = self.client.get("/ai/low-stock", headers=headers)
        self.assertEqual(low.status_code, 200, low.text)
        self.assertEqual([row["id"] for row in low.json()], [item_id])
        self.assertNotIn("unit_buy_price", low.json()[0])

        categories = self.client.get("/ai/categories", headers=headers).json()
        self.assertEqual(categories, [{"name": "Pain relief", "item_count": 1}])

        summary = self.client.get("/ai/inventory/summary", headers=headers).json()
        self.assertEqual(set(summary), NEW_KEYS["inventory_summary"])
        self.assertEqual(summary["item_count"], 1)

        history = self.client.get(f"/ai/items/{item_id}/price-history", headers=headers).json()
        self.assertEqual(len(history), 1)
        self.assertEqual(set(history[0]), NEW_KEYS["price_change"])
        self.assertEqual(history[0]["unit_sell_price"], 12.5)

        sales = self.client.get(f"/ai/summary?day={day}", headers=headers)
        self.assertEqual(sales.status_code, 200, sales.text)
        self.assertEqual(set(sales.json()), NEW_KEYS["summary"])

        timeline = self.client.get("/ai/timeline", headers=headers)
        self.assertEqual(timeline.status_code, 200, timeline.text)
        events = timeline.json()
        self.assertTrue(events)
        for event in events:
            self.assertEqual(set(event), NEW_KEYS["timeline"])
        self.assertIn("CREATE_PRODUCT", {event["kind"] for event in events})

    def test_roles_tool_is_owner_only_and_hides_ids(self):
        owner = self.register_owner("Roles Tool Pharmacy")
        member = self.custom_member(owner, ["view_inventory"], "Stock Reader")
        roles = self.client.get("/ai/roles", headers=self.ai_headers(owner))
        self.assertEqual(roles.status_code, 200, roles.text)
        rows = roles.json()["roles"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(set(rows[0]), NEW_KEYS["role"])
        self.assertEqual(rows[0]["scopes"], ["view_inventory"])
        self.assertEqual(rows[0]["assigned_count"], 1)
        denied = self.client.get("/ai/roles", headers=self.ai_headers(member))
        self.assertEqual(denied.status_code, 403, denied.text)

    def test_timeline_for_a_cashier_never_shows_other_peoples_rows_or_names(self):
        owner = self.register_owner("Timeline Scope Pharmacy")
        self.make_product(owner)
        cashier = self.join(owner, {"fixed_role": "cashier"}, "Cashier Two")
        response = self.client.get("/ai/timeline", headers=self.ai_headers(cashier))
        if response.status_code == 200:
            self.assertEqual(response.json(), [])
        else:
            self.assertEqual(response.status_code, 403, response.text)

    def test_other_pharmacy_sees_nothing_and_cannot_reach_the_first_ones_product(self):
        first = self.register_owner("Isolation One")
        second = self.register_owner("Isolation Two")
        item_id = self.make_product(first, category="Isolated")
        headers = self.ai_headers(second)
        self.assertEqual(self.client.get("/ai/low-stock", headers=headers).json(), [])
        self.assertEqual(self.client.get("/ai/categories", headers=headers).json(), [])
        self.assertEqual(self.client.get("/ai/inventory/summary", headers=headers).json()["item_count"], 0)
        self.assertEqual(self.client.get(f"/ai/items/{item_id}/price-history", headers=headers).status_code, 404)
        roles = self.client.get("/ai/roles", headers=headers).json()["roles"]
        self.assertEqual(roles, [])

    def test_bad_arguments_answer_422_not_500(self):
        owner = self.register_owner("Bad Arguments Pharmacy")
        headers = self.ai_headers(owner)
        for path in (
            "/ai/low-stock?limit=0",
            "/ai/low-stock?limit=51",
            "/ai/items/0/price-history",
            "/ai/timeline?limit=0",
            "/ai/timeline?offset=1001",
            "/ai/summary?day=not-a-date",
            "/ai/summary?day=2026-01-01&start_day=2026-01-01&end_day=2026-01-02",
            "/ai/summary?start_day=2026-01-02&end_day=2026-01-01",
        ):
            response = self.client.get(path, headers=headers)
            self.assertEqual(response.status_code, 422, f"{path}: {response.text}")
        self.assertEqual(self.client.get("/ai/low-stock").status_code, 401)

    def test_ai_token_is_refused_on_the_main_api_and_accepted_on_ai(self):
        owner = self.register_owner("Audience Pharmacy")
        ai_headers = self.ai_headers(owner)
        self.assertIn(self.client.get("/api/inventory/items", headers=ai_headers).status_code, (401, 403))
        self.assertEqual(self.client.get("/ai/categories", headers=ai_headers).status_code, 200)

    # ---- chat: fixed prompt and fallback ----
    def test_agent_path_sends_the_fixed_prompt_and_a_failed_agent_gets_a_plain_note(self):
        owner = self.register_owner("Agent Chat Pharmacy")
        headers = self.auth(owner["token"])
        with patch("server.app.api.chat.settings.AI_TOOLS_ENABLED", True), \
                patch("server.app.api.chat.settings.USE_MICROMIND", True), \
                patch("server.app.services.micromind.micromind_client.query_agent", new_callable=AsyncMock) as agent:
            agent.return_value = {"text": "Agent answer."}
            ok = self.client.post("/api/chat", headers=headers, json={"text": "hello", "language": "en"})
            self.assertEqual(ok.status_code, 200, ok.text)
            self.assertEqual(ok.json()["text"], "Agent answer.")
            question, token = agent.await_args.args
            self.assertTrue(question.startswith(SYSTEM_PROMPT))
            self.assertIn("Tools you may use now:", question)
            self.assertIn("- list_roles:", question)
            self.assertTrue(question.endswith("Answer in English.\nUser question:\nhello"))
            self.assertEqual(decode_access_token(token)["audience"], "ai")
            self.assertNotIn(token, question)

            agent.return_value = None
            failed = self.client.post("/api/chat", headers=headers, json={"text": "hello", "language": "en"})
            self.assertEqual(failed.status_code, 200, failed.text)
            self.assertIn("could not be reached", failed.json()["text"])
            failed_ar = self.client.post("/api/chat", headers=headers, json={"text": "hello", "language": "ar"})
            self.assertIn("تعذّر", failed_ar.json()["text"])

    def test_agent_failure_adds_no_note_while_micromind_is_off(self):
        owner = self.register_owner("Agent Off Pharmacy")
        with patch("server.app.api.chat.settings.AI_TOOLS_ENABLED", True), \
                patch("server.app.api.chat.settings.USE_MICROMIND", False):
            response = self.client.post(
                "/api/chat", headers=self.auth(owner["token"]), json={"text": "hello", "language": "en"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertNotIn("could not be reached", response.json()["text"])


if __name__ == "__main__":
    unittest.main()