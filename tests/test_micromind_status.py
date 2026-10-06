# tests/test_micromind_status.py
import unittest
from unittest.mock import patch

import httpx

from server.app.config import settings
from server.app.services import micromind as mm


class FakeResponse:
    def __init__(self, status=200, data=None, bad_json=False):
        self.status_code = status
        self._data = data
        self._bad_json = bad_json

    def json(self):
        if self._bad_json:
            raise ValueError("not json")
        return self._data


def fake_client(response=None, error=None):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            if error is not None:
                raise error
            return response

    return FakeClient


class MicroMindStatusTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.client = mm.MicroMindClient(api_url="https://flow.invalid/run")
        patcher = patch.object(settings, "USE_MICROMIND", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    async def agent(self, response=None, error=None, token="rsh-test-token"):
        with patch.object(mm.httpx, "AsyncClient", fake_client(response, error)):
            return await self.client.query_agent("question", token, timeout=1.0)

    async def test_success_clears_the_error(self):
        self.client._fail("agent", "timeout", "1s")
        data = await self.agent(FakeResponse(200, {"text": "hello"}))
        self.assertEqual(data, {"text": "hello"})
        self.assertIsNone(self.client.status_text())
        self.assertIsNotNone(self.client.last_ok_at)

    async def test_each_failure_kind_is_recorded(self):
        cases = [
            (FakeResponse(502, {}), None, "http_status", "502"),
            (FakeResponse(200, None, bad_json=True), None, "bad_json", ""),
            (FakeResponse(200, {"text": "  "}), None, "empty_answer", ""),
            (FakeResponse(200, {"other": "x"}), None, "empty_answer", ""),
            (None, httpx.ReadTimeout("slow"), "timeout", "1s"),
            (None, httpx.ConnectError("down"), "exception", "ConnectError"),
        ]
        for response, error, kind, detail in cases:
            with self.subTest(kind=kind, detail=detail):
                self.assertIsNone(await self.agent(response, error))
                self.assertEqual(self.client.last_error["kind"], kind)
                self.assertEqual(self.client.last_error["detail"], detail)
                self.assertIn(kind, self.client.status_text())

    async def test_switched_on_but_unusable_is_named(self):
        self.assertIsNone(await self.agent(token=""))
        self.assertEqual(self.client.last_error["kind"], "no_token")
        self.client.api_url = ""
        self.assertIsNone(await self.agent())
        self.assertEqual(self.client.last_error["kind"], "no_url")

    async def test_status_never_holds_secrets_or_text(self):
        await self.agent(None, httpx.ConnectError("https://flow.invalid/run?key=SECRET question text"))
        text = self.client.status_text()
        for forbidden in ("SECRET", "flow.invalid", "question", "rsh-test-token"):
            self.assertNotIn(forbidden, text)

    async def test_plain_query_records_failures_too(self):
        with patch.object(mm.httpx, "AsyncClient", fake_client(FakeResponse(500, {}))):
            self.assertIsNone(await self.client.query({"question": "q"}))
        self.assertEqual(self.client.last_error["route"], "plain")
        self.assertEqual(self.client.last_error["kind"], "http_status")


if __name__ == "__main__":
    unittest.main()