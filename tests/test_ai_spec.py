# tests/test_ai_spec.py
"""Tests for server/app/services/ai_spec.py (the cleaned spec given to MicroMind's toolkit)."""

import copy
import json
import unittest

from server.app.services.ai_spec import toolkit_spec

HEADER = {
    "name": "authorization", "in": "header", "required": False,
    "schema": {"anyOf": [{"type": "string"}, {"type": "null"}], "title": "Authorization"},
}


def raw_spec() -> dict:
    return {
        "openapi": "3.1.0",
        "info": {"title": "T", "version": "1"},
        "servers": [{"url": "https://example.test/ai"}],
        "paths": {
            "/items": {"get": {
                "operationId": "search_inventory", "summary": "Search",
                "parameters": [
                    {"name": "search", "in": "query", "required": False, "schema": {
                        "anyOf": [{"type": "string", "maxLength": 100}, {"type": "null"}], "title": "Search"}},
                    {"name": "limit", "in": "query", "required": False, "schema": {
                        "type": "integer", "maximum": 50, "minimum": 1, "default": 20, "title": "Limit"}},
                    HEADER,
                ],
                "responses": {
                    "200": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/Item"}}}},
                    "422": {"content": {"application/json": {"schema": {"$ref": "#/components/schemas/HTTPValidationError"}}}},
                },
            }},
            "/match": {"post": {
                "operationId": "match_product", "summary": "Match", "parameters": [HEADER],
                "requestBody": {"required": True, "content": {"application/json": {
                    "schema": {"$ref": "#/components/schemas/MatchRequest"}}}},
                "responses": {},
            }},
        },
        "components": {"schemas": {
            "MatchRequest": {
                "type": "object", "title": "MatchRequest", "required": ["query_name"],
                "properties": {"query_name": {"type": "string", "maxLength": 100, "title": "Query Name"}},
            },
            "Item": {"type": "object", "properties": {"id": {"type": "integer"}}},
            "HTTPValidationError": {"type": "object"},
        }},
    }


class ToolkitSpecTests(unittest.TestCase):
    def test_header_parameters_refs_nulls_and_response_schemas_are_removed(self):
        out = toolkit_spec(raw_spec())
        text = json.dumps(out)
        for gone in ('"$ref"', '"null"', '"in": "header"', "HTTPValidationError"):
            self.assertNotIn(gone, text)
        self.assertNotIn('"title"', json.dumps(out["paths"]))  # schema titles are noise; info.title stays
        names = [p["name"] for p in out["paths"]["/items"]["get"]["parameters"]]
        self.assertEqual(names, ["search", "limit"])
        self.assertEqual(out["paths"]["/items"]["get"]["parameters"][0]["schema"], {"type": "string", "maxLength": 100})
        body = out["paths"]["/match"]["post"]["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(body["required"], ["query_name"])
        self.assertNotIn("parameters", out["paths"]["/match"]["post"])

    def test_every_operation_declares_bearer_security_and_keeps_its_operation_id(self):
        out = toolkit_spec(raw_spec())
        self.assertEqual(out["components"]["securitySchemes"]["bearerAuth"], {"type": "http", "scheme": "bearer"})
        ids = []
        for methods in out["paths"].values():
            for operation in methods.values():
                self.assertEqual(operation["security"], [{"bearerAuth": []}])
                ids.append(operation["operationId"])
        self.assertEqual(sorted(ids), ["match_product", "search_inventory"])
        self.assertEqual(out["servers"], [{"url": "https://example.test/ai"}])

    def test_identity_arguments_and_missing_operation_ids_fail_loudly(self):
        for name in ("pharmacy_id", "user_id", "token", "role", "scope"):
            bad = raw_spec()
            bad["paths"]["/items"]["get"]["parameters"].append(
                {"name": name, "in": "query", "schema": {"type": "integer"}})
            with self.assertRaises(ValueError, msg=name):
                toolkit_spec(bad)
        bad_body = raw_spec()
        bad_body["components"]["schemas"]["MatchRequest"]["properties"]["pharmacy_id"] = {"type": "integer"}
        with self.assertRaises(ValueError):
            toolkit_spec(bad_body)
        no_id = raw_spec()
        del no_id["paths"]["/items"]["get"]["operationId"]
        with self.assertRaises(ValueError):
            toolkit_spec(no_id)

    def test_recursive_schemas_are_refused_and_input_is_not_modified(self):
        looping = raw_spec()
        looping["components"]["schemas"]["MatchRequest"] = {"$ref": "#/components/schemas/MatchRequest"}
        with self.assertRaises(ValueError):
            toolkit_spec(looping)
        original = raw_spec()
        snapshot = copy.deepcopy(original)
        toolkit_spec(original)
        self.assertEqual(original, snapshot)


if __name__ == "__main__":
    unittest.main()