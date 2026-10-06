# server/app/services/rate_limit.py
"""
Small in-memory sliding-window rate limiter.

State lives in the memory of one server process: with several workers each one
counts on its own, so the real ceiling is (limit x workers). That is enough to stop
a runaway client; move the counters to Redis or the database if exact limits are
needed (not scheduled).
"""
import math
import time
from collections import deque
from typing import Callable, Hashable, Optional

from server.app.config import settings

_PRUNE_ABOVE_KEYS = 5000

# One chat message can make the assistant call several /ai tools, so by default the /ai
# budget is this many calls per allowed chat message in the same window. Set
# AI_RATE_LIMIT_CALLS in server/.env to choose the number of calls directly.
AI_CALLS_PER_CHAT_MESSAGE = 5


def ai_call_budget() -> int:
    """Calls allowed per window on the /ai routes: AI_RATE_LIMIT_CALLS when set (above 0),
    else the chat message limit times AI_CALLS_PER_CHAT_MESSAGE."""
    configured = int(settings.AI_RATE_LIMIT_CALLS or 0)
    if configured > 0:
        return configured
    return settings.CHAT_RATE_LIMIT_MESSAGES * AI_CALLS_PER_CHAT_MESSAGE


class SlidingWindowLimiter:
    def __init__(self, max_calls: int, window_seconds: float, clock: Callable[[], float] = time.monotonic):
        if max_calls < 1 or window_seconds <= 0:
            raise ValueError("max_calls must be at least 1 and window_seconds positive")
        self.max_calls = max_calls
        self.window = window_seconds
        self._clock = clock
        self._hits: dict = {}

    def check(self, key: Hashable) -> Optional[int]:
        """Record one call. Return None if allowed, else seconds to wait (at least 1)."""
        now = self._clock()
        if len(self._hits) > _PRUNE_ABOVE_KEYS:
            self._prune(now)
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] >= self.window:
            hits.popleft()
        if len(hits) >= self.max_calls:
            return max(1, math.ceil(self.window - (now - hits[0])))
        hits.append(now)
        return None

    def _prune(self, now: float) -> None:
        for key in list(self._hits):
            hits = self._hits[key]
            while hits and now - hits[0] >= self.window:
                hits.popleft()
            if not hits:
                del self._hits[key]


# /api/chat: one message can call MicroMind (and later up to 3 tools). The limits
# come from CHAT_RATE_LIMIT_MESSAGES and CHAT_RATE_LIMIT_WINDOW_SECONDS in server/.env.
chat_limiter = SlidingWindowLimiter(
    settings.CHAT_RATE_LIMIT_MESSAGES, settings.CHAT_RATE_LIMIT_WINDOW_SECONDS
)

# /ai tool routes (Session 111, debt 15 a): same window as chat, a multiple of its
# message budget, counted per user and pharmacy after the token is checked.
ai_limiter = SlidingWindowLimiter(
    ai_call_budget(),
    settings.CHAT_RATE_LIMIT_WINDOW_SECONDS,
)