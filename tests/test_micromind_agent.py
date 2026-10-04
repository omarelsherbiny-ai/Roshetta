# tests/test_micromind_agent.py
"""Unit tests for MicroMindClient.query_agent (the HTTP client is replaced by a fake)."""
import asyncio

from server.app.services import micromind
from server.app.services.micromind import MicroMindClient

URL = "https://flow.example/api/v1/prediction/abc"
TOKEN = "rsh1.fake-token-for-test"


class FakeResponse:
    def __init__(self, status_code=200, body=None):
        self.status_code = status_code
        self._body = body if body is not None else {"text": "ok"}

    def json(self):
        return self._body


def install_fake(monkeypatch, response=None, error=None):
    calls = []

    class FakeClient:
        def __init__(self, timeout=None):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, json=None, headers=None):
            calls.append({"url": url, "json": json, "headers": headers, "timeout": self.timeout})
            if error:
                raise error
            return response or FakeResponse()

    monkeypatch.setattr(micromind.httpx, "AsyncClient", FakeClient)
    return calls


def enable(monkeypatch, timeout=25.0):
    monkeypatch.setattr(micromind.settings, "USE_MICROMIND", True)
    monkeypatch.setattr(micromind.settings, "AI_AGENT_TIMEOUT_SECONDS", timeout)
    # MicroMindClient("") falls back to settings.MICROMIND_API_URL, which holds the real
    # flow URL when server/.env sets it; clear it so these tests do not depend on that file.
    monkeypatch.setattr(micromind.settings, "MICROMIND_API_URL", "")


def run(coro):
    return asyncio.run(coro)


def test_agent_call_is_off_when_micromind_is_off(monkeypatch):
    monkeypatch.setattr(micromind.settings, "USE_MICROMIND", False)
    calls = install_fake(monkeypatch)
    assert run(MicroMindClient(URL).query_agent("hi", TOKEN)) is None
    assert calls == []


def test_agent_call_needs_a_url_and_a_token(monkeypatch):
    enable(monkeypatch)
    calls = install_fake(monkeypatch)
    assert run(MicroMindClient("").query_agent("hi", TOKEN)) is None
    assert run(MicroMindClient(URL).query_agent("hi", "")) is None
    assert calls == []


def test_token_travels_only_as_a_variable_never_in_the_question(monkeypatch):
    enable(monkeypatch, timeout=17.5)
    calls = install_fake(monkeypatch)
    result = run(MicroMindClient(URL).query_agent("What is low on stock?", TOKEN))
    assert result == {"text": "ok"}
    sent = calls[0]
    assert sent["url"] == URL
    assert sent["json"]["question"] == "What is low on stock?"
    assert TOKEN not in sent["json"]["question"]
    assert sent["json"]["overrideConfig"] == {"vars": {"ROSHETTA_TOKEN": TOKEN}}
    assert set(sent["json"]) == {"question", "overrideConfig"}
    assert sent["timeout"] == 17.5


def test_explicit_timeout_wins(monkeypatch):
    enable(monkeypatch, timeout=25.0)
    calls = install_fake(monkeypatch)
    run(MicroMindClient(URL).query_agent("hi", TOKEN, timeout=3.0))
    assert calls[0]["timeout"] == 3.0


def test_non_200_and_errors_give_none(monkeypatch):
    enable(monkeypatch)
    install_fake(monkeypatch, response=FakeResponse(500))
    assert run(MicroMindClient(URL).query_agent("hi", TOKEN)) is None
    install_fake(monkeypatch, error=TimeoutError("slow"))
    assert run(MicroMindClient(URL).query_agent("hi", TOKEN)) is None


def test_plain_query_is_unchanged(monkeypatch):
    enable(monkeypatch)
    calls = install_fake(monkeypatch)
    run(MicroMindClient(URL).query({"question": "hello"}))
    assert calls[0]["json"] == {"question": "hello"}
    assert calls[0]["timeout"] == 6.0