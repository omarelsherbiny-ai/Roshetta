# tests/test_ai_token.py
"""Unit tests for the short-lived AI access token (no database needed)."""
import json
import time

import pytest
from fastapi import HTTPException

from server.app.services import security


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setattr(security.settings, "SERVER_SECRET_KEY", "unit-test-secret-" + "k" * 32)


def _forge(payload: dict) -> str:
    """Sign an arbitrary payload with the real key, to test claim validation."""
    return security._sign_payload(payload)


def _claims(token: str) -> dict:
    return json.loads(security._b64decode(token.split(".")[1]))


def test_normal_token_has_no_audience():
    token = security.create_access_token(7, 3)
    decoded = security.decode_access_token(token)
    assert decoded["audience"] is None
    assert decoded["user_id"] == 7 and decoded["pharmacy_id"] == 3
    assert "aud" not in _claims(token)


def test_ai_token_carries_audience_and_short_life():
    token = security.create_ai_access_token(7, 3)
    decoded = security.decode_access_token(token)
    assert decoded["audience"] == security.AI_TOKEN_AUDIENCE
    assert decoded["pharmacy_id"] == 3
    claims = _claims(token)
    assert claims["exp"] - claims["iat"] == security.AI_TOKEN_TTL_SECONDS
    assert token.startswith(security.TOKEN_VERSION + ".")


def test_ai_token_life_is_capped_and_never_below_one_second():
    longest = _claims(security.create_ai_access_token(1, 1, ttl_seconds=10**9))
    assert longest["exp"] - longest["iat"] == security.AI_TOKEN_MAX_TTL_SECONDS
    shortest = _claims(security.create_ai_access_token(1, 1, ttl_seconds=-50))
    assert shortest["exp"] - shortest["iat"] == 1


@pytest.mark.parametrize("bad", [None, True, "3", 3.5])
def test_ai_token_requires_a_selected_pharmacy(bad):
    with pytest.raises(ValueError):
        security.create_ai_access_token(7, bad)


def test_ai_token_expires(monkeypatch):
    token = security.create_ai_access_token(7, 3)
    real = time.time()
    monkeypatch.setattr(security.time, "time", lambda: real + security.AI_TOKEN_TTL_SECONDS + 5)
    with pytest.raises(HTTPException) as caught:
        security.decode_access_token(token)
    assert caught.value.status_code == 401


def test_unknown_audience_is_rejected():
    now = int(time.time())
    token = _forge({"sub": 1, "pharmacy_id": 1, "iat": now, "exp": now + 60, "jti": "x", "aud": "admin"})
    with pytest.raises(HTTPException) as caught:
        security.decode_access_token(token)
    assert caught.value.status_code == 401


def test_removing_the_audience_breaks_the_signature():
    """Someone cannot turn an AI token into a full token by editing the payload."""
    token = security.create_ai_access_token(7, 3)
    version, encoded, signature = token.split(".")
    claims = json.loads(security._b64decode(encoded))
    del claims["aud"]
    claims["exp"] += 3600 * 12
    edited = security._b64encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    with pytest.raises(HTTPException) as caught:
        security.decode_access_token(f"{version}.{edited}.{signature}")
    assert caught.value.status_code == 401


def test_wrong_secret_is_rejected(monkeypatch):
    token = security.create_ai_access_token(7, 3)
    monkeypatch.setattr(security.settings, "SERVER_SECRET_KEY", "another-secret-" + "z" * 32)
    with pytest.raises(HTTPException):
        security.decode_access_token(token)