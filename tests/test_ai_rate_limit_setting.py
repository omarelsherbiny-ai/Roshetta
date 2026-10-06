# tests/test_ai_rate_limit_setting.py
import unittest
from unittest.mock import patch

from server.app.config import Settings, settings
from server.app.services import rate_limit


class AiRateLimitSettingTests(unittest.TestCase):
    def test_default_is_the_chat_limit_times_five(self):
        with patch.object(settings, "AI_RATE_LIMIT_CALLS", 0), patch.object(settings, "CHAT_RATE_LIMIT_MESSAGES", 20):
            self.assertEqual(rate_limit.ai_call_budget(), 100)

    def test_the_setting_wins_when_above_zero(self):
        with patch.object(settings, "AI_RATE_LIMIT_CALLS", 7), patch.object(settings, "CHAT_RATE_LIMIT_MESSAGES", 20):
            self.assertEqual(rate_limit.ai_call_budget(), 7)

    def test_negative_values_are_refused(self):
        with self.assertRaises(ValueError):
            Settings(AI_RATE_LIMIT_CALLS=-1)

    def test_limiter_uses_the_budget(self):
        limiter = rate_limit.SlidingWindowLimiter(3, 60.0, clock=lambda: 0.0)
        self.assertEqual([limiter.check("k") for _ in range(3)], [None, None, None])
        self.assertEqual(limiter.check("k"), 60)


if __name__ == "__main__":
    unittest.main()