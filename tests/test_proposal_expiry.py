# tests/test_proposal_expiry.py
"""Assistant proposals expire (debt 13(c), Session 111). Pure checks of the age rule and of the setting,
then endpoint checks (Session 113) that the pending list and confirm use the same rule. The endpoint
tests use an in-memory SQLite database and shrink the allowed age instead of editing stored dates."""

import os
import secrets
import time
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["SEED_DEMO_DATA"] = "false"
os.environ["USE_MICROMIND"] = "false"
os.environ["AI_TOOLS_ENABLED"] = "false"
os.environ["OCR_PROVIDER"] = "disabled"

from fastapi.testclient import TestClient
from pydantic import ValidationError

from server.app.config import Settings, settings
from server.app.main import app
from server.app.services.proposals import proposal_cutoff, proposal_is_expired

NOW = datetime(2026, 10, 4, 12, 0, 0)


class ProposalExpiryTests(unittest.TestCase):
    def test_fresh_proposal_is_not_expired(self):
        self.assertFalse(proposal_is_expired(NOW - timedelta(hours=1), NOW, 24))

    def test_old_proposal_is_expired(self):
        self.assertTrue(proposal_is_expired(NOW - timedelta(hours=24, seconds=1), NOW, 24))

    def test_exactly_at_the_limit_is_still_allowed(self):
        self.assertFalse(proposal_is_expired(NOW - timedelta(hours=24), NOW, 24))

    def test_fractional_hours_work(self):
        self.assertTrue(proposal_is_expired(NOW - timedelta(minutes=31), NOW, 0.5))
        self.assertFalse(proposal_is_expired(NOW - timedelta(minutes=29), NOW, 0.5))

    def test_missing_creation_time_is_not_expired(self):
        self.assertFalse(proposal_is_expired(None, NOW, 24))

    def test_cutoff_matches_the_rule(self):
        cutoff = proposal_cutoff(NOW, 24)
        self.assertEqual(cutoff, NOW - timedelta(hours=24))
        self.assertTrue(proposal_is_expired(cutoff - timedelta(seconds=1), NOW, 24))
        self.assertFalse(proposal_is_expired(cutoff, NOW, 24))

    def test_setting_default_and_validation(self):
        self.assertEqual(Settings(_env_file=None).PENDING_ACTION_TTL_HOURS, 24.0)
        self.assertEqual(Settings(_env_file=None, PENDING_ACTION_TTL_HOURS=2).PENDING_ACTION_TTL_HOURS, 2.0)
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, PENDING_ACTION_TTL_HOURS=0)


class ProposalExpiryEndpointTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client_context = TestClient(app)
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client_context.__exit__(None, None, None)

    def pharmacy_with_proposal(self, name: str):
        """A new pharmacy with one product (stock 4) and one pending sale proposal; returns (headers, item_id, proposal_id)."""
        owner = self.client.post("/api/auth/register-pharmacy", json={
            "owner_name": "Expiry Owner", "phone": f"09{secrets.randbelow(100_000_000):08d}",
            "pin": "1234", "pharmacy_name": name,
        })
        self.assertEqual(owner.status_code, 200, owner.text)
        headers = {"Authorization": f"Bearer {owner.json()['token']}"}
        created = self.client.post("/api/inventory/create", headers=headers, json={
            "name_ar": "بنادول اكسترا (أحمر)", "name_en": "Panadol Extra (Red)", "stock_qty": 4,
            "min_threshold": 1, "unit_buy_price": 28, "unit_sell_price": 35,
        })
        self.assertEqual(created.status_code, 200, created.text)
        item_id = created.json()["item"]["id"]
        chat = self.client.post("/api/chat", headers=headers, json={"text": "sold panadol extra", "language": "en"})
        self.assertEqual(chat.status_code, 200, chat.text)
        proposal = chat.json()["proposal"]
        self.assertIsNotNone(proposal, chat.text)
        return headers, item_id, proposal["id"]

    def pending_ids(self, headers: dict) -> list:
        response = self.client.get("/api/actions/pending", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return [action["id"] for action in response.json()["actions"]]

    def stock_of(self, headers: dict, item_id: int) -> float:
        response = self.client.get("/api/inventory/items", headers=headers)
        self.assertEqual(response.status_code, 200, response.text)
        return next(row["stock_qty"] for row in response.json() if row["id"] == item_id)

    def test_a_fresh_proposal_is_listed_and_confirms(self):
        headers, item_id, proposal_id = self.pharmacy_with_proposal("Expiry Fresh Pharmacy")
        self.assertIn(proposal_id, self.pending_ids(headers))
        confirmed = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        self.assertLess(self.stock_of(headers, item_id), 4)

    def test_an_expired_proposal_is_hidden_refused_without_changes_and_can_still_be_cancelled(self):
        headers, item_id, proposal_id = self.pharmacy_with_proposal("Expiry Old Pharmacy")
        self.assertIn(proposal_id, self.pending_ids(headers))

        # Allow a proposal only a few milliseconds of life, then let it age past that.
        with patch.object(settings, "PENDING_ACTION_TTL_HOURS", 1e-6):
            time.sleep(0.05)
            self.assertNotIn(proposal_id, self.pending_ids(headers))
            refused = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
            self.assertEqual(refused.status_code, 409, refused.text)
            self.assertIn("expired", refused.json()["detail"].lower())
            self.assertEqual(self.stock_of(headers, item_id), 4)  # nothing was sold

            cancelled = self.client.post(f"/api/actions/{proposal_id}/cancel", headers=headers)
            self.assertEqual(cancelled.status_code, 200, cancelled.text)
            self.assertEqual(cancelled.json()["proposal"]["status"], "cancelled")

        # Back on the normal setting the cancelled proposal stays gone and cannot be confirmed.
        self.assertNotIn(proposal_id, self.pending_ids(headers))
        again = self.client.post(f"/api/actions/{proposal_id}/confirm", headers=headers, json={})
        self.assertEqual(again.status_code, 409, again.text)
        self.assertEqual(self.stock_of(headers, item_id), 4)


if __name__ == "__main__":
    unittest.main()