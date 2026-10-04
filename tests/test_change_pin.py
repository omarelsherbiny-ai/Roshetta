# tests/test_change_pin.py
"""POST /api/auth/change-pin (Session 111). In-memory SQLite database."""

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

CHANGE = "/api/auth/change-pin"


class ChangePinTests(unittest.TestCase):
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

    def account(self, pin: str = "1234") -> dict:
        phone = f"09{secrets.randbelow(100_000_000):08d}"
        response = self.client.post("/api/auth/register-user", json={
            "name": "Pin Tester", "phone": phone, "pin": pin, "language_pref": "en",
        })
        self.assertEqual(response.status_code, 200, response.text)
        return {"phone": phone, "token": response.json()["token"]}

    def login(self, account: dict, pin: str):
        return self.client.post("/api/auth/account-login", json={"phone": account["phone"], "pin": pin})

    def test_wrong_current_pin_is_refused_and_nothing_changes(self):
        a = self.account()
        refused = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                   json={"current_pin": "9999", "new_pin": "5678"})
        self.assertEqual(refused.status_code, 403, refused.text)  # 403, not 401: not a dead session
        self.assertEqual(self.login(a, "1234").status_code, 200)
        self.assertEqual(self.login(a, "5678").status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(a["token"])).status_code, 200)

    def test_invalid_or_unchanged_new_pins_are_refused(self):
        a = self.account()
        for new_pin in ("1234", "12ab", "123", "1234567"):
            response = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                        json={"current_pin": "1234", "new_pin": new_pin})
            self.assertEqual(response.status_code, 422, new_pin)
        self.assertEqual(self.login(a, "1234").status_code, 200)

    def test_success_changes_the_pin_revokes_this_session_and_returns_a_new_token(self):
        a = self.account()
        changed = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                   json={"current_pin": "1234", "new_pin": "567890"})
        self.assertEqual(changed.status_code, 200, changed.text)
        new_token = changed.json()["token"]
        self.assertNotEqual(new_token, a["token"])
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(a["token"])).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(new_token)).status_code, 200)
        self.assertEqual(self.login(a, "567890").status_code, 200)
        self.assertEqual(self.login(a, "1234").status_code, 401)
        # The change is in the person's own activity, without any PIN in it.
        activity = self.client.get("/api/staff/me/activity", headers=self.auth(new_token))
        self.assertEqual(activity.status_code, 200, activity.text)
        rows = [row for row in activity.json() if row["action_type"] == "CHANGE_PIN"]
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["pharmacy_id"])
        for pin in ("1234", "567890"):
            self.assertNotIn(pin, str(rows[0]))

    def test_every_other_session_is_signed_out_but_later_sign_ins_work(self):
        a = self.account()
        other_session = self.login(a, "1234").json()["token"]
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(other_session)).status_code, 200)
        changed = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                   json={"current_pin": "1234", "new_pin": "5678"})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(other_session)).status_code, 401)
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(changed.json()["token"])).status_code, 200)
        later = self.login(a, "5678").json()["token"]
        self.assertEqual(self.client.get("/api/auth/me", headers=self.auth(later)).status_code, 200)

    def test_wrong_current_pins_are_throttled_like_sign_in(self):
        a = self.account()
        for _ in range(5):
            wrong = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                     json={"current_pin": "0000", "new_pin": "5678"})
            self.assertEqual(wrong.status_code, 403)
        blocked = self.client.post(CHANGE, headers=self.auth(a["token"]),
                                   json={"current_pin": "1234", "new_pin": "5678"})
        self.assertEqual(blocked.status_code, 429, blocked.text)
        # The shared throttle also stops sign-in for this phone.
        self.assertEqual(self.login(a, "1234").status_code, 429)

    def test_a_token_is_required(self):
        response = self.client.post(CHANGE, json={"current_pin": "1234", "new_pin": "5678"})
        self.assertIn(response.status_code, (401, 403))


if __name__ == "__main__":
    unittest.main()