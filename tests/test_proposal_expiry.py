# tests/test_proposal_expiry.py
"""Assistant proposals expire (debt 13(c), Session 111). Pure checks of the age rule and of the setting;
the pending list and confirm endpoints use the same helpers (no database needed here)."""

import os
import unittest
from datetime import datetime, timedelta

os.environ["SERVER_SECRET_KEY"] = "roshetta-isolated-test-secret-32-characters"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

from pydantic import ValidationError

from server.app.config import Settings
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


if __name__ == "__main__":
    unittest.main()