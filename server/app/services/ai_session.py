# server/app/services/ai_session.py
"""Chat memory for the MicroMind agent flow (task 9b, command 0).

The flow keeps the conversation under a session id. The id is made HERE, never taken from
the browser: the page only sends a `context_id` (a random value per open chat), and the
server mixes it with the pharmacy, the signed-in user, the role and the scopes from the
token. So a client can only ever reach its own memory, and a change of role or scopes
starts a fresh memory (what the old scopes allowed the model to read must not carry over).

No id (and so no memory) for the placeholder "default" or an empty value: a page that does
not send its own id gets the old one-message behaviour.
"""
import hashlib
from typing import Any, Dict, Iterable, Optional

NO_MEMORY_CONTEXT_IDS = {"", "default"}


def agent_session_id(
    pharmacy_id: Optional[int],
    user_id: Optional[int],
    role: Optional[str],
    scopes: Optional[Iterable[str]],
    context_id: Optional[str],
) -> Optional[str]:
    """The flow's session id for this chat, or None when this chat has no memory."""
    chat = (context_id or "").strip()
    if chat.lower() in NO_MEMORY_CONTEXT_IDS or pharmacy_id is None or user_id is None:
        return None
    scope_part = ",".join(sorted(str(s) for s in scopes)) if scopes is not None else "-"
    raw = f"{pharmacy_id}|{user_id}|{role or ''}|{scope_part}|{chat}"
    return "rsh-" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:40]


def agent_payload(question: str, ai_token: str, session_id: Optional[str] = None) -> Dict[str, Any]:
    """The JSON sent to the agent flow. The token travels only as the per-request variable
    ROSHETTA_TOKEN, never inside the question; the session id only when there is one."""
    override: Dict[str, Any] = {"vars": {"ROSHETTA_TOKEN": ai_token}}
    if session_id:
        override["sessionId"] = session_id
    return {"question": question, "overrideConfig": override}