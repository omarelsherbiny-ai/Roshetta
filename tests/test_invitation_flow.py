# tests/test_invitation_flow.py
"""Invitation path for a person who joins a pharmacy through a link (Session 109, W4).

Covers: a stranger registers and accepts, then holds only that role's scopes; expired,
used-up, revoked, unknown and malformed links; a link opened by an already signed-in
pharmacy session; an existing phone number (sign in, then accept); a role removed before
use; and a member who is already active. Uses an in-memory SQLite database."""

import os
import secrets
import unittest
from datetime import timedelta
from unittest.mock import patch

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app
from server.app.services.clock import utc_now_naive

ACCEPT = "/api/pharmacies/invitations/accept"


class InvitationFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    @staticmethod
    def new_phone() -> str:
        return f"09{secrets.randbelow(100_000_000):08d}"

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def register_owner(self, name: str = "Invite Flow Pharmacy") -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Flow Owner", "phone": self.new_phone(), "pin": "1234",
            "pharmacy_name": name, "address": "Private address",
            "license_number": "LICENSE-PRIVATE", "tax_id": "TAX-PRIVATE",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def register_account(self, name: str = "Flow Stranger", phone: str | None = None) -> dict:
        response = self.client.post("/api/auth/register-user", json={
            "name": name, "phone": phone or self.new_phone(), "pin": "2468", "language_pref": "ar",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def invite(self, owner: dict, **body) -> dict:
        body.setdefault("max_uses", 1)
        if "custom_role_id" not in body:
            body.setdefault("fixed_role", "cashier")
        response = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations",
            headers=self.auth(owner["token"]), json=body,
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def accept(self, token: str, invite_token: str):
        return self.client.post(ACCEPT, headers=self.auth(token), json={"token": invite_token})

    def invitation_row(self, owner: dict, invitation_id: int) -> dict:
        listed = self.client.get(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations", headers=self.auth(owner["token"])
        )
        self.assertEqual(listed.status_code, 200, listed.text)
        return next(row for row in listed.json() if row["id"] == invitation_id)

    def test_stranger_registers_accepts_and_holds_only_the_invited_role(self):
        owner = self.register_owner("Stranger Path Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        invitation = self.invite(owner, fixed_role="cashier")
        # The token travels in the #fragment, which browsers never send to a server.
        self.assertEqual(invitation["join_path"], f"/onboarding#invite={invitation['token']}")
        self.assertNotIn("?", invitation["join_path"])

        phone = self.new_phone()
        account = self.register_account("New Cashier", phone)
        accepted = self.accept(account["token"], invitation["token"])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["scope"], "pharmacy")
        self.assertEqual(accepted.json()["pharmacy_id"], pharmacy_id)
        self.assertEqual(accepted.json()["role"], "cashier")

        headers = self.auth(accepted.json()["token"])
        self.assertEqual(self.client.get("/api/inventory/items", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/auth/staff", headers=headers).status_code, 403)
        self.assertEqual(self.client.get(f"/api/pharmacies/{pharmacy_id}/roles", headers=headers).status_code, 403)
        self.assertEqual(self.client.get(f"/api/pharmacies/{pharmacy_id}/invitations", headers=headers).status_code, 403)
        profile = self.client.get("/api/auth/profile", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        for private in ("owner_name", "phone", "license_number", "tax_id"):
            self.assertNotIn(private, profile.json())

        # Signing in later lands in the same pharmacy with the same role.
        login = self.client.post("/api/auth/login", json={"phone": phone, "pin": "2468"})
        self.assertEqual(login.status_code, 200, login.text)
        self.assertEqual(login.json()["pharmacy"]["id"], pharmacy_id)
        self.assertEqual(login.json()["role"], "cashier")

        row = self.invitation_row(owner, invitation["invitation_id"])
        self.assertEqual(row["used_count"], 1)
        self.assertFalse(row["is_active"])

    def test_expired_link_is_refused_and_not_consumed(self):
        owner = self.register_owner("Expired Link Pharmacy")
        invitation = self.invite(owner)
        account = self.register_account("Late Joiner")
        with patch("server.app.api.staff.utc_now_naive", return_value=utc_now_naive() + timedelta(days=8)):
            late = self.accept(account["token"], invitation["token"])
        self.assertEqual(late.status_code, 404, late.text)
        self.assertEqual(self.invitation_row(owner, invitation["invitation_id"])["used_count"], 0)
        # Inside its lifetime the same link still works: the refusal changed nothing.
        self.assertEqual(self.accept(account["token"], invitation["token"]).status_code, 200)

    def test_used_up_link_is_refused_for_the_next_person(self):
        owner = self.register_owner("Used Up Pharmacy")
        single = self.invite(owner, max_uses=1)
        first, second = self.register_account("First"), self.register_account("Second")
        self.assertEqual(self.accept(first["token"], single["token"]).status_code, 200)
        self.assertEqual(self.accept(second["token"], single["token"]).status_code, 404)

        double = self.invite(owner, max_uses=2)
        accounts = [self.register_account(f"Two Use {index}") for index in range(3)]
        self.assertEqual(self.accept(accounts[0]["token"], double["token"]).status_code, 200)
        self.assertEqual(self.accept(accounts[1]["token"], double["token"]).status_code, 200)
        self.assertEqual(self.accept(accounts[2]["token"], double["token"]).status_code, 404)
        row = self.invitation_row(owner, double["invitation_id"])
        self.assertEqual((row["used_count"], row["is_active"]), (2, False))

    def test_revoked_link_is_refused_and_only_its_own_pharmacy_can_revoke(self):
        owner = self.register_owner("Revoke Pharmacy")
        stranger_owner = self.register_owner("Other Revoke Pharmacy")
        invitation = self.invite(owner)
        route = f"/api/pharmacies/{owner['pharmacy']['id']}/invitations/{invitation['invitation_id']}"
        self.assertEqual(self.client.delete(route, headers=self.auth(stranger_owner["token"])).status_code, 404)
        self.assertEqual(self.client.delete(route, headers=self.auth(owner["token"])).status_code, 200)
        account = self.register_account("Too Late")
        refused = self.accept(account["token"], invitation["token"])
        self.assertEqual(refused.status_code, 404, refused.text)
        self.assertFalse(self.invitation_row(owner, invitation["invitation_id"])["is_active"])

    def test_unknown_malformed_and_unauthenticated_accepts_are_refused(self):
        account = self.register_account("Guesser")
        self.assertEqual(self.accept(account["token"], secrets.token_urlsafe(32)).status_code, 404)
        self.assertEqual(self.accept(account["token"], "short").status_code, 422)
        self.assertEqual(self.accept(account["token"], "x" * 129).status_code, 422)
        self.assertEqual(self.client.post(ACCEPT, json={"token": secrets.token_urlsafe(32)}).status_code, 401)

    def test_a_pharmacy_session_cannot_accept_before_returning_to_the_hub(self):
        owner = self.register_owner("Signed In Accept Pharmacy")
        other = self.register_owner("Signed In Target Pharmacy")
        invitation = self.invite(other)
        refused = self.accept(owner["token"], invitation["token"])
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(self.invitation_row(other, invitation["invitation_id"])["used_count"], 0)

        # After returning to the account hub the same person can accept.
        hub = self.client.post("/api/auth/account-scope", headers=self.auth(owner["token"]))
        self.assertEqual(hub.status_code, 200, hub.text)
        accepted = self.accept(hub.json()["token"], invitation["token"])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["pharmacy_id"], other["pharmacy"]["id"])

    def test_existing_phone_number_signs_in_then_accepts(self):
        owner = self.register_owner("Existing Phone Pharmacy")
        invitation = self.invite(owner, fixed_role="viewer")
        phone = self.new_phone()
        self.register_account("Already Registered", phone)

        # The registration form is refused for a known number; the client then signs in.
        duplicate = self.client.post("/api/auth/register-user", json={
            "name": "Again", "phone": phone, "pin": "2468", "language_pref": "ar",
        })
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        signed_in = self.client.post("/api/auth/account-login", json={"phone": phone, "pin": "2468"})
        self.assertEqual(signed_in.status_code, 200, signed_in.text)
        accepted = self.accept(signed_in.json()["token"], invitation["token"])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["role"], "viewer")
        self.assertEqual(self.client.get("/api/inventory/items", headers=self.auth(accepted.json()["token"])).status_code, 403)

    def test_role_removed_before_use_blocks_the_link_without_consuming_it(self):
        owner = self.register_owner("Dead Role Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        headers = self.auth(owner["token"])
        role = self.client.post(f"/api/pharmacies/{pharmacy_id}/roles", headers=headers, json={
            "name": "Short Lived", "scopes": ["view_inventory"],
        })
        self.assertEqual(role.status_code, 200, role.text)
        role_id = role.json()["role"]["id"]
        invitation = self.invite(owner, custom_role_id=role_id)
        # Nobody holds the role yet, so it can be deactivated.
        self.assertEqual(self.client.delete(f"/api/pharmacies/{pharmacy_id}/roles/{role_id}", headers=headers).status_code, 200)
        account = self.register_account("Orphaned Invitee")
        refused = self.accept(account["token"], invitation["token"])
        self.assertEqual(refused.status_code, 409, refused.text)
        self.assertEqual(self.invitation_row(owner, invitation["invitation_id"])["used_count"], 0)
        memberships = self.client.get("/api/pharmacies", headers=self.auth(account["token"]))
        self.assertEqual(memberships.json()["pharmacies"], [])

    def test_custom_role_link_gives_exactly_the_role_scopes(self):
        owner = self.register_owner("Custom Scope Link Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        role = self.client.post(f"/api/pharmacies/{pharmacy_id}/roles", headers=self.auth(owner["token"]), json={
            "name": "Stock Viewer", "scopes": ["view_inventory"],
        })
        self.assertEqual(role.status_code, 200, role.text)
        invitation = self.invite(owner, custom_role_id=role.json()["role"]["id"])
        account = self.register_account("Stock Viewer Person")
        accepted = self.accept(account["token"], invitation["token"])
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual((accepted.json()["role"], accepted.json()["role_name"]), ("custom", "Stock Viewer"))
        headers = self.auth(accepted.json()["token"])
        self.assertEqual(self.client.get("/api/inventory/items", headers=headers).status_code, 200)
        self.assertEqual(self.client.get("/api/ledger/entries", headers=headers).status_code, 403)

    def test_an_active_member_cannot_reuse_a_link_and_does_not_burn_a_use(self):
        owner = self.register_owner("Active Member Pharmacy")
        invitation = self.invite(owner, max_uses=5)
        account = self.register_account("Already Inside")
        self.assertEqual(self.accept(account["token"], invitation["token"]).status_code, 200)
        again = self.accept(account["token"], invitation["token"])
        self.assertEqual(again.status_code, 409, again.text)
        row = self.invitation_row(owner, invitation["invitation_id"])
        self.assertEqual((row["used_count"], row["is_active"]), (1, True))


if __name__ == "__main__":
    unittest.main()