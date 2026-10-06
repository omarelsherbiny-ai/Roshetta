# tests/test_ai_spec_request_body_hint.py
"""Every POST tool tells the model that its fields go inside one object named RequestBody;
GET tools are left alone (Session 127)."""
from server.app.services.ai_spec import REQUEST_BODY_HINT, toolkit_spec


def _raw():
    body = {
        "content": {"application/json": {"schema": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "unit_sell_price": {"type": "number"}},
        }}}
    }
    return {
        "openapi": "3.1.0",
        "paths": {
            "/propose-product": {"post": {"operationId": "propose_product", "summary": "Prepare a card to add a product", "requestBody": body}},
            "/propose-category": {"post": {"operationId": "propose_category", "summary": "Prepare a category card.", "requestBody": body}},
            "/search": {"get": {"operationId": "search_inventory", "summary": "Search products"}},
        },
    }


def test_post_tools_carry_the_request_body_hint():
    paths = toolkit_spec(_raw())["paths"]
    for path in ("/propose-product", "/propose-category"):
        operation = paths[path]["post"]
        assert operation["summary"].endswith(REQUEST_BODY_HINT)
        assert operation["requestBody"]["description"] == REQUEST_BODY_HINT
    assert paths["/propose-product"]["post"]["summary"] == "Prepare a card to add a product. " + REQUEST_BODY_HINT
    assert paths["/propose-category"]["post"]["summary"] == "Prepare a category card. " + REQUEST_BODY_HINT


def test_get_tools_are_unchanged():
    operation = toolkit_spec(_raw())["paths"]["/search"]["get"]
    assert operation["summary"] == "Search products"
    assert "requestBody" not in operation


def test_hint_has_no_word_the_exporter_forbids():
    for word in ("$ref", "unit_buy_price", "confirmed_by", "notes", "authorization"):
        assert word not in REQUEST_BODY_HINT