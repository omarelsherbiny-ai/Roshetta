# server/app/services/security.py
"""Authentication primitives for access tokens and local PIN credentials."""

import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException

from server.app.config import settings


TOKEN_VERSION = "rsh1"
TOKEN_TTL_SECONDS = 60 * 60 * 12
# Tokens handed to the external AI flow: valid only for the /ai tools, a few minutes long.
AI_TOKEN_AUDIENCE = "ai"
AI_TOKEN_TTL_SECONDS = 5 * 60
AI_TOKEN_MAX_TTL_SECONDS = 10 * 60
PIN_HASH_ITERATIONS = 310_000
_INSECURE_EXAMPLE_SECRETS = {
    "roshetta_pharmacy_secret_key_development_mode_only",
    "replace-with-a-unique-random-secret-of-at-least-32-characters",
}


def _secret_key() -> bytes:
    value = settings.SERVER_SECRET_KEY
    if len(value) < 32 or value in _INSECURE_EXAMPLE_SECRETS:
        raise RuntimeError(
            "SERVER_SECRET_KEY must be a unique random value of at least 32 characters."
        )
    return value.encode("utf-8")


def validate_auth_configuration() -> None:
    _secret_key()


def throttle_key(scope: str, identity: str, remote_address: str) -> str:
    material = f"{scope}\0{identity.strip().lower()}\0{remote_address}".encode("utf-8")
    return hmac.new(_secret_key(), material, hashlib.sha256).hexdigest()


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _sign_payload(payload: dict) -> str:
    encoded = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    unsigned = f"{TOKEN_VERSION}.{encoded}"
    signature = hmac.new(_secret_key(), unsigned.encode("ascii"), hashlib.sha256).digest()
    return f"{unsigned}.{_b64encode(signature)}"


def _now_ms() -> int:
    return time.time_ns() // 1_000_000


def create_access_token(user_id: int, pharmacy_id: int | None) -> str:
    now = int(time.time())
    return _sign_payload({
        "sub": user_id,
        "pharmacy_id": pharmacy_id,
        "iat": now,
        # Millisecond issue time: lets a PIN change sign out every token issued before it
        # (User.tokens_valid_after) without a whole-second blind spot.
        "iat_ms": _now_ms(),
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": secrets.token_urlsafe(12),
    })


def create_ai_access_token(
    user_id: int,
    pharmacy_id: int,
    ttl_seconds: int = AI_TOKEN_TTL_SECONDS,
) -> str:
    """Short-lived token for the external AI flow. The `aud` claim makes the main API
    refuse it; only the /ai sub-app accepts it. Live permissions still come from the
    user's current membership, so it can never do more than the user can."""
    if not isinstance(pharmacy_id, int) or isinstance(pharmacy_id, bool):
        raise ValueError("An AI token needs a selected pharmacy.")
    ttl = max(1, min(int(ttl_seconds), AI_TOKEN_MAX_TTL_SECONDS))
    now = int(time.time())
    return _sign_payload({
        "sub": user_id,
        "pharmacy_id": pharmacy_id,
        "iat": now,
        "iat_ms": _now_ms(),
        "exp": now + ttl,
        "jti": secrets.token_urlsafe(12),
        "aud": AI_TOKEN_AUDIENCE,
    })


def decode_access_token(token: str) -> dict:
    try:
        version, encoded, supplied_signature = token.split(".")
        if version != TOKEN_VERSION:
            raise ValueError("Unsupported token version")
        unsigned = f"{version}.{encoded}"
        expected_signature = hmac.new(
            _secret_key(), unsigned.encode("ascii"), hashlib.sha256
        ).digest()
        if not hmac.compare_digest(expected_signature, _b64decode(supplied_signature)):
            raise ValueError("Invalid signature")
        payload = json.loads(_b64decode(encoded))
        now = int(time.time())
        if (
            not isinstance(payload.get("sub"), int)
            or (payload.get("pharmacy_id") is not None and not isinstance(payload.get("pharmacy_id"), int))
            or not isinstance(payload.get("exp"), int)
            or not isinstance(payload.get("iat"), int)
            or not isinstance(payload.get("jti"), str)
            or not payload["jti"]
            or payload["exp"] <= now
            or payload["iat"] > now + 60
            or payload.get("aud") not in (None, AI_TOKEN_AUDIENCE)
            or (payload.get("iat_ms") is not None
                and (not isinstance(payload["iat_ms"], int) or isinstance(payload["iat_ms"], bool)))
        ):
            raise ValueError("Invalid or expired claims")
        return {
            "user_id": payload["sub"],
            "pharmacy_id": payload.get("pharmacy_id"),
            "token_id": payload["jti"],
            "token_expires_at": payload["exp"],
            # Tokens issued before iat_ms existed fall back to their whole-second time.
            "issued_at_ms": payload["iat_ms"] if payload.get("iat_ms") is not None else payload["iat"] * 1000,
            "audience": payload.get("aud"),
        }
    except RuntimeError:
        raise
    except Exception as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.") from exc


def hash_pin(pin: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", pin.encode("utf-8"), salt, PIN_HASH_ITERATIONS, dklen=32
    )
    return _b64encode(salt), _b64encode(digest)


def verify_pin(pin: str, salt: str, expected_hash: str) -> bool:
    try:
        actual = hashlib.pbkdf2_hmac(
            "sha256", pin.encode("utf-8"), _b64decode(salt), PIN_HASH_ITERATIONS, dklen=32
        )
        return hmac.compare_digest(actual, _b64decode(expected_hash))
    except (ValueError, TypeError):
        return False


def verify_legacy_pin(pin: str, stored_pin: str | None) -> bool:
    return bool(stored_pin) and hmac.compare_digest(pin.encode("utf-8"), stored_pin.encode("utf-8"))


def validate_pin(pin: str) -> str:
    value = pin.strip()
    if not 4 <= len(value) <= 6 or not value.isascii() or not value.isdigit():
        raise HTTPException(status_code=422, detail="PIN must contain 4 to 6 digits.")
    return value