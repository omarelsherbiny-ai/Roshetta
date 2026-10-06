# tests/test_ai_session.py
"""Chat memory id and agent payload (task 9b, command 0)."""
from server.app.services.ai_session import agent_payload, agent_session_id


def _sid(**over):
    args = dict(pharmacy_id=1, user_id=7, role="pharmacist", scopes=["view_inventory", "manage_inventory"], context_id="chat-a")
    args.update(over)
    return agent_session_id(**args)


def test_no_memory_for_placeholder_or_empty_context():
    for value in (None, "", "   ", "default", "DEFAULT"):
        assert _sid(context_id=value) is None


def test_no_memory_without_identity():
    assert _sid(pharmacy_id=None) is None
    assert _sid(user_id=None) is None


def test_same_chat_gets_the_same_id_and_order_of_scopes_does_not_matter():
    assert _sid() == _sid()
    assert _sid(scopes=["a", "b"]) == _sid(scopes=["b", "a"])


def test_other_user_pharmacy_chat_role_or_scopes_get_another_id():
    base = _sid()
    assert _sid(user_id=8) != base
    assert _sid(pharmacy_id=2) != base
    assert _sid(context_id="chat-b") != base
    assert _sid(role="cashier") != base
    assert _sid(scopes=["view_inventory"]) != base


def test_id_is_opaque_and_short():
    sid = _sid()
    assert sid.startswith("rsh-") and len(sid) == 44
    assert "chat-a" not in sid and "pharmacist" not in sid


def test_built_in_role_without_scope_list_is_supported():
    assert _sid(scopes=None) is not None


def test_payload_keeps_token_out_of_the_question():
    payload = agent_payload("hello", "rsh1.secret")
    assert payload["question"] == "hello"
    assert payload["overrideConfig"] == {"vars": {"ROSHETTA_TOKEN": "rsh1.secret"}}
    assert "rsh1.secret" not in payload["question"]


def test_payload_carries_session_id_only_when_given():
    assert "sessionId" not in agent_payload("q", "t", None)["overrideConfig"]
    assert agent_payload("q", "t", "rsh-abc")["overrideConfig"]["sessionId"] == "rsh-abc"