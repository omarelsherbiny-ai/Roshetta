# tests/test_micromind_retry.py
"""An empty agent answer is asked again once; no other failure is retried (Session 125)."""
import unittest
from unittest.mock import patch

import httpx

from server.app.config import settings
from server.app.services import micromind as mm


class FakeResponse:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data

    def json(self):
        return self._data


def counting_client(responses, calls):
    """A client whose successive posts return `responses` in order (the last one repeats)."""

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            index = min(len(calls), len(responses) - 1)
            calls.append(1)
            item = responses[index]
            if isinstance(item, Exception):
                raise item
            return item

    return FakeClient


class AgentRetryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = mm.MicroMindClient(api_url="https://flow.invalid/run")
        patcher = patch.object(settings, "USE_MICROMIND", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def run_agent(self, responses, **kwargs):
        calls = []
        with patch.object(mm.httpx, "AsyncClient", counting_client(responses, calls)):
            data = await self.client.query_agent("question", "rsh-test-token", timeout=1.0, **kwargs)
        return data, len(calls)

    async def test_empty_then_text_returns_the_second_answer(self):
        data, calls = await self.run_agent([FakeResponse(200, {"text": ""}), FakeResponse(200, {"text": "ok"})])
        self.assertEqual(data, {"text": "ok"})
        self.assertEqual(calls, 2)
        self.assertIsNone(self.client.status_text())

    async def test_empty_twice_gives_up_after_two_calls_and_records_it(self):
        data, calls = await self.run_agent([FakeResponse(200, {"text": " "})])
        self.assertIsNone(data)
        self.assertEqual(calls, 2)
        self.assertEqual(self.client.last_error["kind"], "empty_answer")

    async def test_text_on_the_first_call_is_one_call(self):
        data, calls = await self.run_agent([FakeResponse(200, {"text": "hello"})])
        self.assertEqual(data, {"text": "hello"})
        self.assertEqual(calls, 1)

    async def test_other_failures_are_not_retried(self):
        for response in (FakeResponse(502, {}), httpx.ReadTimeout("slow"), httpx.ConnectError("down")):
            with self.subTest(failure=type(response).__name__):
                data, calls = await self.run_agent([response])
                self.assertIsNone(data)
                self.assertEqual(calls, 1)

    async def test_retries_can_be_switched_off(self):
        data, calls = await self.run_agent([FakeResponse(200, {"text": ""})], empty_retries=0)
        self.assertIsNone(data)
        self.assertEqual(calls, 1)


if __name__ == "__main__":
    unittest.main()