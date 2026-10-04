# tests/test_api_security.py
"""API security integration tests using an in-memory SQLite database."""

import os
import secrets
import unittest
from datetime import date, datetime
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo


# Set test configuration before importing the application. This keeps the test
# suite off any developer database and prevents external service calls.
os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient

from server.app.main import app


class PharmacyAPISecurityTests(unittest.TestCase):
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

    def register_owner(self, pharmacy_name: str = "Test Pharmacy") -> dict:
        response = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Test Owner",
            "phone": self.new_phone(),
            "pin": "1234",
            "pharmacy_name": pharmacy_name,
            "address": "Private address",
            "license_number": "LICENSE-PRIVATE",
            "tax_id": "TAX-PRIVATE",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def join_cashier(self, owner: dict) -> dict:
        pharmacy_id = owner["pharmacy"]["id"]
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=self.auth(owner["token"]),
            json={"fixed_role": "cashier", "max_uses": 1},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account = self.register_personal_account("Test Cashier")
        response = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": invitation.json()["token"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        joined = response.json()
        joined["user"] = account["user"]
        return joined

    def register_personal_account(self, name: str = "Personal User") -> dict:
        response = self.client.post("/api/auth/register-user", json={
            "name": name,
            "phone": self.new_phone(),
            "pin": "2468",
            "language_pref": "ar",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def test_health_reports_disabled_external_integrations_accurately(self):
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["micromind_configured"])
        self.assertFalse(response.json()["micromind_enabled"])
        self.assertFalse(response.json()["ocr_available"])

    def test_micromind_is_only_called_for_general_chat(self):
        owner = self.register_owner("MicroMind Data-Minimization Pharmacy")
        headers = self.auth(owner["token"])
        unsupported_language = self.client.post("/api/chat", headers=headers, json={
            "text": "hello",
            "language": "fr",
        })
        self.assertEqual(unsupported_language.status_code, 422, unsupported_language.text)

        with patch("server.app.services.micromind.settings.USE_MICROMIND", True), \
                patch("server.app.services.micromind.settings.AI_TOOLS_ENABLED", False), \
                patch("server.app.services.micromind.micromind_client.query", new_callable=AsyncMock) as query:
            query.return_value = {"text": "General answer from configured assistant."}
            stock = self.client.post("/api/chat", headers=headers, json={
                "text": "show stock",
                "language": "en",
            })
            self.assertEqual(stock.status_code, 200, stock.text)
            query.assert_not_awaited()

            general = self.client.post("/api/chat", headers=headers, json={
                "text": "hello",
                "language": "en",
            })
            self.assertEqual(general.status_code, 200, general.text)
            query.assert_awaited_once_with({"question": "Answer in English.\nUser question:\nhello"})
            self.assertEqual(general.json()["text"], "General answer from configured assistant.")

            arabic = self.client.post("/api/chat", headers=headers, json={
                "text": "hello",
                "language": "ar",
            })
            self.assertEqual(arabic.status_code, 200, arabic.text)
            query.assert_any_await({"question": "Answer in Arabic.\nUser question:\nhello"})
            self.assertEqual(query.await_count, 2)

    def test_stock_chat_response_uses_requested_locale_and_real_inventory(self):
        owner = self.register_owner("Localized Inventory Chat Pharmacy")
        headers = self.auth(owner["token"])
        created = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول",
            "name_en": "Panadol",
            "stock_qty": 2,
            "min_threshold": 5,
            "unit_buy_price": 10,
            "unit_sell_price": 12,
        })
        self.assertEqual(created.status_code, 200, created.text)

        english = self.client.post("/api/chat", headers=headers, json={
            "text": "show stock",
            "language": "en",
        })
        self.assertEqual(english.status_code, 200, english.text)
        self.assertIn("Panadol", english.json()["text"])
        self.assertIn("current stock: 2 units", english.json()["text"])

        arabic = self.client.post("/api/chat", headers=headers, json={
            "text": "عرض المخزون",
            "language": "ar",
        })
        self.assertEqual(arabic.status_code, 200, arabic.text)
        self.assertIn("بنادول", arabic.json()["text"])
        self.assertIn("الرصيد الحالي: 2 وحدة", arabic.json()["text"])

    def test_personal_account_pharmacy_hub_and_five_owned_limit(self):
        account = self.register_personal_account()
        headers = self.auth(account["token"])
        self.assertEqual(account["scope"], "account")
        self.assertNotIn("pharmacy", account)

        initial = self.client.get("/api/pharmacies", headers=headers)
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(initial.json(), {"pharmacies": [], "owned_count": 0, "owned_limit": 5})
        self.assertEqual(self.client.get("/api/inventory/items", headers=headers).status_code, 409)

        created = []
        for index in range(5):
            response = self.client.post("/api/pharmacies", headers=headers, json={
                "pharmacy_name": f"Owned Pharmacy {index + 1}",
                "address": f"Address {index + 1}",
            })
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["pharmacy"]["currency"], "EGP")
            created.append(response.json()["pharmacy"])

        full = self.client.get("/api/pharmacies", headers=headers)
        self.assertEqual(full.status_code, 200, full.text)
        self.assertEqual(full.json()["owned_count"], 5)
        self.assertEqual(len(full.json()["pharmacies"]), 5)
        over_limit = self.client.post("/api/pharmacies", headers=headers, json={"pharmacy_name": "Sixth Pharmacy"})
        self.assertEqual(over_limit.status_code, 409, over_limit.text)

        selected = self.client.post(f"/api/pharmacies/{created[0]['id']}/select", headers=headers)
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertEqual(selected.json()["scope"], "pharmacy")
        self.assertEqual(selected.json()["pharmacy"]["pharmacy_name"], "Owned Pharmacy 1")
        return_to_hub = self.client.post("/api/auth/account-scope", headers=self.auth(selected.json()["token"]))
        self.assertEqual(return_to_hub.status_code, 200, return_to_hub.text)
        self.assertEqual(return_to_hub.json()["scope"], "account")
        self.assertEqual(self.client.get(
            "/api/auth/profile", headers=self.auth(selected.json()["token"])
        ).status_code, 401)
        self.assertEqual(self.client.get(
            "/api/pharmacies", headers=self.auth(return_to_hub.json()["token"])
        ).json()["owned_count"], 5)

    def test_pharmacy_created_without_optional_fields_reads_them_back_empty(self):
        # Session 52 (c): a pharmacy made without address, license and tax ID must not
        # inherit the demo values that used to be column defaults.
        demo_values = {"EG-PH-88921", "TR-4432190", "شارع التحرير، الدقي، الجيزة"}
        account = self.register_personal_account("No Optional Fields Owner")
        created = self.client.post(
            "/api/pharmacies",
            headers=self.auth(account["token"]),
            json={"pharmacy_name": "Bare Pharmacy"},
        )
        self.assertEqual(created.status_code, 200, created.text)
        self.assertFalse(created.json()["pharmacy"]["address"])

        selected = self.client.post(
            f"/api/pharmacies/{created.json()['pharmacy']['id']}/select",
            headers=self.auth(account["token"]),
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        self.assertFalse(selected.json()["pharmacy"]["address"])

        profile = self.client.get("/api/auth/profile", headers=self.auth(selected.json()["token"]))
        self.assertEqual(profile.status_code, 200, profile.text)
        for field in ("address", "license_number", "tax_id"):
            self.assertIn(field, profile.json())
            self.assertFalse(profile.json()[field], f"{field} should be empty: {profile.json()[field]!r}")
            self.assertNotIn(profile.json()[field], demo_values)

    def test_personal_profile_updates_and_explicitly_clears_optional_fields(self):
        account = self.register_personal_account("Profile User")
        headers = self.auth(account["token"])
        updated = self.client.patch("/api/auth/me", headers=headers, json={
            "name": "Updated Profile User",
            "location": "Cairo",
            "photo_url": "https://example.test/profile.png",
            "birth_date": "1990-05-12",
            "language_pref": "en",
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["user"]["name"], "Updated Profile User")
        self.assertEqual(updated.json()["user"]["location"], "Cairo")
        self.assertEqual(updated.json()["user"]["birth_date"], "1990-05-12")

        cleared = self.client.patch("/api/auth/me", headers=headers, json={
            "location": None,
            "photo_url": None,
            "birth_date": None,
        })
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["user"]["location"])
        self.assertIsNone(cleared.json()["user"]["photo_url"])
        self.assertIsNone(cleared.json()["user"]["birth_date"])
        self.assertEqual(cleared.json()["user"]["name"], "Updated Profile User")

        future_date = self.client.patch("/api/auth/me", headers=headers, json={"birth_date": "2999-01-01"})
        self.assertEqual(future_date.status_code, 422)
        insecure_photo = self.client.patch("/api/auth/me", headers=headers, json={"photo_url": "http://example.test/profile.png"})
        self.assertEqual(insecure_photo.status_code, 422)

    def test_my_profile_birth_date_is_strict_and_empty_values_clear_fields(self):
        # Session 52 (e): PATCH /api/me takes only strict YYYY-MM-DD, never a future
        # date, and an empty string clears birth_date or location.
        account = self.register_personal_account("Strict Profile User")
        headers = self.auth(account["token"])

        saved = self.client.patch("/api/me", headers=headers, json={
            "birth_date": "1990-05-12",
            "location": "Cairo",
        })
        self.assertEqual(saved.status_code, 200, saved.text)
        self.assertEqual(saved.json()["user"]["birth_date"], "1990-05-12")
        self.assertEqual(saved.json()["user"]["location"], "Cairo")

        for bad_date in ("1990-5-12", "2026-1-5", "12/05/1990", "1990-02-30", "not-a-date", "2999-01-01"):
            rejected = self.client.patch("/api/me", headers=headers, json={"birth_date": bad_date})
            self.assertEqual(rejected.status_code, 422, f"{bad_date!r}: {rejected.text}")

        unchanged = self.client.get("/api/me", headers=headers)
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json()["user"]["birth_date"], "1990-05-12")

        cleared = self.client.patch("/api/me", headers=headers, json={"birth_date": "", "location": ""})
        self.assertEqual(cleared.status_code, 200, cleared.text)
        self.assertIsNone(cleared.json()["user"]["birth_date"])
        self.assertIsNone(cleared.json()["user"]["location"])
        self.assertEqual(cleared.json()["user"]["name"], "Strict Profile User")

    def test_account_hub_profile_and_activity_responses_match_declared_contracts(self):
        owner = self.register_owner("Account Hub Pharmacy")
        headers = self.auth(owner["token"])
        profile = self.client.get("/api/me", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["pharmacy_count"], 1)
        self.assertEqual(profile.json()["pharmacy_ids"], [owner["pharmacy"]["id"]])

        updated = self.client.patch("/api/me", headers=headers, json={
            "name": "Account Hub Owner",
            "language_pref": "en",
        })
        self.assertEqual(updated.status_code, 200, updated.text)
        self.assertEqual(updated.json()["user"]["name"], "Account Hub Owner")

        activity = self.client.get("/api/me/activity?period=all", headers=headers)
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(activity.json()["period"], "all")
        self.assertEqual(activity.json()["pharmacy_id"], owner["pharmacy"]["id"])

    def test_account_accepts_owner_invitation_and_receives_pharmacy_scope(self):
        owner = self.register_owner("Invitation Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=self.auth(owner["token"]),
            json={"fixed_role": "cashier", "max_uses": 1},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)

        account = self.register_personal_account("Invited User")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["scope"], "pharmacy")
        self.assertEqual(accepted.json()["pharmacy_id"], pharmacy_id)
        self.assertEqual(accepted.json()["pharmacy"]["pharmacy_name"], "Invitation Pharmacy")

        memberships = self.client.get("/api/pharmacies", headers=self.auth(accepted.json()["token"]))
        self.assertEqual(memberships.status_code, 200, memberships.text)
        self.assertEqual(len(memberships.json()["pharmacies"]), 1)
        self.assertFalse(memberships.json()["pharmacies"][0]["is_owner"])

    def test_fresh_invitation_reactivates_previously_removed_staff_membership(self):
        owner = self.register_owner("Reinvitation Pharmacy")
        owner_headers = self.auth(owner["token"])
        pharmacy_id = owner["pharmacy"]["id"]
        first_invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"fixed_role": "cashier"},
        )
        self.assertEqual(first_invite.status_code, 200, first_invite.text)

        account = self.register_personal_account("Returning Employee")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": first_invite.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        user_id = account["user"]["id"]

        removed = self.client.delete(f"/api/pharmacies/{pharmacy_id}/staff/{user_id}", headers=owner_headers)
        self.assertEqual(removed.status_code, 200, removed.text)
        second_invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"fixed_role": "pharmacist"},
        )
        self.assertEqual(second_invite.status_code, 200, second_invite.text)
        reaccepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": second_invite.json()["token"]},
        )
        self.assertEqual(reaccepted.status_code, 200, reaccepted.text)
        self.assertEqual(reaccepted.json()["role"], "pharmacist")

        memberships = self.client.get("/api/pharmacies", headers=self.auth(account["token"]))
        self.assertEqual(memberships.status_code, 200, memberships.text)
        self.assertEqual(len(memberships.json()["pharmacies"]), 1)
        self.assertEqual(memberships.json()["pharmacies"][0]["role"], "pharmacist")

    def test_personal_activity_feed_only_returns_actions_by_the_current_user(self):
        owner = self.register_owner("Activity Isolation Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"fixed_role": "cashier"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)

        account = self.register_personal_account("Activity Feed Employee")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)

        owner_activity = self.client.get("/api/staff/me/activity", headers=owner_headers)
        employee_activity = self.client.get(
            "/api/staff/me/activity", headers=self.auth(accepted.json()["token"])
        )
        self.assertEqual(owner_activity.status_code, 200, owner_activity.text)
        self.assertEqual(employee_activity.status_code, 200, employee_activity.text)
        owner_actions = {entry["action_type"] for entry in owner_activity.json()}
        employee_actions = {entry["action_type"] for entry in employee_activity.json()}
        self.assertIn("CREATE_PHARMACY_INVITATION", owner_actions)
        self.assertNotIn("ACCEPT_PHARMACY_INVITATION", owner_actions)
        self.assertIn("ACCEPT_PHARMACY_INVITATION", employee_actions)
        self.assertNotIn("CREATE_PHARMACY_INVITATION", employee_actions)
        self.assertTrue(all(
            entry["pharmacy_id"] in (None, pharmacy_id)
            for entry in employee_activity.json()
        ))

    def test_custom_role_scopes_cannot_grant_owner_capabilities(self):
        owner = self.register_owner("Custom Role Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])

        forbidden_role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles",
            headers=owner_headers,
            json={"name": "Escalated", "scopes": ["log_sale", "manage_roles"]},
        )
        self.assertEqual(forbidden_role.status_code, 422, forbidden_role.text)

        role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles",
            headers=owner_headers,
            json={"name": "Sales Only", "scopes": ["log_sale"]},
        )
        self.assertEqual(role.status_code, 200, role.text)
        role_id = role.json()["role"]["id"]
        available_scopes = self.client.get(
            f"/api/pharmacies/{pharmacy_id}/roles", headers=owner_headers
        ).json()["available_scopes"]
        self.assertIn("view_staff_activity", available_scopes)
        invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"custom_role_id": role_id, "max_uses": 1},
        )
        self.assertEqual(invite.status_code, 200, invite.text)

        account = self.register_personal_account("Limited Staff")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": invite.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        staff_headers = self.auth(accepted.json()["token"])
        self.assertEqual(self.client.get("/api/inventory/items", headers=staff_headers).status_code, 403)
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/roles", headers=staff_headers
        ).status_code, 403)
        self.assertIn("permission", self.client.post(
            "/api/chat", headers=staff_headers,
            json={"text": "show stock", "language": "en"},
        ).json()["text"].lower())
        self.assertIn("permission", self.client.post(
            "/api/chat", headers=staff_headers,
            json={"text": "sales today", "language": "en"},
        ).json()["text"].lower())
        disallowed_sale = self.client.post(
            "/api/chat", headers=staff_headers,
            json={"text": "sold two panadol", "language": "en"},
        )
        self.assertIsNone(disallowed_sale.json()["proposal"])
        self.assertIn("permission", disallowed_sale.json()["text"].lower())
        self.assertEqual(self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{owner['user']['id']}/role",
            headers=owner_headers,
            json={"custom_role_id": role_id},
        ).status_code, 409)
        self.assertEqual(self.client.post(
            f"/api/pharmacies/{pharmacy_id}/staff/{account['user']['id']}/compensation",
            headers=staff_headers,
            json={"pay_type": "monthly", "amount": 1000, "currency": "EGP"},
        ).status_code, 403)

    def test_delegated_staff_scope_cannot_use_legacy_pin_issuing_invite(self):
        owner = self.register_owner("Delegated Staff Scope Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])
        role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles",
            headers=owner_headers,
            json={"name": "Staff Manager", "scopes": ["manage_staff", "edit_settings"]},
        )
        self.assertEqual(role.status_code, 200, role.text)
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"custom_role_id": role.json()["role"]["id"]},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        manager_account = self.register_personal_account("Delegated Staff Manager")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(manager_account["token"]),
            json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)

        manager_headers = self.auth(accepted.json()["token"])
        retired_invite = self.client.post("/api/auth/invite", headers=self.auth(owner["token"]), json={})
        self.assertEqual(retired_invite.status_code, 410, retired_invite.text)
        self.assertEqual(self.client.post("/api/auth/join", json={}).status_code, 410)
        self.assertEqual(self.client.post(
            "/api/auth/refresh-invite-code", headers=self.auth(owner["token"])
        ).status_code, 410)
        response = self.client.post("/api/auth/invite", headers=manager_headers, json={
            "name": "Must Not Be Created",
            "phone": self.new_phone(),
            "role": "cashier",
        })
        self.assertEqual(response.status_code, 403, response.text)
        self.assertNotIn("initial_pin", response.json())
        self.assertEqual(self.client.post(
            "/api/auth/refresh-invite-code", headers=manager_headers
        ).status_code, 403)
        manager_profile = self.client.get("/api/auth/profile", headers=manager_headers)
        self.assertEqual(manager_profile.status_code, 200, manager_profile.text)
        self.assertNotIn("invite_code", manager_profile.json())
        manager_login = self.client.post("/api/auth/login", json={
            "phone": manager_account["user"]["phone"],
            "pin": "2468",
        })
        self.assertEqual(manager_login.status_code, 200, manager_login.text)
        self.assertNotIn("invite_code", manager_login.json()["pharmacy"])

    def join_custom_manager(self, owner: dict, role_name: str, scopes: list[str]) -> dict:
        """Create a custom role with the given scopes and join a new account to it."""
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])
        role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles", headers=owner_headers,
            json={"name": role_name, "scopes": scopes},
        )
        self.assertEqual(role.status_code, 200, role.text)
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations", headers=owner_headers,
            json={"custom_role_id": role.json()["role"]["id"]},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account = self.register_personal_account(role_name)
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept", headers=self.auth(account["token"]),
            json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return {"headers": self.auth(accepted.json()["token"]), "user_id": account["user"]["id"]}

    def test_staff_manager_cannot_self_promote_or_grant_roles_it_does_not_hold(self):
        owner = self.register_owner("Escalation Guard Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])
        manager = self.join_custom_manager(owner, "Lite Staff Manager", ["manage_staff", "view_reports"])
        cashier = self.join_cashier(owner)
        cashier_id = cashier["user"]["id"]

        # Self-promotion is blocked, even to a role the manager could otherwise grant.
        for role in ("pharmacist", "viewer"):
            self.assertEqual(self.client.patch(
                f"/api/pharmacies/{pharmacy_id}/staff/{manager['user_id']}/role",
                headers=manager["headers"], json={"role": role},
            ).status_code, 403, role)

        # Granting a role that carries permissions the manager lacks is blocked.
        for role in ("pharmacist", "cashier"):
            self.assertEqual(self.client.post(
                f"/api/pharmacies/{pharmacy_id}/invitations",
                headers=manager["headers"], json={"fixed_role": role},
            ).status_code, 403, role)
        self.assertEqual(self.client.patch(
            f"/api/pharmacies/{pharmacy_id}/staff/{cashier_id}/role",
            headers=manager["headers"], json={"role": "pharmacist"},
        ).status_code, 403)

        # A role whose permissions the manager holds (viewer = view_reports) may be invited.
        self.assertEqual(self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=manager["headers"], json={"fixed_role": "viewer"},
        ).status_code, 200)
        # But the manager may not change a member who holds more than the manager does
        # (Session 109, W5): a cashier has log_sale and more, the manager has neither.
        self.assertEqual(self.client.patch(
            f"/api/pharmacies/{pharmacy_id}/staff/{cashier_id}/role",
            headers=manager["headers"], json={"role": "viewer"},
        ).status_code, 403)

        # The owner is never restricted.
        self.assertEqual(self.client.patch(
            f"/api/pharmacies/{pharmacy_id}/staff/{cashier_id}/role",
            headers=owner_headers, json={"role": "pharmacist"},
        ).status_code, 200)

    def test_staff_manager_can_grant_a_built_in_role_whose_permissions_it_holds(self):
        owner = self.register_owner("Escalation Guard Allowed Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        # view_inventory is implied by manage_inventory, like has_permission treats it.
        manager = self.join_custom_manager(
            owner, "Full Cashier Manager",
            ["manage_staff", "log_sale", "log_expense", "view_reports", "manage_inventory"],
        )
        invitation = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=manager["headers"], json={"fixed_role": "cashier"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        # Still cannot reach pharmacist: log_restock, view_audit and the rest are not held.
        self.assertEqual(self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=manager["headers"], json={"fixed_role": "pharmacist"},
        ).status_code, 403)

    def test_staff_schedule_validation_and_compensation_privacy(self):
        owner = self.register_owner("Staff Terms Pharmacy")
        pharmacy_id = owner["pharmacy"]["id"]
        owner_headers = self.auth(owner["token"])
        invite = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/invitations",
            headers=owner_headers,
            json={"fixed_role": "cashier", "max_uses": 1},
        )
        account = self.register_personal_account("Staff Terms User")
        accepted = self.client.post(
            "/api/pharmacies/invitations/accept",
            headers=self.auth(account["token"]),
            json={"token": invite.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        staff_id = account["user"]["id"]
        staff_headers = self.auth(accepted.json()["token"])
        self.assertEqual(self.client.get(
            "/api/staff/me/summary", headers=staff_headers
        ).status_code, 200)
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/staff/{owner['user']['id']}/summary",
            headers=staff_headers,
        ).status_code, 403)
        activity_role = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/roles",
            headers=owner_headers,
            json={"name": "Activity Reviewer", "scopes": ["view_staff_activity"]},
        )
        self.assertEqual(activity_role.status_code, 200, activity_role.text)
        assigned_role = self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/role",
            headers=owner_headers,
            json={"custom_role_id": activity_role.json()["role"]["id"]},
        )
        self.assertEqual(assigned_role.status_code, 200, assigned_role.text)
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/staff/{owner['user']['id']}/summary",
            headers=staff_headers,
        ).status_code, 200)
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/summary",
            headers=owner_headers,
        ).status_code, 200)

        invalid_currency = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/compensation",
            headers=owner_headers,
            json={"pay_type": "monthly", "amount": 12000, "currency": "USD"},
        )
        self.assertEqual(invalid_currency.status_code, 422, invalid_currency.text)
        saved_terms = self.client.post(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/compensation",
            headers=owner_headers,
            json={"pay_type": "monthly", "amount": 12000, "currency": "EGP"},
        )
        self.assertEqual(saved_terms.status_code, 200, saved_terms.text)
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/compensation",
            headers=staff_headers,
        ).json()[0]["currency"], "EGP")
        self.assertEqual(self.client.get(
            f"/api/pharmacies/{pharmacy_id}/staff/{owner['user']['id']}/compensation",
            headers=staff_headers,
        ).status_code, 403)

        overlapping = [
            {"day_of_week": 1, "start_time": "09:00", "end_time": "13:00", "timezone": "Africa/Cairo"},
            {"day_of_week": 1, "start_time": "12:00", "end_time": "16:00", "timezone": "Africa/Cairo"},
        ]
        rejected = self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
            headers=owner_headers,
            json={"shifts": overlapping},
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        mixed_timezones = [
            {"day_of_week": 1, "start_time": "09:00", "end_time": "13:00", "timezone": "Africa/Cairo"},
            {"day_of_week": 2, "start_time": "09:00", "end_time": "13:00", "timezone": "Europe/London"},
        ]
        self.assertEqual(self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
            headers=owner_headers,
            json={"shifts": mixed_timezones},
        ).status_code, 422)
        separate_periods = [
            {"day_of_week": 1, "start_time": "09:00", "end_time": "13:00", "timezone": "Africa/Cairo", "effective_from": "2026-01-01", "effective_until": "2026-06-30"},
            {"day_of_week": 1, "start_time": "09:00", "end_time": "13:00", "timezone": "Africa/Cairo", "effective_from": "2026-07-01", "effective_until": "2026-12-31"},
        ]
        accepted_periods = self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
            headers=owner_headers,
            json={"shifts": separate_periods},
        )
        self.assertEqual(accepted_periods.status_code, 200, accepted_periods.text)
        self.assertEqual(accepted_periods.json()["shift_count"], 2)

        zone_name = next((zone for zone in ("Pacific/Kiritimati", "Pacific/Pago_Pago")
                          if datetime.now(ZoneInfo(zone)).date() != date.today()), None)
        if zone_name is not None:
            defaulted = self.client.put(
                f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
                headers=owner_headers,
                json={"shifts": [{
                    "day_of_week": 3,
                    "start_time": "09:00",
                    "end_time": "13:00",
                    "timezone": zone_name,
                }]},
            )
            self.assertEqual(defaulted.status_code, 200, defaulted.text)
            current_schedule = self.client.get(
                f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
                headers=owner_headers,
            )
            self.assertEqual(current_schedule.status_code, 200, current_schedule.text)
            self.assertEqual(
                current_schedule.json()[0]["effective_from"],
                datetime.now(ZoneInfo(zone_name)).date().isoformat(),
            )

        self.assertEqual(self.client.put(
            f"/api/pharmacies/{pharmacy_id}/staff/{staff_id}/schedule",
            headers=staff_headers,
            json={"shifts": []},
        ).status_code, 403)

    def test_non_owner_auth_and_profile_payloads_omit_private_pharmacy_fields(self):
        owner = self.register_owner()
        private_fields = {"owner_name", "phone", "license_number", "tax_id"}
        self.assertTrue((private_fields | {"address"}).issubset(owner["pharmacy"]))
        self.assertNotIn("invite_code", owner["pharmacy"])

        joined = self.join_cashier(owner)
        self.assertTrue(private_fields.isdisjoint(joined["pharmacy"]))
        headers = self.auth(joined["token"])

        profile = self.client.get("/api/auth/profile", headers=headers)
        self.assertEqual(profile.status_code, 200, profile.text)
        self.assertEqual(profile.json()["pharmacy_name"], owner["pharmacy"]["pharmacy_name"])
        self.assertTrue(private_fields.isdisjoint(profile.json()))
        owner_profile = self.client.get("/api/auth/profile", headers=self.auth(owner["token"]))
        self.assertNotIn("invite_code", owner_profile.json())

        login = self.client.post("/api/auth/login", json={
            "phone": joined["user"]["phone"],
            "pin": "2468",
        })
        self.assertEqual(login.status_code, 200, login.text)
        self.assertTrue(private_fields.isdisjoint(login.json()["pharmacy"]))

    def test_pharmacy_profile_cannot_change_currency_away_from_egp(self):
        owner = self.register_owner("Currency Integrity Pharmacy")
        headers = self.auth(owner["token"])
        rejected = self.client.post(
            "/api/auth/profile", headers=headers, json={"currency": "SAR"}
        )
        self.assertEqual(rejected.status_code, 422, rejected.text)
        accepted = self.client.post(
            "/api/auth/profile", headers=headers, json={"currency": "EGP"}
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(self.client.get("/api/auth/profile", headers=headers).json()["currency"], "EGP")

    def test_cashier_cannot_access_owner_settings_or_clinical_records(self):
        owner = self.register_owner()
        cashier = self.join_cashier(owner)
        headers = self.auth(cashier["token"])

        self.assertEqual(self.client.get("/api/auth/staff", headers=headers).status_code, 403)
        self.assertEqual(self.client.post(
            "/api/auth/profile", json={"pharmacy_name": "Changed"}, headers=headers
        ).status_code, 403)
        self.assertEqual(self.client.get("/api/ocr/prescriptions", headers=headers).status_code, 403)
        self.assertEqual(self.client.post(
            "/api/ocr/product-box",
            files={"file": ("box.jpg", b"not an image", "image/jpeg")},
            headers=headers,
        ).status_code, 403)
        self.assertEqual(self.client.post(
            "/api/ocr/scan",
            data={"document_type": "prescription"},
            files={"file": ("prescription.jpg", b"not an image", "image/jpeg")},
            headers=headers,
        ).status_code, 403)

    def test_pharmacy_data_isolated_and_logout_revokes_the_session(self):
        first = self.register_owner("First Pharmacy")
        second = self.register_owner("Second Pharmacy")
        first_headers = self.auth(first["token"])
        second_headers = self.auth(second["token"])

        created = self.client.post("/api/inventory/create", headers=first_headers, json={
            "name_ar": "اختبار",
            "name_en": "Isolation Test Product",
            "stock_qty": 2,
            "unit_buy_price": 1,
            "unit_sell_price": 2,
        })
        self.assertEqual(created.status_code, 200, created.text)
        product_id = created.json()["item"]["id"]
        stock_edit = self.client.put(
            f"/api/inventory/items/{product_id}",
            headers=first_headers,
            json={
                "name_ar": "اختبار",
                "name_en": "Isolation Test Product",
                "stock_qty": 3,
                "min_threshold": 1,
                "unit_buy_price": 1,
                "unit_sell_price": 2,
            },
        )
        self.assertEqual(stock_edit.status_code, 409, stock_edit.text)
        self.assertEqual(self.client.get(
            f"/api/inventory/items/{product_id}", headers=first_headers
        ).json()["stock_qty"], 2)
        self.assertEqual(self.client.get(
            f"/api/inventory/items/{product_id}", headers=second_headers
        ).status_code, 404)
        self.assertEqual(self.client.get(
            "/api/ocr/uploads/private-upload-key", headers=second_headers
        ).status_code, 404)

        signed_out = self.client.post("/api/auth/logout", headers=first_headers)
        self.assertEqual(signed_out.status_code, 200, signed_out.text)
        self.assertEqual(self.client.get("/api/auth/profile", headers=first_headers).status_code, 401)

    def test_product_price_changes_are_historic_and_tenant_scoped(self):
        first = self.register_owner("Price History Pharmacy")
        second = self.register_owner("Other Price Pharmacy")
        first_headers = self.auth(first["token"])
        second_headers = self.auth(second["token"])
        product = self.client.post("/api/inventory/create", headers=first_headers, json={
            "name_ar": "صنف اختبار الأسعار",
            "name_en": "Price History Product",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 10.25,
            "unit_sell_price": 12.5,
        })
        self.assertEqual(product.status_code, 200, product.text)
        product_id = product.json()["item"]["id"]

        initial = self.client.get(
            f"/api/inventory/items/{product_id}/price-history", headers=first_headers
        )
        self.assertEqual(initial.status_code, 200, initial.text)
        self.assertEqual(len(initial.json()), 1)
        self.assertIsNone(initial.json()[0]["previous_unit_sell_price"])
        self.assertEqual(initial.json()[0]["unit_sell_price"], 12.5)

        update = self.client.put(f"/api/inventory/items/{product_id}", headers=first_headers, json={
            "name_ar": "صنف اختبار الأسعار",
            "name_en": "Price History Product",
            "min_threshold": 1,
            "unit_buy_price": 10.75,
            "unit_sell_price": 13.25,
        })
        self.assertEqual(update.status_code, 200, update.text)
        history = self.client.get(
            f"/api/inventory/items/{product_id}/price-history", headers=first_headers
        ).json()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["previous_unit_sell_price"], 12.5)
        self.assertEqual(history[0]["unit_sell_price"], 13.25)
        self.assertEqual(history[0]["changed_by"], first["user"]["id"])
        self.assertEqual(self.client.get(
            f"/api/inventory/items/{product_id}/price-history", headers=second_headers
        ).status_code, 404)

        attempted_stock_edit = self.client.put(f"/api/inventory/items/{product_id}", headers=first_headers, json={
            "name_ar": "صنف اختبار الأسعار",
            "name_en": "Price History Product",
            "stock_qty": 5,
            "min_threshold": 1,
            "unit_buy_price": 10.75,
            "unit_sell_price": 13.25,
        })
        self.assertEqual(attempted_stock_edit.status_code, 409, attempted_stock_edit.text)
        unchanged = self.client.get(f"/api/inventory/items/{product_id}", headers=first_headers)
        self.assertEqual(unchanged.json()["stock_qty"], 0)

    def test_inventory_categories_are_database_backed_and_tenant_scoped(self):
        first = self.register_owner("Category Pharmacy")
        second = self.register_owner("Other Category Pharmacy")
        first_headers = self.auth(first["token"])
        second_headers = self.auth(second["token"])

        for category in ("Pain relief", "all"):
            created = self.client.post("/api/inventory/create", headers=first_headers, json={
                "name_ar": f"صنف {category}",
                "name_en": f"Product {category}",
                "category": category,
                "stock_qty": 0,
                "min_threshold": 1,
                "unit_buy_price": 1,
                "unit_sell_price": 2,
            })
            self.assertEqual(created.status_code, 200, created.text)

        self.assertEqual(self.client.get(
            "/api/inventory/categories", headers=first_headers
        ).json(), ["all", "Pain relief"])
        self.assertEqual(self.client.get(
            "/api/inventory/items?category=all", headers=first_headers
        ).json()[0]["category"], "all")
        self.assertEqual(self.client.get(
            "/api/inventory/categories", headers=second_headers
        ).json(), [])

        uncategorized = self.client.post("/api/inventory/create", headers=second_headers, json={
            "name_ar": "صنف بلا فئة",
            "name_en": "Uncategorized product",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 1,
            "unit_sell_price": 2,
        })
        self.assertEqual(uncategorized.status_code, 200, uncategorized.text)
        self.assertIsNone(uncategorized.json()["item"]["category"])

    def test_inventory_search_and_match_treat_blank_and_wildcards_literally(self):
        # Session 52 (f): a blank match query finds nothing, and a typed % or _ is
        # matched as that character, not as a SQL wildcard.
        owner = self.register_owner("Wildcard Search Pharmacy")
        headers = self.auth(owner["token"])
        for name_ar, name_en in (
            ("صنف أول", "Zinc 50%"),
            ("صنف ثاني", "Zinc 500"),
            ("صنف ثالث", "Vit_C Tabs"),
            ("صنف رابع", "VitaXC Tabs"),
        ):
            created = self.client.post("/api/inventory/create", headers=headers, json={
                "name_ar": name_ar,
                "name_en": name_en,
                "stock_qty": 1,
                "min_threshold": 1,
                "unit_buy_price": 1,
                "unit_sell_price": 2,
            })
            self.assertEqual(created.status_code, 200, created.text)

        def searched(term: str) -> list[str]:
            response = self.client.get("/api/inventory/items", headers=headers, params={"search": term})
            self.assertEqual(response.status_code, 200, response.text)
            return sorted(item["name_en"] for item in response.json())

        self.assertEqual(searched("50%"), ["Zinc 50%"])
        self.assertEqual(searched("%"), ["Zinc 50%"])
        self.assertEqual(searched("Vit_C"), ["Vit_C Tabs"])
        self.assertEqual(searched("_"), ["Vit_C Tabs"])

        def matched(term: str) -> dict:
            response = self.client.post("/api/inventory/match", headers=headers, json={"query_name": term})
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()

        for blank in ("", "   "):
            result = matched(blank)
            self.assertFalse(result["found"], blank)
            self.assertIsNone(result.get("matched_item"))
            self.assertEqual(result.get("suggestions"), [])

        literal_underscore = matched("Vit_C")
        self.assertTrue(literal_underscore["found"])
        self.assertEqual(literal_underscore["matched_item"]["name_en"], "Vit_C Tabs")
        self.assertEqual(literal_underscore["alternatives"], [])

        literal_percent = matched("50%")
        self.assertTrue(literal_percent["found"])
        self.assertEqual(literal_percent["matched_item"]["name_en"], "Zinc 50%")
        self.assertEqual(literal_percent["alternatives"], [])

        wildcards_only = matched("%%")
        self.assertFalse(wildcards_only["found"])
        self.assertEqual(wildcards_only.get("suggestions"), [])

    def test_inventory_summary_is_pharmacy_scoped_and_flags_missing_cost_data(self):
        owner = self.register_owner("Inventory Summary Pharmacy")
        headers = self.auth(owner["token"])
        create_known_cost = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "صنف بسعر شراء",
            "name_en": "Known cost item",
            "stock_qty": 3,
            "unit_buy_price": 2,
            "unit_sell_price": 5,
        })
        self.assertEqual(create_known_cost.status_code, 200, create_known_cost.text)
        known = self.client.get("/api/inventory/summary", headers=headers)
        self.assertEqual(known.status_code, 200, known.text)
        self.assertEqual(known.json(), {
            "item_count": 1,
            "total_units": 3.0,
            "potential_sales_value": 15.0,
            "stock_cost_value": 6.0,
            "stock_cost_value_complete": True,
        })

        create_missing_cost = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "صنف بلا سعر شراء",
            "name_en": "Missing cost item",
            "stock_qty": 2,
            "unit_sell_price": 4,
        })
        self.assertEqual(create_missing_cost.status_code, 200, create_missing_cost.text)
        incomplete = self.client.get("/api/inventory/summary", headers=headers)
        self.assertEqual(incomplete.status_code, 200, incomplete.text)
        self.assertEqual(incomplete.json()["item_count"], 2)
        self.assertEqual(incomplete.json()["total_units"], 5.0)
        self.assertEqual(incomplete.json()["potential_sales_value"], 23.0)
        self.assertIsNone(incomplete.json()["stock_cost_value"])
        self.assertFalse(incomplete.json()["stock_cost_value_complete"])

        another_owner = self.register_owner("Other Inventory Summary Pharmacy")
        foreign = self.client.post("/api/inventory/create", headers=self.auth(another_owner["token"]), json={
            "name_ar": "منتج آخر",
            "name_en": "Another pharmacy item",
            "stock_qty": 100,
            "unit_buy_price": 1,
            "unit_sell_price": 2,
        })
        self.assertEqual(foreign.status_code, 200, foreign.text)
        unchanged = self.client.get("/api/inventory/summary", headers=headers)
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        self.assertEqual(unchanged.json(), incomplete.json())

    def test_pending_proposal_recovery_is_tenant_scoped_and_confirmation_updates_stock(self):
        first = self.register_owner("Action Pharmacy")
        second = self.register_owner("Other Pharmacy")
        first_headers = self.auth(first["token"])
        second_headers = self.auth(second["token"])

        created = self.client.post("/api/inventory/create", headers=first_headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 4,
            "min_threshold": 1,
            "unit_buy_price": 28,
            "unit_sell_price": 35,
        })
        self.assertEqual(created.status_code, 200, created.text)

        chat = self.client.post("/api/chat", headers=first_headers, json={
            "text": "sold panadol extra",
            "language": "en",
        })
        self.assertEqual(chat.status_code, 200, chat.text)
        proposal = chat.json()["proposal"]
        self.assertIsNotNone(proposal)
        proposal_id = proposal["id"]

        first_pending = self.client.get("/api/actions/pending", headers=first_headers)
        second_pending = self.client.get("/api/actions/pending", headers=second_headers)
        self.assertEqual(first_pending.status_code, 200, first_pending.text)
        self.assertEqual(second_pending.status_code, 200, second_pending.text)
        self.assertEqual([item["id"] for item in first_pending.json()["actions"]], [proposal_id])
        self.assertEqual(
            first_pending.json()["actions"][0]["items"][0]["subtotal"],
            first_pending.json()["actions"][0]["items"][0]["quantity"]
            * first_pending.json()["actions"][0]["items"][0]["unit_price"],
        )
        self.assertEqual(second_pending.json()["actions"], [])

        confirmed = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=first_headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertEqual(confirmed.json()["proposal"]["status"], "confirmed")
        duplicate = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=first_headers, json={})
        self.assertEqual(duplicate.status_code, 409)

        updated = self.client.get(
            f"/api/inventory/items/{created.json()['item']['id']}", headers=first_headers
        )
        self.assertEqual(updated.json()["stock_qty"], 3)

    def test_confirmed_restock_updates_stock_and_staff_summary(self):
        owner = self.register_owner("Restock Summary Pharmacy")
        headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 28,
            "unit_sell_price": 35,
        })
        self.assertEqual(product.status_code, 200, product.text)

        proposal = self.client.post("/api/chat", headers=headers, json={
            "text": "restock 3 Panadol Extra",
            "language": "en",
        })
        self.assertEqual(proposal.status_code, 200, proposal.text)
        self.assertEqual(proposal.json()["proposal"]["action_type"], "log_restock")
        action_id = proposal.json()["proposal"]["id"]
        confirmed = self.client.post(f"/api/actions/{action_id}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        inventory = self.client.get(
            f"/api/inventory/items/{product.json()['item']['id']}", headers=headers
        )
        self.assertEqual(inventory.json()["stock_qty"], 3)
        # A confirmed assistant restock is a lot too, so lots add up to the stock.
        batches = self.client.get(
            f"/api/inventory/items/{product.json()['item']['id']}/batches", headers=headers
        )
        self.assertEqual(batches.status_code, 200, batches.text)
        self.assertEqual([batch["quantity"] for batch in batches.json()], [3])
        self.assertEqual(batches.json()[0]["unit_buy_price"], 28)
        summary = self.client.get("/api/staff/me/summary?days=365", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["restock_count"], 1)
        self.assertEqual(summary.json()["restocked_quantity"], 3)
        self.assertEqual(summary.json()["restock_amount"], 84)

    def test_direct_restock_validates_inputs_and_writes_batch_and_ledger(self):
        owner = self.register_owner("Restock Validation Pharmacy")
        headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "دواء اختبار",
            "name_en": "Restock Test Medicine",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 10,
            "unit_sell_price": 15,
        })
        self.assertEqual(product.status_code, 200, product.text)
        item_id = product.json()["item"]["id"]
        route = f"/api/inventory/items/{item_id}/restock"

        invalid_date = self.client.post(route, headers=headers, json={
            "quantity": 1,
            "expiry_date": "2027-02-30",
        })
        self.assertEqual(invalid_date.status_code, 422, invalid_date.text)
        long_batch_number = self.client.post(route, headers=headers, json={
            "quantity": 1,
            "batch_number": "B" * 61,
        })
        self.assertEqual(long_batch_number.status_code, 422, long_batch_number.text)

        accepted = self.client.post(route, headers=headers, json={
            "quantity": 2,
            "unit_buy_price": 12,
            "unit_sell_price": 18,
            "batch_number": "BATCH-OK",
            "expiry_date": "2027-12-31",
        })
        self.assertEqual(accepted.status_code, 200, accepted.text)
        self.assertEqual(accepted.json()["new_stock"], 2)
        batches = self.client.get(f"/api/inventory/items/{item_id}/batches", headers=headers)
        self.assertEqual(batches.status_code, 200, batches.text)
        self.assertEqual(batches.json()[0]["batch_number"], "BATCH-OK")
        self.assertEqual(batches.json()[0]["expiry_date"], "2027-12-31")
        entries = self.client.get("/api/ledger/entries", headers=headers)
        self.assertEqual(entries.status_code, 200, entries.text)
        self.assertEqual([entry["entry_type"] for entry in entries.json()], ["log_restock"])
        first_restock_entry = entries.json()[0]
        self.assertEqual(first_restock_entry["total_amount"], 24)
        self.assertEqual(first_restock_entry["items"][0]["unit_price"], 12)
        self.assertEqual(first_restock_entry["items"][0]["subtotal"], 24)
        price_history = self.client.get(
            f"/api/inventory/items/{item_id}/price-history", headers=headers
        )
        self.assertEqual(price_history.status_code, 200, price_history.text)
        self.assertEqual(len(price_history.json()), 2)
        self.assertEqual(price_history.json()[0]["previous_unit_buy_price"], 10)
        self.assertEqual(price_history.json()[0]["unit_buy_price"], 12)
        self.assertEqual(price_history.json()[0]["previous_unit_sell_price"], 15)
        self.assertEqual(price_history.json()[0]["unit_sell_price"], 18)

        zero_cost_restock = self.client.post(route, headers=headers, json={
            "quantity": 1,
            "unit_buy_price": 0,
            "batch_number": "FREE-LOT",
        })
        self.assertEqual(zero_cost_restock.status_code, 200, zero_cost_restock.text)
        self.assertEqual(zero_cost_restock.json()["total_cost"], 0)
        batches = self.client.get(f"/api/inventory/items/{item_id}/batches", headers=headers)
        self.assertEqual(batches.json()[1]["unit_buy_price"], 0)
        latest_entry = self.client.get("/api/ledger/entries", headers=headers).json()[0]
        self.assertEqual(latest_entry["total_amount"], 0)
        self.assertEqual(latest_entry["items"][0]["subtotal"], 0)
        self.assertEqual(latest_entry["items"][0]["unit_price"], 0)

    def test_staff_summary_credits_the_employee_who_confirms_the_sale(self):
        owner = self.register_owner("Confirmed Work Attribution Pharmacy")
        owner_headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=owner_headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 4,
            "min_threshold": 1,
            "unit_buy_price": 28,
            "unit_sell_price": 35,
        })
        self.assertEqual(product.status_code, 200, product.text)
        proposal = self.client.post("/api/chat", headers=owner_headers, json={
            "text": "sold panadol extra",
            "language": "en",
        })
        self.assertEqual(proposal.status_code, 200, proposal.text)

        cashier = self.join_cashier(owner)
        cashier_headers = self.auth(cashier["token"])
        action_id = proposal.json()["proposal"]["id"]
        confirmed = self.client.post(f"/api/actions/{action_id}/confirm", headers=cashier_headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        owner_summary = self.client.get("/api/staff/me/summary?days=365", headers=owner_headers)
        cashier_summary = self.client.get("/api/staff/me/summary?days=365", headers=cashier_headers)
        self.assertEqual(owner_summary.status_code, 200, owner_summary.text)
        self.assertEqual(cashier_summary.status_code, 200, cashier_summary.text)
        self.assertEqual(owner_summary.json()["sales_count"], 0)
        self.assertEqual(cashier_summary.json()["sales_count"], 1)
        self.assertEqual(cashier_summary.json()["sold_quantity"], 1)
        # "days=1" is today in Cairo, so a sale confirmed just now is inside it.
        cashier_today = self.client.get("/api/staff/me/summary?days=1", headers=cashier_headers)
        self.assertEqual(cashier_today.status_code, 200, cashier_today.text)
        self.assertEqual(cashier_today.json()["sales_count"], 1)
        cashier_financials = self.client.get("/api/ledger/daily-summary", headers=cashier_headers)
        self.assertEqual(cashier_financials.status_code, 200, cashier_financials.text)
        self.assertEqual(cashier_financials.json()["total_sales"], 35)
        cashier_entries = self.client.get("/api/ledger/entries", headers=cashier_headers)
        self.assertEqual(cashier_entries.status_code, 200, cashier_entries.text)
        self.assertEqual([entry["entry_type"] for entry in cashier_entries.json()], ["log_sale"])

    def test_sale_with_unknown_purchase_cost_does_not_report_zero_cost_profit(self):
        owner = self.register_owner("Unknown Cost Pharmacy")
        headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 2,
            "min_threshold": 1,
            "unit_sell_price": 50,
        })
        self.assertEqual(product.status_code, 200, product.text)
        proposal = self.client.post("/api/chat", headers=headers, json={
            "text": "sold panadol extra",
            "language": "en",
        })
        self.assertEqual(proposal.status_code, 200, proposal.text)
        action_id = proposal.json()["proposal"]["id"]
        confirmed = self.client.post(f"/api/actions/{action_id}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        summary = self.client.get("/api/ledger/daily-summary", headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["total_sales"], 35)
        self.assertFalse(summary.json()["profit_complete"])
        self.assertIsNone(summary.json()["cost_of_goods"])
        self.assertIsNone(summary.json()["gross_profit"])
        self.assertIsNone(summary.json()["net_profit"])

    def test_catalog_expiry_follows_the_earliest_lot_with_stock(self):
        owner = self.register_owner("Earliest Expiry Pharmacy")
        headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 1,
            "min_threshold": 1,
            "unit_buy_price": 28,
            "unit_sell_price": 35,
            "expiry_date": "2027-01-01",
        })
        self.assertEqual(product.status_code, 200, product.text)
        item_id = product.json()["item"]["id"]
        item_route = f"/api/inventory/items/{item_id}"

        def catalog_expiry() -> str:
            response = self.client.get(item_route, headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            return response.json()["expiry_date"]

        # A later-expiring lot must not hide the earlier one that still has stock.
        later = self.client.post(f"{item_route}/restock", headers=headers, json={
            "quantity": 5,
            "expiry_date": "2027-06-01",
        })
        self.assertEqual(later.status_code, 200, later.text)
        self.assertEqual(catalog_expiry(), "2027-01-01")

        # A direct restock without an expiry keeps the date and its lot has none.
        undated = self.client.post(f"{item_route}/restock", headers=headers, json={"quantity": 1})
        self.assertEqual(undated.status_code, 200, undated.text)
        self.assertEqual(catalog_expiry(), "2027-01-01")

        # A confirmed assistant restock adds an undated lot and keeps the date too.
        proposal = self.client.post("/api/chat", headers=headers, json={
            "text": "restock 3 Panadol Extra",
            "language": "en",
        })
        self.assertEqual(proposal.status_code, 200, proposal.text)
        self.assertEqual(proposal.json()["proposal"]["action_type"], "log_restock")
        restocked = self.client.post(
            f"/api/actions/{proposal.json()['proposal']['id']}/confirm", headers=headers, json={}
        )
        self.assertEqual(restocked.status_code, 200, restocked.text)
        self.assertEqual(catalog_expiry(), "2027-01-01")
        batches = self.client.get(f"{item_route}/batches", headers=headers).json()
        self.assertEqual(
            [batch["expiry_date"] for batch in batches],
            ["2027-01-01", "2027-06-01", None, None],
        )

        # Selling out the early lot moves the catalog date to the next lot with stock.
        sale = self.client.post("/api/chat", headers=headers, json={
            "text": "sold panadol extra",
            "language": "en",
        })
        self.assertEqual(sale.status_code, 200, sale.text)
        self.assertEqual(sale.json()["proposal"]["action_type"], "log_sale")
        sold = self.client.post(
            f"/api/actions/{sale.json()['proposal']['id']}/confirm", headers=headers, json={}
        )
        self.assertEqual(sold.status_code, 200, sold.text)
        batches = self.client.get(f"{item_route}/batches", headers=headers).json()
        self.assertEqual(batches[0]["quantity"], 0)
        self.assertEqual(catalog_expiry(), "2027-06-01")

    def test_product_edit_expiry_changes_the_lot_that_supplies_the_shown_date(self):
        owner = self.register_owner("Edit Expiry Pharmacy")
        headers = self.auth(owner["token"])

        def edit_payload(expiry_date: str) -> dict:
            return {
                "name_ar": "دواء اختبار",
                "name_en": "Edit Expiry Medicine",
                "min_threshold": 1,
                "unit_buy_price": 10,
                "unit_sell_price": 15,
                "expiry_date": expiry_date,
            }

        product = self.client.post("/api/inventory/create", headers=headers, json={
            **edit_payload("2027-01-01"),
            "stock_qty": 2,
        })
        self.assertEqual(product.status_code, 200, product.text)
        item_id = product.json()["item"]["id"]
        item_route = f"/api/inventory/items/{item_id}"
        later = self.client.post(f"{item_route}/restock", headers=headers, json={
            "quantity": 3,
            "expiry_date": "2027-06-01",
        })
        self.assertEqual(later.status_code, 200, later.text)

        # Typing a new date edits the earliest lot, not the later one.
        edited = self.client.put(item_route, headers=headers, json=edit_payload("2027-02-15"))
        self.assertEqual(edited.status_code, 200, edited.text)
        self.assertEqual(edited.json()["item"]["expiry_date"], "2027-02-15")
        batches = self.client.get(f"{item_route}/batches", headers=headers).json()
        self.assertEqual([batch["expiry_date"] for batch in batches], ["2027-02-15", "2027-06-01"])

        # Saving the form again with the shown date changes nothing.
        unchanged = self.client.put(item_route, headers=headers, json=edit_payload("2027-02-15"))
        self.assertEqual(unchanged.status_code, 200, unchanged.text)
        batches = self.client.get(f"{item_route}/batches", headers=headers).json()
        self.assertEqual([batch["expiry_date"] for batch in batches], ["2027-02-15", "2027-06-01"])

        # Moving that lot past the other one makes the other lot the shown date.
        pushed = self.client.put(item_route, headers=headers, json=edit_payload("2027-09-01"))
        self.assertEqual(pushed.status_code, 200, pushed.text)
        self.assertEqual(pushed.json()["item"]["expiry_date"], "2027-06-01")
        batches = self.client.get(f"{item_route}/batches", headers=headers).json()
        self.assertEqual([batch["expiry_date"] for batch in batches], ["2027-09-01", "2027-06-01"])

        # With no stock in any lot only the product's own date changes.
        empty = self.client.post("/api/inventory/create", headers=headers, json={
            **edit_payload("2027-01-01"),
            "name_en": "Edit Expiry Medicine, no stock",
        })
        self.assertEqual(empty.status_code, 200, empty.text)
        empty_id = empty.json()["item"]["id"]
        edited_empty = self.client.put(
            f"/api/inventory/items/{empty_id}", headers=headers, json={
                **edit_payload("2027-05-05"),
                "name_en": "Edit Expiry Medicine, no stock",
            },
        )
        self.assertEqual(edited_empty.status_code, 200, edited_empty.text)
        self.assertEqual(edited_empty.json()["item"]["expiry_date"], "2027-05-05")
        self.assertEqual(
            self.client.get(f"/api/inventory/items/{empty_id}/batches", headers=headers).json(), []
        )

    def test_ledger_entries_paging_type_filter_and_cashier_scope(self):
        owner = self.register_owner("Ledger Paging Pharmacy")
        owner_headers = self.auth(owner["token"])
        product = self.client.post("/api/inventory/create", headers=owner_headers, json={
            "name_ar": "بنادول اكسترا (أحمر)",
            "name_en": "Panadol Extra (Red)",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 28,
            "unit_sell_price": 35,
        })
        self.assertEqual(product.status_code, 200, product.text)
        item_id = product.json()["item"]["id"]
        for _ in range(3):
            restock = self.client.post(
                f"/api/inventory/items/{item_id}/restock",
                headers=owner_headers,
                json={"quantity": 1, "unit_buy_price": 28},
            )
            self.assertEqual(restock.status_code, 200, restock.text)

        # One sale, proposed by the owner and confirmed by a cashier.
        proposal = self.client.post("/api/chat", headers=owner_headers, json={
            "text": "sold panadol extra",
            "language": "en",
        })
        self.assertEqual(proposal.status_code, 200, proposal.text)
        cashier = self.join_cashier(owner)
        cashier_headers = self.auth(cashier["token"])
        confirmed = self.client.post(
            f"/api/actions/{proposal.json()['proposal']['id']}/confirm",
            headers=cashier_headers,
            json={},
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        route = "/api/ledger/entries"
        everything = self.client.get(f"{route}?limit=100", headers=owner_headers)
        self.assertEqual(everything.status_code, 200, everything.text)
        all_ids = [entry["id"] for entry in everything.json()]
        self.assertEqual(len(all_ids), 4)
        self.assertEqual(len(set(all_ids)), 4)

        # Pages of two rows reproduce the full list in the same order, with no repeats.
        first_page = self.client.get(f"{route}?limit=2&offset=0", headers=owner_headers)
        second_page = self.client.get(f"{route}?limit=2&offset=2", headers=owner_headers)
        self.assertEqual(first_page.status_code, 200, first_page.text)
        self.assertEqual(second_page.status_code, 200, second_page.text)
        self.assertEqual(
            [entry["id"] for entry in first_page.json()] + [entry["id"] for entry in second_page.json()],
            all_ids,
        )
        beyond_end = self.client.get(f"{route}?limit=2&offset=4", headers=owner_headers)
        self.assertEqual(beyond_end.status_code, 200, beyond_end.text)
        self.assertEqual(beyond_end.json(), [])
        negative_offset = self.client.get(f"{route}?offset=-1", headers=owner_headers)
        self.assertEqual(negative_offset.status_code, 422, negative_offset.text)

        # The type filter runs on the server across the whole range, and combines with paging.
        restocks = self.client.get(f"{route}?entry_type=log_restock&limit=100", headers=owner_headers)
        self.assertEqual(restocks.status_code, 200, restocks.text)
        self.assertEqual([entry["entry_type"] for entry in restocks.json()], ["log_restock"] * 3)
        sales = self.client.get(f"{route}?entry_type=log_sale&limit=100", headers=owner_headers)
        self.assertEqual([entry["entry_type"] for entry in sales.json()], ["log_sale"])
        expenses = self.client.get(f"{route}?entry_type=log_expense&limit=100", headers=owner_headers)
        self.assertEqual(expenses.status_code, 200, expenses.text)
        self.assertEqual(expenses.json(), [])
        restock_tail = self.client.get(f"{route}?entry_type=log_restock&limit=2&offset=2", headers=owner_headers)
        self.assertEqual(len(restock_tail.json()), 1)
        unknown_type = self.client.get(f"{route}?entry_type=refund", headers=owner_headers)
        self.assertEqual(unknown_type.status_code, 422, unknown_type.text)

        # A cashier still sees only the entries they confirmed, whatever the offset or filter.
        cashier_all = self.client.get(f"{route}?limit=100", headers=cashier_headers)
        self.assertEqual([entry["entry_type"] for entry in cashier_all.json()], ["log_sale"])
        cashier_page_two = self.client.get(f"{route}?limit=100&offset=1", headers=cashier_headers)
        self.assertEqual(cashier_page_two.json(), [])
        cashier_restocks = self.client.get(f"{route}?entry_type=log_restock&limit=100", headers=cashier_headers)
        self.assertEqual(cashier_restocks.status_code, 200, cashier_restocks.text)
        self.assertEqual(cashier_restocks.json(), [])
        cashier_sales = self.client.get(f"{route}?entry_type=log_sale&limit=100", headers=cashier_headers)
        self.assertEqual([entry["entry_type"] for entry in cashier_sales.json()], ["log_sale"])

    def create_credit_restocks(self, headers, *lots):
        """Creates one product and one direct (credit) restock per (quantity, unit price) lot."""
        product = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "منتج مستحقات",
            "name_en": "Payables Product",
            "stock_qty": 0,
            "min_threshold": 1,
            "unit_buy_price": 20,
            "unit_sell_price": 30,
        })
        self.assertEqual(product.status_code, 200, product.text)
        item_id = product.json()["item"]["id"]
        for quantity, unit_price in lots:
            restock = self.client.post(
                f"/api/inventory/items/{item_id}/restock",
                headers=headers,
                json={"quantity": quantity, "unit_buy_price": unit_price},
            )
            self.assertEqual(restock.status_code, 200, restock.text)
        return item_id

    def test_supplier_payables_track_settlements_and_enforce_limits(self):
        owner = self.register_owner("Payables Pharmacy")
        headers = self.auth(owner["token"])
        self.create_credit_restocks(headers, (10, 20), (5, 10))  # totals 200 and 50

        listed = self.client.get("/api/ledger/payables?limit=100", headers=headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        rows = listed.json()
        self.assertEqual([row["total_amount"] for row in rows], [50.0, 200.0])
        for row in rows:
            self.assertEqual(row["status"], "unpaid")
            self.assertEqual(row["paid_amount"], 0.0)
            self.assertEqual(row["remaining_amount"], row["total_amount"])
            self.assertEqual(row["settlements"], [])
            self.assertIsNone(row["supplier_name"])
            self.assertTrue(row["confirmed_by_name"])
            self.assertEqual(len(row["items"]), 1)
        small_id, big_id = rows[0]["id"], rows[1]["id"]

        summary_route = "/api/ledger/payables/summary"
        summary = self.client.get(summary_route, headers=headers)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["total_remaining"], 250.0)
        self.assertEqual(
            (summary.json()["open_count"], summary.json()["unpaid_count"],
             summary.json()["partly_paid_count"], summary.json()["paid_count"]),
            (2, 2, 0, 0),
        )

        route = f"/api/ledger/entries/{big_id}/settlements"
        partial = self.client.post(route, headers=headers, json={"amount": 80, "payment_method": "cash"})
        self.assertEqual(partial.status_code, 200, partial.text)
        self.assertEqual(partial.json()["status"], "partly_paid")
        self.assertEqual(partial.json()["paid_amount"], 80.0)
        self.assertEqual(partial.json()["remaining_amount"], 120.0)
        self.assertEqual(len(partial.json()["settlements"]), 1)
        self.assertEqual(partial.json()["settlements"][0]["amount"], 80.0)
        self.assertEqual(partial.json()["settlements"][0]["payment_method"], "cash")
        self.assertTrue(partial.json()["settlements"][0]["paid_by_name"])
        summary = self.client.get(summary_route, headers=headers).json()
        self.assertEqual(summary["total_remaining"], 170.0)
        self.assertEqual((summary["open_count"], summary["unpaid_count"], summary["partly_paid_count"]), (2, 1, 1))

        # Invalid payments are refused and change nothing.
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": 120.01, "payment_method": "cash"}).status_code, 409)
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": 0, "payment_method": "cash"}).status_code, 422)
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": -5, "payment_method": "cash"}).status_code, 422)
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": 0.001, "payment_method": "cash"}).status_code, 422)
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": 5, "payment_method": "cheque"}).status_code, 422)
        # The payer can never be typed in: unknown fields are rejected.
        self.assertEqual(self.client.post(route, headers=headers, json={
            "amount": 5, "payment_method": "cash", "paid_by": "someone else",
        }).status_code, 422)
        self.assertEqual(self.client.post(
            "/api/ledger/entries/restock-missing/settlements", headers=headers,
            json={"amount": 5, "payment_method": "cash"},
        ).status_code, 404)

        rest = self.client.post(route, headers=headers, json={"amount": 120, "payment_method": "card"})
        self.assertEqual(rest.status_code, 200, rest.text)
        self.assertEqual(rest.json()["status"], "paid")
        self.assertEqual(rest.json()["remaining_amount"], 0.0)
        self.assertEqual([s["payment_method"] for s in rest.json()["settlements"]], ["cash", "card"])
        self.assertEqual(self.client.post(route, headers=headers, json={"amount": 1, "payment_method": "cash"}).status_code, 409)

        summary = self.client.get(summary_route, headers=headers).json()
        self.assertEqual(summary["total_remaining"], 50.0)
        self.assertEqual(
            (summary["open_count"], summary["unpaid_count"], summary["partly_paid_count"], summary["paid_count"]),
            (1, 1, 0, 1),
        )

        def ids(query):
            response = self.client.get(f"/api/ledger/payables?{query}", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            return [row["id"] for row in response.json()]

        self.assertEqual(ids("status=paid&limit=100"), [big_id])
        self.assertEqual(ids("status=unpaid&limit=100"), [small_id])
        self.assertEqual(ids("status=partly_paid&limit=100"), [])
        self.assertEqual(self.client.get("/api/ledger/payables?status=overdue", headers=headers).status_code, 422)
        self.assertEqual(ids("limit=1&offset=0") + ids("limit=1&offset=1"), [small_id, big_id])
        self.assertEqual(ids("limit=1&offset=2"), [])
        self.assertEqual(self.client.get("/api/ledger/payables?limit=0", headers=headers).status_code, 422)
        self.assertEqual(self.client.get("/api/ledger/payables?start_day=2026-01-01", headers=headers).status_code, 422)

        # Settlements are not expenses: nothing was added to the expense totals.
        expenses = self.client.get("/api/ledger/entries?entry_type=log_expense&limit=100", headers=headers)
        self.assertEqual(expenses.json(), [])

        activity = self.client.get("/api/ledger/activity?limit=100", headers=headers)
        self.assertEqual(activity.status_code, 200, activity.text)
        self.assertEqual(
            len([entry for entry in activity.json() if entry["action_type"] == "PAY_SUPPLIER"]), 2
        )

    def test_supplier_payables_permissions_and_tenant_isolation(self):
        owner = self.register_owner("Payables Owner A")
        headers = self.auth(owner["token"])
        self.create_credit_restocks(headers, (4, 25))
        entry_id = self.client.get("/api/ledger/payables", headers=headers).json()[0]["id"]
        route = f"/api/ledger/entries/{entry_id}/settlements"
        payload = {"amount": 10, "payment_method": "cash"}

        cashier = self.join_cashier(owner)
        cashier_headers = self.auth(cashier["token"])
        self.assertEqual(self.client.post(route, headers=cashier_headers, json=payload).status_code, 403)
        cashier_list = self.client.get("/api/ledger/payables", headers=cashier_headers)
        self.assertEqual(cashier_list.status_code, 200, cashier_list.text)
        self.assertEqual(cashier_list.json(), [])
        cashier_summary = self.client.get("/api/ledger/payables/summary", headers=cashier_headers)
        self.assertEqual(cashier_summary.status_code, 200, cashier_summary.text)
        self.assertEqual(cashier_summary.json()["total_remaining"], 0.0)
        self.assertEqual(cashier_summary.json()["open_count"], 0)

        other = self.register_owner("Payables Owner B")
        other_headers = self.auth(other["token"])
        self.assertEqual(self.client.get("/api/ledger/payables", headers=other_headers).json(), [])
        self.assertEqual(self.client.post(route, headers=other_headers, json=payload).status_code, 404)

        self.assertEqual(self.client.get("/api/ledger/payables").status_code, 401)
        self.assertEqual(self.client.post(route, json=payload).status_code, 401)

        # Every refused attempt left the balance untouched.
        untouched = self.client.get("/api/ledger/payables", headers=headers).json()[0]
        self.assertEqual(untouched["status"], "unpaid")
        self.assertEqual(untouched["remaining_amount"], 100.0)

    def test_supplier_payables_ignore_restocks_from_before_tracking_started(self):
        owner = self.register_owner("Payables Cutoff Pharmacy")
        headers = self.auth(owner["token"])
        self.create_credit_restocks(headers, (2, 10))

        with patch("server.app.api.ledger._payables_tracking_start", new_callable=AsyncMock) as start:
            start.return_value = datetime(2999, 1, 1)
            self.assertEqual(self.client.get("/api/ledger/payables", headers=headers).json(), [])
            summary = self.client.get("/api/ledger/payables/summary", headers=headers).json()
            self.assertEqual(summary["open_count"], 0)
            self.assertEqual(summary["total_remaining"], 0.0)
            self.assertEqual(summary["tracking_started_at"], "2999-01-01T00:00:00Z")

        self.assertEqual(len(self.client.get("/api/ledger/payables", headers=headers).json()), 1)

    def test_direct_restock_supplier_name_and_notes_reach_the_payables_list(self):
        owner = self.register_owner("Supplier Name Pharmacy")
        headers = self.auth(owner["token"])
        item_id = self.create_credit_restocks(headers)  # product only, no restock yet
        route = f"/api/inventory/items/{item_id}/restock"

        named = self.client.post(route, headers=headers, json={
            "quantity": 3, "unit_buy_price": 10,
            "supplier_name": "  Nile   Pharma  ", "supplier_notes": "  invoice   77 ",
        })
        self.assertEqual(named.status_code, 200, named.text)
        for blank_name in (None, "   "):
            payload = {"quantity": 1, "unit_buy_price": 5}
            if blank_name is not None:
                payload["supplier_name"] = blank_name
            unnamed = self.client.post(route, headers=headers, json=payload)
            self.assertEqual(unnamed.status_code, 200, unnamed.text)
        too_long = self.client.post(route, headers=headers, json={"quantity": 1, "supplier_name": "x" * 151})
        self.assertEqual(too_long.status_code, 422)

        rows = self.client.get("/api/ledger/payables?limit=100", headers=headers).json()
        self.assertEqual(len(rows), 3)
        by_name = [row for row in rows if row["supplier_name"] == "Nile Pharma"]
        self.assertEqual(len(by_name), 1)
        self.assertEqual(by_name[0]["total_amount"], 30.0)
        self.assertIn("ملاحظات المورد: invoice 77", by_name[0]["notes"])
        unnamed_rows = [row for row in rows if row["supplier_name"] is None]
        self.assertEqual(len(unnamed_rows), 2)
        for row in unnamed_rows:
            self.assertNotIn("ملاحظات المورد", row["notes"])

    @staticmethod
    def _verification_agent():
        # The agents package is put on the import path by the app itself; try both layouts.
        try:
            from agents.verification import verification_agent
        except ImportError:
            from agents.agents.verification import verification_agent
        return verification_agent

    @staticmethod
    def _verification_state(intent: str, quantities: list, stock: float = 5.0) -> dict:
        return {
            "intent": intent,
            "language": "en",
            "payment_method": "cash",
            "extracted_items": [
                {"item_name": "Prod A", "quantity": quantity, "unit_price": 0.0}
                for quantity in quantities
            ],
            "inventory_data": [{
                "id": 1,
                "name_ar": "منتج أ",
                "name_en": "Prod A",
                "stock_qty": stock,
                "unit_buy_price": 5.0,
                "unit_sell_price": 10.0,
                "price_batches": [],
            }],
        }

    def test_sale_proposal_sums_the_same_product_across_lines_and_uses_long_ids(self):
        # Session 52 (g): two lines of the same product are checked together against
        # stock, and proposal ids are "prop-" plus 32 hex digits.
        verify = self._verification_agent()

        over = verify(self._verification_state("log_sale", [3, 3], stock=5.0))
        self.assertIsNone(over["proposal"])
        self.assertIn("6", over["answer_text"])
        self.assertIn("exceeds", over["answer_text"])

        first = verify(self._verification_state("log_sale", [2, 2], stock=5.0))
        second = verify(self._verification_state("log_sale", [2, 2], stock=5.0))
        for result in (first, second):
            self.assertIsNotNone(result["proposal"])
            self.assertRegex(result["proposal"]["id"], r"^prop-[0-9a-f]{32}$")
        self.assertNotEqual(first["proposal"]["id"], second["proposal"]["id"])

        # Restocks add stock, so the same-product sum applies to sales only.
        restock = verify(self._verification_state("log_restock", [4, 4], stock=5.0))
        self.assertIsNotNone(restock["proposal"])

    def test_document_scans_fail_closed_when_no_ocr_provider_is_configured(self):
        owner = self.register_owner()
        headers = self.auth(owner["token"])
        response = self.client.post(
            "/api/ocr/product-box",
            files={"file": ("box.jpg", b"not an image", "image/jpeg")},
            headers=headers,
        )
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn("no OCR provider adapter", response.json()["detail"])


    def test_sign_in_locks_after_five_wrong_pins_and_a_right_pin_restarts_the_count(self):
        # Session 107: the attempt is counted before the PIN is checked. Five wrong PINs
        # are answered 401, the sixth attempt gets 429 even with the right PIN, a success
        # clears the count, and another phone number is not affected.
        phone = self.new_phone()
        created = self.client.post("/api/auth/register-user", json={
            "name": "Throttle User", "phone": phone, "pin": "2468", "language_pref": "ar",
        })
        self.assertEqual(created.status_code, 200, created.text)
        other = self.register_personal_account("Other Throttle User")

        def attempt(pin: str, number: str = phone):
            return self.client.post("/api/auth/account-login", json={"phone": number, "pin": pin})

        for _ in range(4):
            self.assertEqual(attempt("0000").status_code, 401)
        self.assertEqual(attempt("2468").status_code, 200)  # clears the count

        for _ in range(5):
            self.assertEqual(attempt("0000").status_code, 401)
        locked = attempt("2468")
        self.assertEqual(locked.status_code, 429, locked.text)
        self.assertEqual(attempt("2468").status_code, 429)

        self.assertEqual(attempt("2468", other["user"]["phone"]).status_code, 200)

    def test_pharmacy_login_without_a_pharmacy_still_clears_failures_and_answers_404(self):
        # Session 107: a correct PIN clears the failure count before memberships are
        # checked, so an account with no pharmacy is not slowly locked out by its own logins.
        phone = self.new_phone()
        created = self.client.post("/api/auth/register-user", json={
            "name": "No Pharmacy User", "phone": phone, "pin": "2468", "language_pref": "ar",
        })
        self.assertEqual(created.status_code, 200, created.text)
        for _ in range(3):
            self.assertEqual(self.client.post("/api/auth/login", json={"phone": phone, "pin": "0000"}).status_code, 401)
        for _ in range(8):
            self.assertEqual(self.client.post("/api/auth/login", json={"phone": phone, "pin": "2468"}).status_code, 404)


if __name__ == "__main__":
    unittest.main()