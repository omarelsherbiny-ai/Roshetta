# tests/test_my_activity.py
"""GET /api/me/activity (debt 13(d), Session 111): the totals come from SQL sums and counts, and the
results stay what the old in-memory version returned. In-memory SQLite database."""

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

ACTIVITY = "/api/me/activity"
ACCEPT = "/api/pharmacies/invitations/accept"


class MyActivityTests(unittest.TestCase):
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
            "owner_name": "Activity Owner", "phone": self.phone(), "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def cashier(self, owner: dict) -> dict:
        invitation = self.client.post(
            f"/api/pharmacies/{owner['pharmacy']['id']}/invitations",
            headers=self.auth(owner["token"]), json={"fixed_role": "cashier"},
        )
        self.assertEqual(invitation.status_code, 200, invitation.text)
        account = self.client.post("/api/auth/register-user", json={
            "name": "Activity Cashier", "phone": self.phone(), "pin": "2468", "language_pref": "ar",
        }).json()
        accepted = self.client.post(
            ACCEPT, headers=self.auth(account["token"]), json={"token": invitation.json()["token"]},
        )
        self.assertEqual(accepted.status_code, 200, accepted.text)
        return self.auth(accepted.json()["token"])

    def product(self, headers: dict) -> int:
        created = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)", "name_en": "Panadol Extra (Red)", "stock_qty": 6,
            "min_threshold": 1, "unit_buy_price": 28, "unit_sell_price": 35,
        })
        self.assertEqual(created.status_code, 200, created.text)
        return created.json()["item"]["id"]

    def sell_one(self, headers: dict) -> None:
        proposal = self.client.post("/api/chat", headers=headers, json={"text": "sold panadol extra", "language": "en"})
        confirmed = self.client.post(f"/api/actions/{proposal.json()['proposal']['id']}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)

    def test_totals_counts_units_and_recent_entries(self):
        owner = self.owner("Activity Totals Pharmacy")
        headers = self.auth(owner["token"])
        item_id = self.product(headers)
        empty = self.client.get(f"{ACTIVITY}?period=all", headers=headers).json()
        self.assertEqual((empty["sales_count"], empty["expenses_count"], empty["restocks_count"]), (0, 0, 0))
        self.assertEqual((empty["total_sales"], empty["total_expenses"], empty["total_restock"], empty["net"]), (0, 0, 0, 0))
        self.assertEqual((empty["items_sold"], empty["items_restocked"], empty["recent_entries"]), (0, 0, []))

        self.sell_one(headers)
        self.sell_one(headers)
        restock = self.client.post(f"/api/inventory/items/{item_id}/restock", headers=headers,
                                   json={"quantity": 2, "unit_buy_price": 30})
        self.assertEqual(restock.status_code, 200, restock.text)

        for period in ("day", "week", "month", "all"):
            data = self.client.get(f"{ACTIVITY}?period={period}", headers=headers).json()
            self.assertEqual(data["period"], period)
            self.assertEqual(data["pharmacy_id"], owner["pharmacy"]["id"])
            self.assertEqual(data["sales_count"], 2, period)
            self.assertEqual(data["total_sales"], 70.0, period)
            self.assertEqual(data["items_sold"], 2.0, period)
            self.assertEqual(data["restocks_count"], 1, period)
            self.assertEqual(data["items_restocked"], 2.0, period)
            self.assertEqual(data["total_restock"], 60.0, period)
            self.assertEqual(data["expenses_count"], 0, period)
            self.assertEqual(data["net"], 70.0, period)
            self.assertEqual(len(data["recent_entries"]), 3, period)
            stamps = [row["created_at"] for row in data["recent_entries"]]
            self.assertEqual(stamps, sorted(stamps, reverse=True), period)

    def test_each_member_sees_only_their_own_totals(self):
        owner = self.owner("Activity Own Pharmacy")
        owner_headers = self.auth(owner["token"])
        self.product(owner_headers)
        cashier = self.cashier(owner)
        self.sell_one(owner_headers)
        self.sell_one(cashier)
        self.sell_one(cashier)
        mine = self.client.get(f"{ACTIVITY}?period=all", headers=cashier).json()
        theirs = self.client.get(f"{ACTIVITY}?period=all", headers=owner_headers).json()
        self.assertEqual((mine["sales_count"], mine["total_sales"]), (2, 70.0))
        self.assertEqual((theirs["sales_count"], theirs["total_sales"]), (1, 35.0))

    def test_other_pharmacy_and_bad_period_are_refused(self):
        first, second = self.owner("Activity Tenant A"), self.owner("Activity Tenant B")
        headers = self.auth(first["token"])
        self.assertEqual(
            self.client.get(f"{ACTIVITY}?pharmacy_id={second['pharmacy']['id']}", headers=headers).status_code, 403)
        self.assertEqual(self.client.get(f"{ACTIVITY}?period=year", headers=headers).status_code, 422)
        self.assertEqual(self.client.get(ACTIVITY).status_code, 401)


if __name__ == "__main__":
    unittest.main()