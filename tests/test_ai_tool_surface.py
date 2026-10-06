# tests/test_ai_tool_surface.py
"""The /ai tool list, the prompt tables and the spec stay in step (task 9b, step 3)."""
from server.app.api.ai import create_ai_app
from server.app.services.ai_prompt import TOOL_GUIDE, TOOL_SCOPES, allowed_tools, build_agent_question


def _operations() -> dict:
    spec = create_ai_app("https://example.test").openapi()
    return {
        op["operationId"]: op
        for methods in spec["paths"].values()
        for op in methods.values()
    }


def test_every_operation_has_a_scope_and_a_guide_line():
    assert set(_operations()) == set(TOOL_SCOPES) == set(TOOL_GUIDE)


def test_search_inventory_is_the_general_list_tool_with_paging_only():
    # Session 126: no low_stock, out_of_stock or expiring filters (the model set them by itself).
    names = {parameter["name"] for parameter in _operations()["search_inventory"]["parameters"]}
    assert names == {"search", "category", "limit", "offset"}


def test_pharmacy_summary_needs_stock_or_reports():
    assert "get_pharmacy_summary" in allowed_tools("owner", None)
    assert "get_pharmacy_summary" in allowed_tools("custom", ["view_reports"])
    assert "get_pharmacy_summary" in allowed_tools("custom", ["view_inventory"])
    assert "get_pharmacy_summary" not in allowed_tools("custom", ["log_sale"])


def test_pharmacy_summary_takes_no_identity_argument():
    parameters = _operations()["get_pharmacy_summary"].get("parameters", [])
    assert {p["name"] for p in parameters} <= {"expiring_within_days"}


def test_only_the_two_product_proposals_may_name_a_buy_price():
    for name, op in _operations().items():
        if name not in ("propose_product", "propose_product_update"):
            assert "unit_buy_price" not in str(op)


def test_propose_category_needs_manage_inventory_and_only_a_name():
    assert "propose_category" in allowed_tools("owner", None)
    assert "propose_category" in allowed_tools("custom", ["manage_inventory"])
    assert "propose_category" not in allowed_tools("custom", ["view_inventory"])
    # The raw FastAPI spec keeps a $ref to the request model: read the model itself.
    spec = create_ai_app("https://example.test").openapi()
    schema = spec["components"]["schemas"]["AICategoryProposalRequest"]
    assert set(schema["properties"]) == {"name", "language"}


def test_propose_product_update_needs_manage_inventory_and_never_takes_stock():
    assert "propose_product_update" in allowed_tools("owner", None)
    assert "propose_product_update" in allowed_tools("custom", ["manage_inventory"])
    assert "propose_product_update" not in allowed_tools("custom", ["view_inventory"])
    spec = create_ai_app("https://example.test").openapi()
    schema = spec["components"]["schemas"]["AIProductUpdateRequest"]
    assert set(schema["properties"]) == {
        "item_id", "name_ar", "name_en", "unit_sell_price", "unit_buy_price",
        "min_threshold", "category", "language",
    }
    assert "stock_qty" not in schema["properties"]
    assert schema["required"] == ["item_id"]


def test_propose_restock_needs_log_restock_takes_no_price_and_only_adds_units():
    assert "propose_restock" in allowed_tools("owner", None)
    assert "propose_restock" in allowed_tools("custom", ["log_restock"])
    assert "propose_restock" not in allowed_tools("custom", ["view_inventory"])
    spec = create_ai_app("https://example.test").openapi()
    schema = spec["components"]["schemas"]["AIRestockProposalRequest"]
    assert set(schema["properties"]) == {"item_id", "quantity", "language"}
    assert set(schema["required"]) == {"item_id", "quantity"}
    assert schema["properties"]["quantity"]["exclusiveMinimum"] == 0
    assert "unit_buy_price" not in str(schema)


def test_propose_invite_needs_manage_staff_and_takes_only_a_role_and_settings():
    assert "propose_invite" in allowed_tools("owner", None)
    assert "propose_invite" in allowed_tools("custom", ["manage_staff"])
    assert "propose_invite" not in allowed_tools("custom", ["manage_inventory"])
    spec = create_ai_app("https://example.test").openapi()
    schema = spec["components"]["schemas"]["AIInviteProposalRequest"]
    assert set(schema["properties"]) == {"role_name", "expires_in_days", "max_uses", "language"}
    assert schema["required"] == ["role_name"]
    assert schema["properties"]["expires_in_days"]["default"] == 7
    assert schema["properties"]["expires_in_days"]["maximum"] == 30


def test_agent_question_carries_no_prompt_and_no_tool_list():
    # Session 126: Groq free tier = 8000 tokens per minute, so the prompt lives in the MicroMind
    # website (no prompt in code) and the user message is only the question.
    question = build_agent_question("how many?", "English", "owner", None)
    assert question == "how many?"
    assert "Tools you may use now" not in question
    assert "Answer in" not in question