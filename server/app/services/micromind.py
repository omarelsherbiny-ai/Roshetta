# server/app/services/micromind.py
import logging
import httpx
from typing import Dict, Any, Optional
from server.app.config import settings

logger = logging.getLogger(__name__)


class MicroMindClient:
    def __init__(self, api_url: Optional[str] = None):
        self.api_url = api_url or settings.MICROMIND_API_URL

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
                    return response.json()
                else:
                    # Provider bodies can echo user text (including patient or
                    # pharmacy details); keep that content out of server logs.
                    logger.warning("MicroMind returned HTTP status %s", response.status_code)
                    return None
        except Exception as exc:
            # Exception messages may include request URLs or payload fragments.
            logger.info(
                "MicroMind request failed (%s); using the local agent flow.",
                type(exc).__name__,
            )
            return None

    async def query_agent(
        self,
        question: str,
        ai_token: str,
        timeout: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Same workflow call, but the flow may read this pharmacy's data through the /ai
        tools. `ai_token` is the short-lived read-only token from
        `create_ai_access_token`; it travels as the per-request variable
        ROSHETTA_TOKEN, never inside the question text. `query()` is left unchanged.
        Returns response JSON or None (disabled, no token, non-200, timeout, any error).
        """
        if not self.api_url or not settings.USE_MICROMIND or not ai_token:
            return None

        payload = {
            "question": question,
            "overrideConfig": {"vars": {"ROSHETTA_TOKEN": ai_token}},
        }
        wait = timeout if timeout is not None else settings.AI_AGENT_TIMEOUT_SECONDS
        try:
            async with httpx.AsyncClient(timeout=wait) as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code == 200:
                    return response.json()
                # Never log the body or the payload: both can hold user text or the token.
                logger.warning("MicroMind agent returned HTTP status %s", response.status_code)
                return None
        except Exception as exc:
            logger.info(
                "MicroMind agent request failed (%s); using the local answer.",
                type(exc).__name__,
            )
            return None

micromind_client = MicroMindClient()