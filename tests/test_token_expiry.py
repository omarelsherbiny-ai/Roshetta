# tests/test_token_expiry.py
"""A dead token is always answered 401, never 403 (Next tasks 0, Waiting item 96).

The web client signs the person out only on a 401, so an expired, tampered, future-dated
or wrong-audience token must never come back as anything else. No database is needed:
every case here is refused before the first query. The clock and the secret are patched
inside each test, so the checks do not depend on `server/.env`.
"""

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from server.app.services import rbac, security

SECRET = b"k" * 40
START = 1_800_000_000  # a fixed "now", in seconds


def at(seconds):
    """Pretend the clock reads `seconds` (what `time.time()` returns)."""
    return patch.object(security.time, "time", return_value=float(seconds))


def with_secret():
    return patch.object(security, "_secret_key", return_value=SECRET)


def issue(now=START, ai=False, ttl=None):
    with with_secret(), at(now):
        if ai:
            if ttl is None:
                return security.create_ai_access_token(5, 9)
            return security.create_ai_access_token(5, 9, ttl)
        return security.create_access_token(5, 9)


def decode(token, now):
    with with_secret(), at(now):
        return security.decode_access_token(token)


class DecodeTokenExpiryTests(unittest.TestCase):
    def assert_401(self, token, now):
        with self.assertRaises(HTTPException) as caught:
            decode(token, now)
        self.assertEqual(caught.exception.status_code, 401)

    def test_a_fresh_token_decodes(self):
        identity = decode(issue(), START + 1)
        self.assertEqual((identity["user_id"], identity["pharmacy_id"]), (5, 9))

    def test_the_last_second_before_expiry_still_works(self):
        decode(issue(), START + security.TOKEN_TTL_SECONDS - 1)

    def test_a_token_is_dead_at_its_expiry_second(self):
        self.assert_401(issue(), START + security.TOKEN_TTL_SECONDS)

    def test_a_token_long_after_expiry_is_401(self):
        self.assert_401(issue(), START + 10 * security.TOKEN_TTL_SECONDS)

    def test_an_ai_token_dies_after_its_own_short_life(self):
        token = issue(ai=True)
        decode(token, START + security.AI_TOKEN_TTL_SECONDS - 1)
        self.assert_401(token, START + security.AI_TOKEN_TTL_SECONDS)

    def test_an_ai_token_life_is_capped(self):
        token = issue(ai=True, ttl=10_000_000)
        decode(token, START + security.AI_TOKEN_MAX_TTL_SECONDS - 1)
        self.assert_401(token, START + security.AI_TOKEN_MAX_TTL_SECONDS)

    def test_a_token_issued_far_in_the_future_is_401(self):
        # A clock more than 60 seconds behind the issuer is refused, not trusted.
        self.assert_401(issue(now=START + 120), START)

    def test_a_token_issued_a_few_seconds_ahead_is_tolerated(self):
        decode(issue(now=START + 30), START)

    def test_tampered_malformed_and_wrong_version_tokens_are_401(self):
        token = issue()
        version, body, signature = token.split(".")
        flipped = ("A" if signature[0] != "A" else "B") + signature[1:]
        for bad in (
            f"{version}.{body}.{flipped}",   # signature changed
            f"rsh2.{body}.{signature}",      # unknown version
            f"{version}.{body}",             # a part missing
            "not-a-token",
            "",
        ):
            with self.subTest(token=bad[:20]):
                self.assert_401(bad, START + 1)


class HeaderPathTests(unittest.IsolatedAsyncioTestCase):
    """The same refusals through the real header check, before any database query."""

    async def refuse(self, authorization, now=START + 1, allow_ai_token=False):
        with with_secret(), at(now):
            with self.assertRaises(HTTPException) as caught:
                # db=None: a refusal that happens before the first query never touches it.
                await rbac._identity_from_header(authorization, None, allow_ai_token)
        return caught.exception

    async def test_an_expired_token_is_401_through_the_header_check(self):
        token = issue()
        error = await self.refuse(f"Bearer {token}", now=START + security.TOKEN_TTL_SECONDS + 1)
        self.assertEqual(error.status_code, 401)

    async def test_a_missing_or_malformed_header_is_401(self):
        for header in (None, "", "Bearer", "Bearer   ", "Basic abc", "token-without-scheme"):
            with self.subTest(header=header):
                self.assertEqual((await self.refuse(header)).status_code, 401)

    async def test_an_ai_token_on_the_main_api_is_401(self):
        error = await self.refuse(f"Bearer {issue(ai=True)}")
        self.assertEqual(error.status_code, 401)


if __name__ == "__main__":
    unittest.main()