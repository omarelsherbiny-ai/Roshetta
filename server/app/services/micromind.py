# server/app/services/micromind.py
import logging
from datetime import datetime, timezone
import httpx
from typing import Dict, Any, Optional
from server.app.config import settings
from server.app.services.ai_session import agent_payload
from server.app.services.token_fp import token_fingerprint

logger = logging.getLogger(__name__)


def _answer_text(data: Any) -> Optional[str]:
    """The text of a workflow answer (`text`, `answer` or `output`), or None."""
    if not isinstance(data, dict):
        return None
    for key in ("text", "answer", "output"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


class MicroMindClient:
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or settings.MICROMIND_API_URL
        # The reason the last call failed, kept so a broken connection is not mistaken for a
        # disabled one (shown by /health). Only a short kind and a status code or exception
        # type: never the URL, the payload, the token or any text.
        self.last_error: Optional[Dict[str, str]] = None
        self.last_ok_at: Optional[str] = None
        # Session 126: a chat session whose last answer was empty is skipped from then on (the
        # flow's memory holds an empty assistant turn, and the model then keeps answering
        # nothing). The value counts how many times that session was replaced.
        self._empty_epoch: Dict[str, int] = {}

    def _session_for(self, session_id: Optional[str]) -> Optional[str]:
        """The session id to send: the chat's own id, or its fresh replacement after an empty answer."""
        if not session_id:
            return None
        epoch = self._empty_epoch.get(session_id, 0)
        return session_id if epoch == 0 else f"{session_id}-r{epoch}"

    def _retire_session(self, session_id: Optional[str]) -> None:
        if not session_id:
            return
        if len(self._empty_epoch) > 500:
            self._empty_epoch.clear()
        self._empty_epoch[session_id] = self._empty_epoch.get(session_id, 0) + 1

    def _fail(self, route: str, kind: str, detail: str = "") -> None:
        self.last_error = {
            "route": route,
            "kind": kind,
            "detail": detail,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }

    def _ok(self) -> None:
        self.last_error = None
        self.last_ok_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def status_text(self) -> Optional[str]:
        """One short line for /health about the last failure, or None when the last call worked."""
        if not self.last_error:
            return None
        err = self.last_error
        detail = f" {err['detail']}" if err.get("detail") else ""
        return f"{err['route']}: {err['kind']}{detail} at {err['at']}"

    async def query(self, payload: Dict[str, Any], timeout: float = 6.0) -> Optional[Dict[str, Any]]:
        """
        Sends prediction query to MicroMind workflow API.
        Returns response JSON or None if unavailable/timed out.
        """
        if not self.api_url or not settings.USE_MICROMIND:
            return None

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code == 200:
                    data = response.json()
                    self._ok()
                    return data
                else:
                    # Provider bodies can echo user text (including patient or
                    # pharmacy details); keep that content out of server logs.
                    logger.warning("MicroMind returned HTTP status %s", response.status_code)
                    self._fail("plain", "http_status", str(response.status_code))
                    return None
        except Exception as exc:
            # Exception messages may include request URLs or payload fragments.
            logger.info(
                "MicroMind request failed (%s); using the local agent flow.",
                type(exc).__name__,
            )
            self._fail("plain", "exception", type(exc).__name__)
            return None

    async def _agent_once(self, payload: Dict[str, Any], wait: float) -> Optional[Dict[str, Any]]:
        """One call of the agent flow. Returns the answer JSON or None; every failure is
        recorded in `last_error` (kind http_status, bad_json, empty_answer, timeout, exception)."""
        try:
            async with httpx.AsyncClient(timeout=wait) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code != 200:
                    # Never log the body or the payload: both can hold user text or the token.
                    logger.warning("MicroMind agent returned HTTP status %s", response.status_code)
                    self._fail("agent", "http_status", str(response.status_code))
                    return None
                try:
                    data = response.json()
                except ValueError:
                    logger.warning("MicroMind agent answered with a body that is not JSON")
                    self._fail("agent", "bad_json")
                    return None
                if _answer_text(data) is None:
                    logger.warning("MicroMind agent answered without any text (keys text, answer, output)")
                    self._fail("agent", "empty_answer")
                    return None
                self._ok()
                return data
        except httpx.TimeoutException:
            logger.warning("MicroMind agent timed out after %s seconds", wait)
            self._fail("agent", "timeout", f"{wait:g}s")
            return None
        except Exception as exc:
            logger.warning(
                "MicroMind agent request failed (%s); using the local answer.",
                type(exc).__name__,
            )
            self._fail("agent", "exception", type(exc).__name__)
            return None

    async def query_agent(
        self,
        question: str,
        ai_token: str,
        timeout: Optional[float] = None,
        session_id: Optional[str] = None,
        empty_retries: int = 1,
    ) -> Optional[Dict[str, Any]]:
        """
        Same workflow call, but the flow may read this pharmacy's data through the /ai
        tools. `ai_token` is the short-lived read-only token from
        `create_ai_access_token`; it travels as the per-request variable
        ROSHETTA_TOKEN, never inside the question text. `session_id` (made by
        `ai_session.agent_session_id`) lets the flow keep the chat's memory; None means no
        memory. `query()` is left unchanged.
        An answer with no text (the flow sometimes ends a tool turn with an empty string,
        Session 125) is asked again up to `empty_retries` times; no other failure is retried
        (a timeout would double the wait, an HTTP error will not fix itself in a second).
        Returns response JSON or None (disabled, no token, non-200, timeout, any error).
        Every failure is recorded in `last_error` and logged as a warning with its kind.
        """
        if not self.api_url or not settings.USE_MICROMIND or not ai_token:
            if settings.USE_MICROMIND:
                # Switched on but unusable: say which part is missing.
                self._fail("agent", "no_url" if not self.api_url else "no_token")
                logger.warning("MicroMind agent not called: %s", "MICROMIND_API_URL is empty" if not self.api_url else "no AI token")
            return None

        # Token diagnostics (Session 125): fingerprint and length only, never the token.
        self.last_token_fp = token_fingerprint(ai_token)
        logger.warning(
            "[token-diag] agent call: ai token fp=%s len=%d prefix_ok=%s | server key fp=%s len=%d",
            self.last_token_fp, len(ai_token), ai_token.startswith("rsh1."),
            token_fingerprint(settings.SERVER_SECRET_KEY), len(settings.SERVER_SECRET_KEY or ""),
        )
        if settings.AI_DEBUG_PRINT_TOKEN:
            # Debug switch, off by default. Never leave it on or paste this line anywhere.
            logger.warning("[token-diag] RAW ai token: %s", ai_token)
        wait = timeout if timeout is not None else settings.AI_AGENT_TIMEOUT_SECONDS
        for attempt in range(1 + max(0, empty_retries)):
            payload = agent_payload(question, ai_token, self._session_for(session_id))
            data = await self._agent_once(payload, wait)
            if data is not None:
                return data
            if not self.last_error or self.last_error.get("kind") != "empty_answer":
                return None
            # The empty answer is now in that session's memory: leave the session (this retry
            # and the chat's next messages use a fresh one, without the earlier turns).
            self._retire_session(session_id)
            if attempt < empty_retries:
                logger.warning("MicroMind agent answer was empty; asking once more on a fresh session")
        return None


micromind_client = MicroMindClient()