# tests/test_category_confirm.py
"""The create-category card end to end (task 9b, step 5b): propose with the /ai tool, then
review, confirm or cancel with the signed-in person's own token. In-memory SQLite.
"""
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


class CategoryConfirmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    # ---- helpers (same style as tests/test_ai_agent_tools.py) ----
    @staticmethod
    def new_phone() -> str:
        return f"09{secrets.randbelow(100_000_000):08d}"

    @staticmethod
    def auth(token: str) -> dict:
        return {"Authorization": f"Bearer {token}"}

    def register_owner(self, name: str) -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Category Owner", "phone": self.new_phone(), "pin": "1234",
            "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def custom_member(self, owner: dict, scopes: list, who: str) -> dict:
        pharmacy_id = owner["pharmacy"]["id"]
        role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles", headers=self.auth(owner["token"]),
            json={"name": f"Role {secrets.token_hex(3)}", "scopes": scopes},
        )
        self.assertEqual(role.status_code, 200, role.text)
        invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations", headers=self.auth(owner["token"]),
            json={"custom_role_id": role.json()["role"]["id"], "max_uses": 1},
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

    def ai_headers(self, session: dict) -> dict:
        identity = decode_access_token(session["token"])
        return self.auth(create_ai_access_token(identity["user_id"], identity["pharmacy_id"]))

    def propose(self, session: dict, name: str, language: str = "en") -> dict:
        response = self.client.post(
            "/ai/propose-category", headers=self.ai_headers(session),
            json={"name": name, "language": language},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def card(self, session: dict, name: str) -> str:
        result = self.propose(session, name)
        self.assertEqual(result["status"], "pending_review", result)
        self.assertTrue(result["proposal_id"].startswith("prop-"))
        return result["proposal_id"]

    def categories(self, session: dict) -> list:
        response = self.client.get("/api/inventory/categories", headers=self.auth(session["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def pending_ids(self, session: dict) -> list:
        response = self.client.get("/api/actions/pending", headers=self.auth(session["token"]))
        self.assertEqual(response.status_code, 200, response.text)
        return [row["id"] for row in response.json()["actions"]]

    # ---- propose ----
    def test_proposing_writes_nothing_until_confirmed(self):
        owner = self.register_owner("Category Propose Pharmacy")
        proposal_id = self.card(owner, "Vitamins")
        self.assertEqual(self.categories(owner), [])
        self.assertIn(proposal_id, self.pending_ids(owner))

    def test_existing_name_is_not_proposed_again(self):
        owner = self.register_owner("Category Duplicate Pharmacy")
        created = self.client.post(
            "/api/inventory/categories", headers=self.auth(owner["token"]), json={"name": "Skin care"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        result = self.propose(owner, "skin   CARE")
        self.assertEqual(result["status"], "not_created")
        self.assertIsNone(result["proposal_id"])

    def test_member_without_manage_inventory_cannot_propose(self):
        owner = self.register_owner("Category Scope Pharmacy")
        reader = self.custom_member(owner, ["view_inventory"], "Reader")
        response = self.client.post(
            "/ai/propose-category", headers=self.ai_headers(reader), json={"name": "Nope", "language": "en"},
        )
        self.assertEqual(response.status_code, 403, response.text)

    def test_extra_fields_and_blank_names_are_refused(self):
        owner = self.register_owner("Category Body Pharmacy")
        headers = self.ai_headers(owner)
        for body in (
            {"name": "A", "pharmacy_id": 1},
            {"name": ""},
            {"name": "x" * 41},
        ):
            response = self.client.post("/ai/propose-category", headers=headers, json=body)
            self.assertEqual(response.status_code, 422, f"{body}: {response.text}")

    def test_at_most_five_cards_wait_per_person(self):
        owner = self.register_owner("Category Limit Pharmacy")
        for number in range(5):
            self.card(owner, f"Limit {number}")
        self.assertEqual(self.propose(owner, "Limit 5")["status"], "not_created")

    # ---- confirm ----
    def test_confirm_creates_the_category_once(self):
        owner = self.register_owner("Category Confirm Pharmacy")
        proposal_id = self.card(owner, "Vitamins")
        headers = self.auth(owner["token"])
        confirmed = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        body = confirmed.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["proposal"]["status"], "confirmed")
        self.assertEqual(body["proposal"]["category_name"], "Vitamins")
        self.assertEqual(self.categories(owner), ["Vitamins"])
        again = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(self.categories(owner), ["Vitamins"])

    def test_edited_name_is_the_one_created(self):
        owner = self.register_owner("Category Edit Pharmacy")
        proposal_id = self.card(owner, "Pain")
        confirmed = self.client.post(
            f"/api/actions/{proposal_id}/confirm", headers=self.auth(owner["token"]),
            json={"category_name": "Pain relief"},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(self.categories(owner), ["Pain relief"])

    def test_name_taken_after_the_card_gives_409_and_the_card_stays_pending(self):
        owner = self.register_owner("Category Race Pharmacy")
        proposal_id = self.card(owner, "Dup A")
        headers = self.auth(owner["token"])
        taken = self.client.post("/api/inventory/categories", headers=headers, json={"name": "Dup A"})
        self.assertEqual(taken.status_code, 200, taken.text)
        confirmed = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 409, confirmed.text)
        self.assertIn(proposal_id, self.pending_ids(owner))
        self.assertEqual(self.categories(owner), ["Dup A"])

    def test_the_ai_token_cannot_confirm_or_cancel(self):
        owner = self.register_owner("Category Audience Pharmacy")
        proposal_id = self.card(owner, "Sealed")
        ai_headers = self.ai_headers(owner)
        for action in ("confirm", "cancel"):
            response = self.client.post(f"/api/actions/{proposal_id}/{action}", headers=ai_headers, json={})
            self.assertIn(response.status_code, (401, 403), f"{action}: {response.text}")
        self.assertEqual(self.categories(owner), [])

    # ---- cancel ----
    def test_cancel_creates_nothing_and_blocks_a_later_confirm(self):
        owner = self.register_owner("Category Cancel Pharmacy")
        proposal_id = self.card(owner, "Dropped")
        headers = self.auth(owner["token"])
        cancelled = self.client.post(f"/api/actions/{proposal_id}/cancel", headers=headers)
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(self.categories(owner), [])
        self.assertNotIn(proposal_id, self.pending_ids(owner))
        late = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(late.status_code, 409, late.text)

    # ---- creator only ----
    def test_only_the_member_who_prepared_the_card_can_see_confirm_or_cancel_it(self):
        owner = self.register_owner("Category Creator Pharmacy")
        other = self.custom_member(owner, ["manage_inventory"], "Other Manager")
        proposal_id = self.card(owner, "Private card")
        other_headers = self.auth(other["token"])
        self.assertNotIn(proposal_id, self.pending_ids(other))
        confirm = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=other_headers, json={})
        self.assertEqual(confirm.status_code, 403, confirm.text)
        cancel = self.client.post(f"/api/actions/{proposal_id}/cancel", headers=other_headers)
        self.assertEqual(cancel.status_code, 403, cancel.text)
        self.assertEqual(self.categories(owner), [])
        self.assertIn(proposal_id, self.pending_ids(owner))
        done = self.client.post(
            f"/api/actions/{proposal_id}/confirm", headers=self.auth(owner["token"]), json={},
        )
        self.assertEqual(done.status_code, 200, done.text)

    def test_another_pharmacy_cannot_reach_the_card(self):
        first = self.register_owner("Category Tenant One")
        second = self.register_owner("Category Tenant Two")
        proposal_id = self.card(first, "Tenant card")
        response = self.client.post(
            f"/api/actions/{proposal_id}/confirm", headers=self.auth(second["token"]), json={},
        )
        self.assertEqual(response.status_code, 404, response.text)


if __name__ == "__main__":
    unittest.main()