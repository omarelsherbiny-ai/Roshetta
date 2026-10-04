# tests/test_token_cutoff.py
"""Token issue time and the users.tokens_valid_after migration (Session 111, debt 22)."""

import os
import unittest

os.environ.setdefault("SERVER_SECRET_KEY", "roshetta-isolated-test-secret-32-characters")

from sqlalchemy import create_engine, inspect, text

from server.app.db.migrations import _upgrade_sync
from server.app.services import security


class TokenIssueTimeTests(unittest.TestCase):
    def test_new_tokens_carry_a_millisecond_issue_time(self):
        decoded = security.decode_access_token(security.create_access_token(7, None))
        self.assertIsInstance(decoded["issued_at_ms"], int)
        # The two clock reads can straddle a second boundary, so allow one second.
        issued_second = decoded["token_expires_at"] - security.TOKEN_TTL_SECONDS
        self.assertLessEqual(abs(decoded["issued_at_ms"] // 1000 - issued_second), 1)

    def test_a_token_without_the_millisecond_claim_falls_back_to_its_second(self):
        token = security._sign_payload({
            "sub": 7, "pharmacy_id": None, "iat": 1_700_000_000, "exp": 4_000_000_000, "jti": "legacy",
        })
        self.assertEqual(security.decode_access_token(token)["issued_at_ms"], 1_700_000_000_000)

    def test_a_non_integer_millisecond_claim_is_refused(self):
        from fastapi import HTTPException
        token = security._sign_payload({
            "sub": 7, "pharmacy_id": None, "iat": 1_700_000_000, "iat_ms": "now",
            "exp": 4_000_000_000, "jti": "bad",
        })
        with self.assertRaises(HTTPException):
            security.decode_access_token(token)


class MigrationFourteenTests(unittest.TestCase):
    def test_adds_the_column_once_and_records_the_version(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, name VARCHAR(100))"))
            connection.execute(text(
                "CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, applied_at TIMESTAMP NOT NULL)"
            ))
            for version in range(1, 14):
                connection.execute(text(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (:v, CURRENT_TIMESTAMP)"
                ), {"v": version})
            _upgrade_sync(connection)
            columns = {c["name"] for c in inspect(connection).get_columns("users")}
            self.assertIn("tokens_valid_after", columns)
            versions = {row[0] for row in connection.execute(text("SELECT version FROM schema_migrations"))}
            self.assertIn(14, versions)
            _upgrade_sync(connection)  # running again changes nothing and does not fail


if __name__ == "__main__":
    unittest.main()