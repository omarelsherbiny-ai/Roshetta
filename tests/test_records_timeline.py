# tests/test_records_timeline.py
"""Records timeline (Session 109, W6): one newest-first list of ledger entries plus product,
supplier and staff audit rows, each source gated by its own scope; a cashier sees only their
own rows; new audit rows carry the acting role's name. In-memory SQLite database."""

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

TIMELINE = "/api/ledger/timeline"
ACCEPT = "/api/pharmacies/invitations/accept"


class RecordsTimelineTests(unittest.TestCase):
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
            "owner_name": "Timeline Owner", "phone": self.phone(), "pin": "1234", "pharmacy_name": name,
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
            "name": "Timeline Member", "phone": self.phone(), "pin": "2468", "language_pref": "ar",
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

    def product(self, headers: dict, name_en: str = "Panadol Extra (Red)", name_ar: str = "بنادول اكسترا (أحمر)", stock: int = 4) -> int:
        created = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": name_ar, "name_en": name_en, "stock_qty": stock, "min_threshold": 1,
            "unit_buy_price": 28, "unit_sell_price": 35,
        })
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    def timeline(self, headers: dict, query: str = "limit=100"):
        return self.client.get(f"{TIMELINE}?{query}", headers=headers)

    def kinds(self, headers: dict, query: str = "limit=100") -> list[str]:
        response = self.timeline(headers, query)
        self.assertEqual(response.status_code, 200, response.text)
        return [row["kind"] for row in response.json()]

    def test_owner_sees_one_organized_timeline_without_duplicates(self):
        owner = self.owner("Timeline Owner Pharmacy")
        headers = self.auth(owner["token"])
        item_id = self.product(headers)
        edit = self.client.put(f"/api/inventory/items/{item_id}", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)", "name_en": "Panadol Extra (Red)", "min_threshold": 1,
            "unit_buy_price": 30, "unit_sell_price": 40,
        })
        self.assertEqual(edit.status_code, 200, edit.text)
        restock = self.client.post(f"/api/inventory/items/{item_id}/restock", headers=headers,
                                   json={"quantity": 2, "unit_buy_price": 30})
        self.assertEqual(restock.status_code, 200, restock.text)
        proposal = self.client.post("/api/chat", headers=headers, json={"text": "sold panadol extra", "language": "en"})
        confirmed = self.client.post(f"/api/actions/{proposal.json()['proposal']['id']}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        rows = self.timeline(headers).json()
        kinds = [row["kind"] for row in rows]
        for expected in ("CREATE_PRODUCT", "UPDATE_PRODUCT", "log_restock", "log_sale"):
            self.assertIn(expected, kinds)
        # A ledger entry is never repeated by its audit row.
        self.assertNotIn("DIRECT_RESTOCK", kinds)
        self.assertNotIn("CONFIRM_ACTION", kinds)
        stamps = [row["occurred_at"] for row in rows]
        self.assertEqual(stamps, sorted(stamps, reverse=True))
        update = next(row for row in rows if row["kind"] == "UPDATE_PRODUCT")
        self.assertEqual(update["details"]["previous_unit_sell_price"], 35)
        self.assertEqual(update["details"]["unit_sell_price"], 40)
        self.assertEqual(update["actor_role_name"], "owner")
        sale = next(row for row in rows if row["kind"] == "log_sale")
        # The sale is priced from the oldest stock lot, which keeps the sell price it was created
        # with (35); editing the product's sell price changes the product row, not existing lots.
        self.assertEqual(sale["amount"], 35)
        self.assertEqual(sale["source"], "ledger")

        # Filtering by kind and paging reproduce the same rows.
        self.assertEqual(self.kinds(headers, "kind=log_sale&limit=100"), ["log_sale"])
        self.assertEqual(self.kinds(headers, "kind=UPDATE_PRODUCT&limit=100"), ["UPDATE_PRODUCT"])
        paged = self.timeline(headers, "limit=2&offset=0").json() + self.timeline(headers, "limit=2&offset=2").json()
        self.assertEqual([row["id"] for row in paged], [row["id"] for row in rows][:4])
        self.assertEqual(self.timeline(headers, "limit=2&offset=1000").json(), [])
        self.assertEqual(self.timeline(headers, "offset=1001").status_code, 422)
        self.assertEqual(self.timeline(headers, "start_day=2026-01-01").status_code, 422)
        self.assertEqual(self.timeline(headers, "start_day=2999-01-01&end_day=2999-01-02").json(), [])

    def test_each_source_is_gated_by_its_own_scope(self):
        owner = self.owner("Timeline Scope Pharmacy")
        owner_headers = self.auth(owner["token"])
        item_id = self.product(owner_headers)
        self.client.post(f"/api/inventory/items/{item_id}/restock", headers=owner_headers,
                         json={"quantity": 1, "unit_buy_price": 28})

        viewer = self.join(owner, fixed_role="viewer")
        self.assertEqual(set(self.kinds(viewer["headers"])), {"log_restock"})

        stock_look = self.custom(owner, "Stock Look", ["view_inventory"])
        self.assertEqual(set(self.kinds(stock_look["headers"])), {"CREATE_PRODUCT"})
        auditor = self.custom(owner, "Auditor", ["view_audit"])
        auditor_kinds = set(self.kinds(auditor["headers"]))
        self.assertIn("CREATE_PHARMACY_ROLE", auditor_kinds)
        self.assertNotIn("CREATE_PRODUCT", auditor_kinds)
        self.assertNotIn("log_restock", auditor_kinds)

        seller = self.custom(owner, "Seller Only", ["log_sale"])
        self.assertEqual(self.timeline(seller["headers"]).status_code, 403)

        # The same members keep their existing limits on the older record endpoints.
        self.assertEqual(self.client.get("/api/ledger/entries", headers=stock_look["headers"]).status_code, 403)
        self.assertEqual(self.client.get("/api/ledger/activity", headers=stock_look["headers"]).status_code, 403)
        self.assertEqual(self.client.get("/api/ledger/payables", headers=stock_look["headers"]).status_code, 403)
        self.assertEqual(self.client.get("/api/ledger/activity", headers=viewer["headers"]).status_code, 403)
        self.assertEqual(self.client.get("/api/inventory/items", headers=viewer["headers"]).status_code, 403)

    def test_cashier_sees_only_their_own_rows(self):
        owner = self.owner("Timeline Cashier Pharmacy")
        owner_headers = self.auth(owner["token"])
        self.product(owner_headers)
        proposal = self.client.post("/api/chat", headers=owner_headers, json={"text": "sold panadol extra", "language": "en"})
        cashier = self.join(owner, fixed_role="cashier")
        confirmed = self.client.post(f"/api/actions/{proposal.json()['proposal']['id']}/confirm",
                                     headers=cashier["headers"], json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

        self.assertEqual(self.kinds(cashier["headers"]), ["log_sale"])  # not the owner's product rows
        self.assertEqual(self.timeline(cashier["headers"], f"user_id={cashier['user_id']}").status_code, 200)
        self.assertEqual(self.timeline(cashier["headers"], f"user_id={owner['user']['id']}").status_code, 403)
        # The owner can filter by person.
        by_cashier = self.timeline(owner_headers, f"user_id={cashier['user_id']}&limit=100").json()
        by_cashier_kinds = [row["kind"] for row in by_cashier]
        self.assertIn("log_sale", by_cashier_kinds)
        self.assertNotIn("CREATE_PRODUCT", by_cashier_kinds)  # the owner's own row

    def test_custom_role_name_is_recorded_on_new_audit_rows(self):
        owner = self.owner("Timeline Role Name Pharmacy")
        editor = self.custom(owner, "Catalog Editor", ["manage_inventory"])
        self.product(editor["headers"], name_en="Role Name Product", name_ar="منتج اسم الدور", stock=1)
        rows = self.timeline(self.auth(owner["token"]), "kind=CREATE_PRODUCT&limit=100").json()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["actor_role_name"], "Catalog Editor")
        self.assertEqual(rows[0]["product_name"], "منتج اسم الدور")
        self.assertNotIn("role_name", rows[0]["details"])

    def test_timeline_is_tenant_scoped_and_needs_a_pharmacy_session(self):
        first, second = self.owner("Timeline Tenant A"), self.owner("Timeline Tenant B")
        self.product(self.auth(first["token"]))
        other = self.timeline(self.auth(second["token"])).json()
        self.assertEqual([row["kind"] for row in other if row["source"] == "ledger"], [])
        self.assertNotIn("CREATE_PRODUCT", [row["kind"] for row in other])
        self.assertEqual(self.client.get(TIMELINE).status_code, 401)
        account = self.client.post("/api/auth/register-user", json={
            "name": "Hub Only", "phone": self.phone(), "pin": "2468", "language_pref": "ar"}).json()
        self.assertEqual(self.timeline(self.auth(account["token"])).status_code, 409)


if __name__ == "__main__":
    unittest.main()