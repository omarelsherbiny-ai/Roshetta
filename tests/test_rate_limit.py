# tests/test_rate_limit.py
import unittest

from pydantic import ValidationError

from server.app.config import Settings, settings
from server.app.services.rate_limit import (
    AI_CALLS_PER_CHAT_MESSAGE,
    SlidingWindowLimiter,
    ai_limiter,
    chat_limiter,
)


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class SlidingWindowLimiterTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.limiter = SlidingWindowLimiter(3, 60.0, clock=self.clock)

    def test_calls_up_to_the_limit_are_allowed_then_blocked(self):
        for _ in range(3):
            self.assertIsNone(self.limiter.check("u1"))
        self.assertIsNotNone(self.limiter.check("u1"))

    def test_retry_after_counts_down_from_the_oldest_call(self):
        for _ in range(3):
            self.limiter.check("u1")
        self.assertEqual(self.limiter.check("u1"), 60)
        self.clock.now += 45
        self.assertEqual(self.limiter.check("u1"), 15)

    def test_calls_are_allowed_again_after_the_window(self):
        for _ in range(3):
            self.limiter.check("u1")
        self.clock.now += 60
        self.assertIsNone(self.limiter.check("u1"))

    def test_blocked_calls_do_not_extend_the_block(self):
        for _ in range(3):
            self.limiter.check("u1")
        for _ in range(10):
            self.limiter.check("u1")
        self.clock.now += 60
        self.assertIsNone(self.limiter.check("u1"))

    def test_each_key_has_its_own_budget(self):
        for _ in range(3):
            self.limiter.check(("pharmacy-1", "user-1"))
        self.assertIsNotNone(self.limiter.check(("pharmacy-1", "user-1")))
        self.assertIsNone(self.limiter.check(("pharmacy-1", "user-2")))
        self.assertIsNone(self.limiter.check(("pharmacy-2", "user-1")))

    def test_idle_keys_are_pruned(self):
        for n in range(5001):
            self.limiter.check(n)
        self.clock.now += 61
        self.limiter.check("new")
        self.assertEqual(len(self.limiter._hits), 1)

    def test_invalid_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            SlidingWindowLimiter(0, 60)
        with self.assertRaises(ValueError):
            SlidingWindowLimiter(1, 0)

    def test_chat_limiter_uses_the_configured_limits(self):
        self.assertEqual(chat_limiter.max_calls, settings.CHAT_RATE_LIMIT_MESSAGES)
        self.assertEqual(chat_limiter.window, settings.CHAT_RATE_LIMIT_WINDOW_SECONDS)

    def test_settings_reject_a_zero_chat_limit(self):
        with self.assertRaises(ValidationError):
            Settings(CHAT_RATE_LIMIT_MESSAGES=0)
        with self.assertRaises(ValidationError):
            Settings(CHAT_RATE_LIMIT_WINDOW_SECONDS=0)


class AiRateLimitTests(unittest.TestCase):
    def test_ai_limiter_is_a_multiple_of_the_chat_budget(self):
        self.assertEqual(ai_limiter.max_calls, settings.CHAT_RATE_LIMIT_MESSAGES * AI_CALLS_PER_CHAT_MESSAGE)
        self.assertEqual(ai_limiter.window, settings.CHAT_RATE_LIMIT_WINDOW_SECONDS)

    def test_key_is_pharmacy_and_member_from_the_token_context(self):
        from server.app.api.ai import ai_rate_limit_key
        self.assertEqual(ai_rate_limit_key({"pharmacy_id": 3, "user_id": 7}), (3, 7))
        self.assertNotEqual(
            ai_rate_limit_key({"pharmacy_id": 3, "user_id": 7}),
            ai_rate_limit_key({"pharmacy_id": 4, "user_id": 7}),
        )

    def test_every_ai_route_carries_the_limit_dependency(self):
        from server.app.api.ai import ai_rate_limit, router
        self.assertIn(ai_rate_limit, [d.dependency for d in router.dependencies])

    def test_over_the_limit_answers_429_with_retry_after(self):
        import asyncio
        from fastapi import HTTPException
        from server.app.api import ai as ai_module

        clock = FakeClock()
        original = ai_module.ai_limiter
        ai_module.ai_limiter = SlidingWindowLimiter(2, 60.0, clock=clock)
        try:
            ctx = {"pharmacy_id": 1, "user_id": 1}
            asyncio.run(ai_module.ai_rate_limit(ctx))
            asyncio.run(ai_module.ai_rate_limit(ctx))
            with self.assertRaises(HTTPException) as caught:
                asyncio.run(ai_module.ai_rate_limit(ctx))
            self.assertEqual(caught.exception.status_code, 429)
            self.assertEqual(caught.exception.headers["Retry-After"], "60")
        finally:
            ai_module.ai_limiter = original


if __name__ == "__main__":
    unittest.main()