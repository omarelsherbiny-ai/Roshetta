# tests/test_ai_tools.py
import json
import unittest
from typing import Optional

from fastapi import FastAPI, Header, HTTPException

from server.app.services import ai_tools
from server.app.services.ai_tools import AiToolExecutor, MANIFEST_PATH, filter_result

GOOD = "Bearer good-token"

MANIFEST = {
    "version": 1,
    "execution": {"max_tool_calls_per_message": 3},
    "never_return_keys": ["phone", "unit_buy_price", "notes", "paid_by"],
    "denied_argument_names": ["pharmacy_id", "user_id", "token", "role", "scope"],
    "forbidden_path_prefixes": ["/api/auth", "/api/actions"],
    "tools": [
        {
            "name": "search_inventory", "kind": "read", "method": "GET",
            "path": "/api/inventory/items",
            "parameters": [
                {"name": "search", "in": "query", "required": False, "type": "string", "maxLength": 50},
                {"name": "limit", "in": "query", "required": False, "type": "integer", "minimum": 1, "maximum": 100},
                {"name": "kind", "in": "query", "required": False, "type": "string", "enum": ["a", "b"]},
            ],
        },
        {
            "name": "get_item_batches", "kind": "read", "method": "GET",
            "path": "/api/inventory/items/{item_id}/batches",
            "parameters": [{"name": "item_id", "in": "path", "required": True, "type": "integer"}],
        },
        {
            "name": "match_product", "kind": "read", "method": "POST",
            "path": "/api/inventory/match", "parameters": [],
            "body": {"properties": {"query": {"type": "string", "maxLength": 100}}, "required": ["query"]},
        },
        {
            "name": "sneaky_auth", "kind": "read", "method": "GET",
            "path": "/api/auth/me", "parameters": [],
        },
        {
            "name": "write_tool", "kind": "write", "method": "POST",
            "path": "/api/inventory/items", "parameters": [],
        },
    ],
}


def make_app(seen: list) -> FastAPI:
    app = FastAPI()

    def check(authorization: Optional[str]):
        seen.append(authorization)
        if authorization != GOOD:
            raise HTTPException(status_code=401, detail="secret internal detail")

    @app.get("/api/inventory/items")
    async def items(search: Optional[str] = None, limit: int = 10, kind: Optional[str] = None,
                    authorization: Optional[str] = Header(default=None)):
        check(authorization)
        if search == "forbidden":
            raise HTTPException(status_code=403, detail="role cashier cannot do this")
        return [{
            "id": 1, "name_ar": "بانادول", "stock_qty": 12, "unit_buy_price": 20.0,
            "owner": {"phone": "01001234567", "gross_profit": 5, "profit_complete": False},
            "note_text": "call 01001234567 about it", "notes": "customer Ahmed",
        }]

    @app.get("/api/inventory/items/{item_id}/batches")
    async def batches(item_id: int, authorization: Optional[str] = Header(default=None)):
        check(authorization)
        return [{"id": item_id, "quantity": 3}]

    @app.post("/api/inventory/match")
    async def match(payload: dict, authorization: Optional[str] = Header(default=None)):
        check(authorization)
        return {"found": True, "query": payload.get("query")}

    @app.get("/api/auth/me")
    async def auth_me(authorization: Optional[str] = Header(default=None)):
        check(authorization)
        return {"phone": "x"}

    @app.get("/big")
    async def big():
        return {"x": "y" * 10}

    return app


class AiToolExecutorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.seen: list = []
        self.app = make_app(self.seen)

    def executor(self, authorization: Optional[str] = GOOD, manifest: Optional[dict] = None):
        return AiToolExecutor(self.app, authorization, manifest or MANIFEST)

    async def test_valid_call_forwards_the_users_own_authorization_header(self):
        result = await self.executor().call("search_inventory", {"search": "بانادول", "limit": "5"})
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.seen, [GOOD])
        self.assertEqual(result["data"][0]["stock_qty"], 12)

    async def test_missing_authorization_never_reaches_the_app(self):
        result = await self.executor(authorization=None).call("search_inventory", {})
        self.assertFalse(result["ok"])
        self.assertEqual(self.seen, [])

    async def test_endpoint_rejection_returns_a_fixed_message_without_its_detail(self):
        bad = await self.executor("Bearer other").call("search_inventory", {})
        self.assertEqual(bad, {"ok": False, "error": "Authentication failed."})
        denied = await self.executor().call("search_inventory", {"search": "forbidden"})
        self.assertEqual(denied["error"], "This account is not allowed to use this tool.")
        self.assertNotIn("cashier", json.dumps(denied))

    async def test_identity_arguments_are_refused_without_calling_the_app(self):
        for name in ("pharmacy_id", "user_id", "token", "role", "scope"):
            result = await self.executor().call("search_inventory", {name: 1})
            self.assertFalse(result["ok"], name)
        result = await self.executor().call("match_product", {"body": {"query": "x", "pharmacy_id": 7}})
        self.assertFalse(result["ok"])
        self.assertEqual(self.seen, [])

    async def test_undeclared_arguments_and_bad_values_are_refused(self):
        cases = [
            ("search_inventory", {"sort": "name"}),
            ("search_inventory", {"limit": 0}),
            ("search_inventory", {"limit": 101}),
            ("search_inventory", {"limit": True}),
            ("search_inventory", {"kind": "c"}),
            ("search_inventory", {"search": "x" * 51}),
            ("get_item_batches", {}),
            ("get_item_batches", {"item_id": "1/../../auth"}),
            ("get_item_batches", {"item_id": {"a": 1}}),
            ("match_product", {}),
            ("match_product", {"body": {}}),
            ("match_product", {"body": {"other": "x"}}),
        ]
        for name, args in cases:
            result = await self.executor().call(name, args)
            self.assertFalse(result["ok"], (name, args))
        self.assertEqual(self.seen, [])

    async def test_unknown_write_and_forbidden_path_tools_do_not_run(self):
        for name in ("no_such_tool", "write_tool", "sneaky_auth", None, 5):
            result = await self.executor().call(name, {})
            self.assertEqual(result, {"ok": False, "error": "Unknown tool."}, name)
        self.assertEqual(self.seen, [])

    async def test_path_and_body_tools_work(self):
        ex = self.executor()
        batches = await ex.call("get_item_batches", {"item_id": 7})
        self.assertEqual(batches["data"], [{"id": 7, "quantity": 3}])
        match = await ex.call("match_product", {"body": {"query": "بانادول"}})
        self.assertTrue(match["data"]["found"])

    async def test_sensitive_keys_and_numbers_are_removed_from_results(self):
        result = await self.executor().call("search_inventory", {})
        text = json.dumps(result["data"], ensure_ascii=False)
        for forbidden in ("unit_buy_price", "phone", "gross_profit", "profit_complete",
                          "notes", "customer Ahmed", "01001234567"):
            self.assertNotIn(forbidden, text)
        self.assertIn("[number]", text)

    async def test_call_limit_is_enforced_per_executor(self):
        ex = self.executor()
        for _ in range(3):
            self.assertTrue((await ex.call("search_inventory", {}))["ok"])
        fourth = await ex.call("search_inventory", {})
        self.assertEqual(fourth, {"ok": False, "error": "Tool call limit reached for this message."})
        self.assertEqual(len(self.seen), 3)
        self.assertTrue((await self.executor().call("search_inventory", {}))["ok"])

    async def test_large_results_are_refused_not_sent(self):
        manifest = json.loads(json.dumps(MANIFEST))
        manifest["tools"].append({"name": "big", "kind": "read", "method": "GET", "path": "/big", "parameters": []})
        original = ai_tools.MAX_RESULT_CHARS
        ai_tools.MAX_RESULT_CHARS = 5
        try:
            result = await self.executor(manifest=manifest).call("big", {})
        finally:
            ai_tools.MAX_RESULT_CHARS = original
        self.assertFalse(result["ok"])


class FilterResultTests(unittest.TestCase):
    def test_lists_are_capped_and_flagged(self):
        data, truncated = filter_result([{"i": n} for n in range(100)], set())
        self.assertEqual(len(data), ai_tools.MAX_RESULT_ITEMS)
        self.assertTrue(truncated)

    def test_nested_keys_are_matched_case_insensitively(self):
        data, _ = filter_result({"a": [{"Phone": "1", "ok": 1}]}, {"phone"})
        self.assertEqual(data, {"a": [{"ok": 1}]})


class GeneratedManifestTests(unittest.TestCase):
    @unittest.skipUnless(MANIFEST_PATH.exists(), "run scripts/export_micromind_tools.py first")
    def test_generated_manifest_is_read_only_and_identity_free(self):
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        denied = {n.lower() for n in manifest["denied_argument_names"]}
        for tool in manifest["tools"]:
            self.assertEqual(tool["kind"], "read", tool["name"])
            self.assertIn(tool["method"], ("GET", "POST"), tool["name"])
            self.assertFalse(
                any(tool["path"].startswith(p) for p in manifest["forbidden_path_prefixes"]), tool["name"]
            )
            names = {p["name"].lower() for p in tool["parameters"]}
            names |= {n.lower() for n in tool.get("body", {}).get("properties", {})}
            self.assertFalse(names & denied, tool["name"])
            self.assertTrue(all(p["in"] in ("path", "query") for p in tool["parameters"]), tool["name"])
        self.assertLessEqual(manifest["execution"]["max_tool_calls_per_message"], 3)
        self.assertEqual({p["intent"] for p in manifest["proposals"]}, {"log_sale", "log_restock", "log_expense"})


if __name__ == "__main__":
    unittest.main()