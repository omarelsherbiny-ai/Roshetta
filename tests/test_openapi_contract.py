# tests/test_openapi_contract.py
"""Keep the checked-in API contract aligned with the FastAPI application."""

import json
import os
import unittest


os.environ.setdefault("SERVER_SECRET_KEY", "roshetta-openapi-contract-test-secret")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("SEED_DEMO_DATA", "false")
os.environ.setdefault("USE_MICROMIND", "false")
os.environ.setdefault("OCR_PROVIDER", "disabled")

from scripts.export_openapi import CONTRACT_PATH, render_contract  # noqa: E402


class OpenAPIContractTests(unittest.TestCase):
    @staticmethod
    def _has_constrained_success_schema(schema):
        if not isinstance(schema, dict):
            return False
        if schema.get("$ref"):
            return True
        if schema.get("properties"):
            return True
        if schema.get("type") in {"string", "integer", "number", "boolean"}:
            return True
        if schema.get("type") == "array":
            return OpenAPIContractTests._has_constrained_success_schema(schema.get("items"))
        return False

    def test_checked_in_contract_matches_fastapi_routes(self):
        self.assertEqual(CONTRACT_PATH.read_text(encoding="utf-8"), render_contract())

    def test_contract_documents_bearer_auth_and_retired_endpoints(self):
        spec = json.loads(render_contract())
        self.assertEqual(
            spec["components"]["securitySchemes"]["RoshettaBearer"],
            {"type": "http", "scheme": "bearer"},
        )
        self.assertEqual(spec["paths"]["/api/auth/join"]["post"]["responses"]["410"]["description"], "Gone")
        self.assertEqual(spec["paths"]["/api/auth/invite"]["post"]["responses"]["410"]["description"], "Gone")

    def test_all_declared_success_responses_have_constrained_schemas(self):
        spec = json.loads(render_contract())
        for path, path_item in spec["paths"].items():
            for method, operation in path_item.items():
                if method not in {"get", "post", "put", "patch", "delete"}:
                    continue
                response = operation.get("responses", {}).get("200")
                if response is None:
                    continue
                with self.subTest(path=path, method=method):
                    content = response.get("content", {})
                    self.assertTrue(content, "success response must document its media type")
                    self.assertTrue(
                        any(self._has_constrained_success_schema(media.get("schema")) for media in content.values()),
                        "success response must not be an unconstrained object",
                    )

    def test_inventory_success_responses_are_typed(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/inventory/categories", "get"),
            ("/api/inventory/summary", "get"),
            ("/api/inventory/items", "get"),
            ("/api/inventory/items/{item_id}", "get"),
            ("/api/inventory/items/{item_id}/price-history", "get"),
            ("/api/inventory/items/{item_id}/batches", "get"),
            ("/api/inventory/low-stock", "get"),
            ("/api/inventory/create", "post"),
            ("/api/inventory/items/{item_id}", "put"),
            ("/api/inventory/match", "post"),
            ("/api/inventory/items/{item_id}/restock", "post"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                response = spec["paths"][path][method]["responses"]["200"]
                schema = response["content"]["application/json"]["schema"]
                self.assertTrue(schema)

    def test_ledger_success_responses_are_typed(self):
        spec = json.loads(render_contract())
        for path in (
            "/api/ledger/daily-summary",
            "/api/ledger/entries",
            "/api/ledger/activity",
        ):
            with self.subTest(path=path):
                response = spec["paths"][path]["get"]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_personal_account_auth_responses_are_typed(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/auth/logout", "post"),
            ("/api/auth/account-scope", "post"),
            ("/api/auth/register-user", "post"),
            ("/api/auth/account-login", "post"),
            ("/api/auth/me", "get"),
            ("/api/auth/me", "patch"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                response = spec["paths"][path][method]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_action_flow_success_responses_are_typed(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/actions/pending", "get"),
            ("/api/actions/{action_id}/confirm", "post"),
            ("/api/actions/{action_id}/cancel", "post"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                response = spec["paths"][path][method]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_pharmacy_auth_and_profile_success_responses_are_typed(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/auth/register-pharmacy", "post"),
            ("/api/auth/login", "post"),
            ("/api/auth/switch-pharmacy", "post"),
            ("/api/auth/staff", "get"),
            ("/api/auth/profile", "get"),
            ("/api/auth/profile", "post"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                response = spec["paths"][path][method]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_personal_profile_success_responses_are_typed(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/me", "get"),
            ("/api/me", "patch"),
            ("/api/me/photo", "post"),
            ("/api/me/activity", "get"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                response = spec["paths"][path][method]["responses"]["200"]
                self.assertIn("schema", response["content"]["application/json"])

    def test_pharmacy_hub_and_staff_success_responses_have_constrained_schemas(self):
        spec = json.loads(render_contract())
        expected = {
            ("/api/pharmacies", "get"),
            ("/api/pharmacies", "post"),
            ("/api/pharmacies/{pharmacy_id}/select", "post"),
            ("/api/pharmacies/{pharmacy_id}/summary", "get"),
            ("/api/pharmacies/{pharmacy_id}/roles", "get"),
            ("/api/pharmacies/{pharmacy_id}/roles", "post"),
            ("/api/pharmacies/{pharmacy_id}/roles/{role_id}", "put"),
            ("/api/pharmacies/{pharmacy_id}/roles/{role_id}", "delete"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/role", "put"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/role", "patch"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}", "delete"),
            ("/api/pharmacies/{pharmacy_id}/invitations", "post"),
            ("/api/pharmacies/{pharmacy_id}/invitations", "get"),
            ("/api/pharmacies/{pharmacy_id}/invitations/{invitation_id}", "delete"),
            ("/api/pharmacies/invitations/accept", "post"),
            ("/api/staff/me/activity", "get"),
            ("/api/staff/me/summary", "get"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/summary", "get"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/schedule", "get"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/schedule", "put"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/compensation", "get"),
            ("/api/pharmacies/{pharmacy_id}/staff/{user_id}/compensation", "post"),
        }
        for path, method in expected:
            with self.subTest(path=path, method=method):
                schema = spec["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
                self.assertTrue(
                    schema.get("$ref") or schema.get("properties") or schema.get("items"),
                    f"{method.upper()} {path} has an unconstrained success response",
                )

if __name__ == "__main__":
    unittest.main()