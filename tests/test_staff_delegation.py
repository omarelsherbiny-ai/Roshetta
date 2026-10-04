# tests/test_staff_delegation.py
"""Delegated staff management (Session 109, W5): a staff manager can use custom roles, but
nobody can grant a scope they do not hold, change their own role, or change or remove a
member who holds more than they do. In-memory SQLite database."""

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

ACCEPT = "/api/pharmacies/invitations/accept"


class StaffDelegationTests(unittest.TestCase):
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
            "owner_name": "Delegation Owner", "phone": self.phone(), "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def role(self, owner: dict, name: str, scopes: list[str]) -> int:
        response = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/roles",
            headers=self.auth(owner["token"]), json={"name": name, "scopes": scopes},
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()["role"]["id"]

    def join(self, owner: dict, **invite_body) -> dict:
        invitation = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations",
            headers=self.auth(owner["token"]), json=invite_body,
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account = self.client.post("/api/auth/register-user", json={
            "name": "Delegation Member", "phone": self.phone(), "pin": "2468", "language_pref": "ar",
        }).json()
        accepted = self.client.post(
            ACCEPT, headers=self.auth(account["token"]), json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return {"headers": self.auth(accepted.json()["token"]), "user_id": account["user"]["id"]}

    def setup_pharmacy(self, name: str) -> dict:
        owner = self.owner(name)
        delegate_role = self.role(owner, "Delegate", ["manage_staff", "view_reports", "view_inventory"])
        return {
            "owner": owner,
            "id": owner["pharmacy"]["id"],
            "delegate": self.join(owner, custom_role_id=delegate_role),
            "look_role": self.role(owner, "Stock Look", ["view_inventory"]),
            "seller_role": self.role(owner, "Seller", ["log_sale"]),
            "super_role": self.role(owner, "Super", ["manage_staff", "view_reports", "view_inventory", "view_audit"]),
        }

    def test_delegate_invites_only_custom_roles_whose_scopes_it_holds(self):
        p = self.setup_pharmacy("Delegate Invite Pharmacy")
        route = f"/api/pharmacies/{p['id']}/invitations"
        ok = self.client.post(route, headers=p["delegate"]["headers"], json={"custom_role_id": p["look_role"]})
        self.assertEqual(ok.status_code, 200, ok.text)
        for key in ("seller_role", "super_role"):
            refused = self.client.post(route, headers=p["delegate"]["headers"], json={"custom_role_id": p[key]})
            self.assertEqual(refused.status_code, 403, key)
        # The owner is not restricted.
        self.assertEqual(self.client.post(route, headers=self.auth(p["owner"]["token"]),
                                          json={"custom_role_id": p["super_role"]}).status_code, 200)

    def test_delegate_assigns_custom_roles_within_its_own_scopes_to_members_within_them(self):
        p = self.setup_pharmacy("Delegate Assign Pharmacy")
        viewer = self.join(p["owner"], fixed_role="viewer")
        route = f"/api/pharmacies/{p['id']}/staff/{viewer['user_id']}/role"
        put = lambda role_id: self.client.put(route, headers=p["delegate"]["headers"], json={"custom_role_id": role_id})

        self.assertEqual(put(p["seller_role"]).status_code, 403)   # scope the delegate lacks
        self.assertEqual(put(p["super_role"]).status_code, 403)    # scope the delegate lacks
        assigned = put(p["look_role"])
        self.assertEqual(assigned.status_code, 200, assigned.text)
        self.assertEqual(assigned.json()["role_name"], "Stock Look")
        # The new member can now read the catalog and nothing more.
        self.assertEqual(self.client.get("/api/inventory/items", headers=viewer["headers"]).status_code, 200)
        self.assertEqual(self.client.get("/api/ledger/entries", headers=viewer["headers"]).status_code, 403)
        self.assertEqual(put(p["look_role"]).status_code, 200)

    def test_delegate_cannot_change_or_remove_a_member_who_holds_more(self):
        p = self.setup_pharmacy("Delegate Target Pharmacy")
        cashier = self.join(p["owner"], fixed_role="cashier")
        seller = self.join(p["owner"], custom_role_id=p["seller_role"])
        for target in (cashier, seller):
            base = f"/api/pharmacies/{p['id']}/staff/{target['user_id']}"
            self.assertEqual(self.client.patch(f"{base}/role", headers=p["delegate"]["headers"], json={"role": "viewer"}).status_code, 403)
            self.assertEqual(self.client.put(f"{base}/role", headers=p["delegate"]["headers"], json={"custom_role_id": p["look_role"]}).status_code, 403)
            self.assertEqual(self.client.delete(base, headers=p["delegate"]["headers"]).status_code, 403)
        # A member within the delegate's scopes can be removed by the delegate.
        viewer = self.join(p["owner"], fixed_role="viewer")
        self.assertEqual(self.client.delete(
            f"/api/pharmacies/{p['id']}/staff/{viewer['user_id']}", headers=p["delegate"]["headers"]).status_code, 200)
        # The owner can still change anyone.
        self.assertEqual(self.client.put(
            f"/api/pharmacies/{p['id']}/staff/{cashier['user_id']}/role",
            headers=self.auth(p["owner"]["token"]), json={"custom_role_id": p["seller_role"]}).status_code, 200)

    def test_delegate_cannot_change_its_own_role_or_touch_the_owner(self):
        p = self.setup_pharmacy("Delegate Self Pharmacy")
        own = f"/api/pharmacies/{p['id']}/staff/{p['delegate']['user_id']}/role"
        self.assertEqual(self.client.put(own, headers=p["delegate"]["headers"], json={"custom_role_id": p["look_role"]}).status_code, 403)
        self.assertEqual(self.client.patch(own, headers=p["delegate"]["headers"], json={"role": "viewer"}).status_code, 403)
        owner_id = p["owner"]["user"]["id"]
        owner_route = f"/api/pharmacies/{p['id']}/staff/{owner_id}"
        self.assertEqual(self.client.put(f"{owner_route}/role", headers=p["delegate"]["headers"], json={"custom_role_id": p["look_role"]}).status_code, 409)
        self.assertEqual(self.client.delete(owner_route, headers=p["delegate"]["headers"]).status_code, 409)
        self.assertEqual(self.client.patch(f"{owner_route}/role", headers=p["delegate"]["headers"], json={"role": "viewer"}).status_code, 409)
        # The owner membership cannot be reassigned or removed by anyone, so a pharmacy always keeps
        # at least one member who can manage staff (no "last manager" guard is needed).
        self.assertEqual(self.client.delete(owner_route, headers=self.auth(p["owner"]["token"])).status_code, 409)

    def test_member_without_manage_staff_cannot_use_any_of_it(self):
        p = self.setup_pharmacy("No Manage Staff Pharmacy")
        seller = self.join(p["owner"], custom_role_id=p["seller_role"])
        target = self.join(p["owner"], fixed_role="viewer")
        self.assertEqual(self.client.put(
            f"/api/pharmacies/{p['id']}/staff/{target['user_id']}/role",
            headers=seller["headers"], json={"custom_role_id": p["look_role"]}).status_code, 403)
        self.assertEqual(self.client.post(
            f"/api/pharmacies/{p['id']}/invitations", headers=seller["headers"],
            json={"custom_role_id": p["look_role"]}).status_code, 403)


    def test_roles_overview_for_staff_managers(self):
        p = self.setup_pharmacy("Roles Overview Pharmacy")
        self.join(p["owner"], fixed_role="viewer")
        route = f"/api/pharmacies/{p['id']}/roles/overview"

        def by_key(response):
            self.assertEqual(response.status_code, 200, response.text)
            return {row["key"]: row for row in response.json()["roles"]}

        delegate_view = by_key(self.client.get(route, headers=p["delegate"]["headers"]))
        self.assertEqual(set(delegate_view) & {"owner", "pharmacist", "cashier", "viewer"}, {"owner", "pharmacist", "cashier", "viewer"})
        self.assertFalse(delegate_view["owner"]["grantable"])
        self.assertTrue(delegate_view["viewer"]["grantable"])          # view_reports is held
        self.assertFalse(delegate_view["cashier"]["grantable"])        # log_sale is not held
        self.assertTrue(delegate_view[f"custom:{p['look_role']}"]["grantable"])
        self.assertFalse(delegate_view[f"custom:{p['seller_role']}"]["grantable"])
        self.assertFalse(delegate_view[f"custom:{p['super_role']}"]["grantable"])
        self.assertEqual(delegate_view["viewer"]["assigned_count"], 1)
        self.assertEqual(delegate_view["owner"]["assigned_count"], 1)
        self.assertEqual(delegate_view[f"custom:{p['look_role']}"]["scopes"], ["view_inventory"])
        # Counts only: no member names, ids or phone numbers in the answer.
        text = self.client.get(route, headers=p["delegate"]["headers"]).text
        for forbidden in ("Delegation Member", "Delegation Owner", "phone", "user_id"):
            self.assertNotIn(forbidden, text)

        owner_view = by_key(self.client.get(route, headers=self.auth(p["owner"]["token"])))
        self.assertFalse(owner_view["owner"]["grantable"])
        self.assertTrue(owner_view["cashier"]["grantable"])
        self.assertTrue(owner_view[f"custom:{p['super_role']}"]["grantable"])

        # A member without manage_staff is refused, and another pharmacy's roles never show up.
        seller = self.join(p["owner"], custom_role_id=p["seller_role"])
        self.assertEqual(self.client.get(route, headers=seller["headers"]).status_code, 403)
        other = self.owner("Other Overview Pharmacy")
        other_role = self.role(other, "Other Only", ["view_reports"])
        self.assertNotIn(f"custom:{other_role}", owner_view)
        self.assertEqual(self.client.get(route, headers=self.auth(other["token"])).status_code, 404)


    def test_list_roles_counts_active_members_per_role(self):
        p = self.setup_pharmacy("Roles Count Pharmacy")
        first = self.join(p["owner"], custom_role_id=p["look_role"])
        self.join(p["owner"], custom_role_id=p["look_role"])
        route = f"/api/pharmacies/{p['id']}/roles"
        owner_headers = self.auth(p["owner"]["token"])

        def counts():
            response = self.client.get(route, headers=owner_headers)
            self.assertEqual(response.status_code, 200, response.text)
            return {row["name"]: row["assigned_count"] for row in response.json()["roles"]}

        self.assertEqual(counts(), {"Delegate": 1, "Stock Look": 2, "Seller": 0, "Super": 0})
        # A removed member no longer counts, and another pharmacy's members never do.
        self.assertEqual(self.client.delete(
            f"/api/pharmacies/{p['id']}/staff/{first['user_id']}", headers=owner_headers).status_code, 200)
        other = self.owner("Other Count Pharmacy")
        other_role = self.role(other, "Stock Look", ["view_inventory"])
        self.join(other, custom_role_id=other_role)
        self.assertEqual(counts()["Stock Look"], 1)
        # Still owner only.
        self.assertEqual(self.client.get(route, headers=p["delegate"]["headers"]).status_code, 403)


    def test_work_summary_totals_come_from_the_members_own_entries(self):
        p = self.setup_pharmacy("Work Summary Pharmacy")
        owner_headers = self.auth(p["owner"]["token"])
        summary = lambda headers, days=7: self.client.get(f"/api/staff/me/summary?days={days}", headers=headers)

        empty = summary(owner_headers)
        self.assertEqual(empty.status_code, 200, empty.text)
        self.assertEqual(
            {k: v for k, v in empty.json().items() if k not in ("from", "through", "period_days")},
            {"sales_count": 0, "sales_amount": 0.0, "sold_quantity": 0.0, "expenses_count": 0,
             "expenses_amount": 0.0, "restock_count": 0, "restock_amount": 0.0, "restocked_quantity": 0.0},
        )

        created = self.client.post("/api/inventory/create", headers=owner_headers, json={
            "name_ar": "دواء ملخص", "name_en": "Summary Medicine", "unit_sell_price": 20,
        })
        self.assertEqual(created.status_code, 200, created.text)
        item_id = created.json()["item"]["id"]
        for quantity, price in ((4, 5), (2, 10)):
            restock = self.client.post(f"/api/inventory/items/{item_id}/restock", headers=owner_headers,
                                       json={"quantity": quantity, "unit_buy_price": price})
            self.assertEqual(restock.status_code, 200, restock.text)

        body = summary(owner_headers).json()
        self.assertEqual(body["restock_count"], 2)
        self.assertEqual(body["restock_amount"], 40.0)
        self.assertEqual(body["restocked_quantity"], 6.0)
        self.assertEqual((body["sales_count"], body["expenses_count"]), (0, 0))
        self.assertEqual(body["period_days"], 7)
        # Another member sees only their own work, and a bad period is refused.
        self.assertEqual(summary(p["delegate"]["headers"]).json()["restock_count"], 0)
        self.assertEqual(summary(owner_headers, days=0).status_code, 422)


    def test_delegate_cannot_remove_its_own_membership(self):
        p = self.setup_pharmacy("Delegate Self Remove Pharmacy")
        own = f"/api/pharmacies/{p['id']}/staff/{p['delegate']['user_id']}"
        self.assertEqual(self.client.delete(own, headers=p["delegate"]["headers"]).status_code, 403)
        # Still a member: the same token keeps working.
        self.assertEqual(self.client.get("/api/inventory/items", headers=p["delegate"]["headers"]).status_code, 200)

    def test_delegate_revokes_only_invitations_within_its_scopes_and_the_list_is_bounded(self):
        p = self.setup_pharmacy("Delegate Revoke Pharmacy")
        owner_headers = self.auth(p["owner"]["token"])
        route = f"/api/pharmacies/{p['id']}/invitations"
        make = lambda **body: self.client.post(route, headers=owner_headers, json=body).json()["invitation_id"]
        high, low, fixed_high, fixed_low = (
            make(custom_role_id=p["super_role"]), make(custom_role_id=p["look_role"]),
            make(fixed_role="cashier"), make(fixed_role="viewer"),
        )
        revoke = lambda headers, invitation_id: self.client.delete(f"{route}/{invitation_id}", headers=headers).status_code
        delegate = p["delegate"]["headers"]
        self.assertEqual(revoke(delegate, high), 403)
        self.assertEqual(revoke(delegate, fixed_high), 403)
        self.assertEqual(revoke(delegate, low), 200)
        self.assertEqual(revoke(delegate, fixed_low), 200)
        self.assertEqual(revoke(owner_headers, high), 200)
        listed = self.client.get(route, headers=owner_headers)
        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertGreaterEqual(len(listed.json()), 5)
        self.assertEqual(len(self.client.get(f"{route}?limit=2", headers=owner_headers).json()), 2)
        self.assertEqual(self.client.get(f"{route}?limit=0", headers=owner_headers).status_code, 422)


if __name__ == "__main__":
    unittest.main()