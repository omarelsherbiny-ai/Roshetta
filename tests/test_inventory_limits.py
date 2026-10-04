# tests/test_inventory_limits.py
import asyncio
import inspect
import unittest

from server.app.api import ai as ai_module
from server.app.api import inventory as inventory_module


def _bounds(function, name):
    default = inspect.signature(function).parameters[name].default
    ge = next((m.ge for m in default.metadata if hasattr(m, "ge")), None)
    le = next((m.le for m in default.metadata if hasattr(m, "le")), None)
    return default.default, ge, le


class InventoryLimitTests(unittest.TestCase):
    def test_price_history_has_a_default_and_a_ceiling(self):
        self.assertEqual(_bounds(inventory_module.get_inventory_price_history, "limit"), (100, 1, 500))

    def test_low_stock_has_a_default_and_a_ceiling(self):
        self.assertEqual(_bounds(inventory_module.list_low_stock, "limit"), (500, 1, 1000))

    def test_ai_price_history_passes_its_own_limit_to_the_endpoint(self):
        # The /ai route calls the endpoint function directly, so it must hand over a real
        # number: otherwise the Query default object would be used as the limit.
        seen = {}

        async def fake(**kwargs):
            seen.update(kwargs)
            return []

        original = ai_module.get_inventory_price_history
        ai_module.get_inventory_price_history = fake
        try:
            asyncio.run(ai_module.get_item_price_history(item_id=1, db=None, ctx={}))
        finally:
            ai_module.get_inventory_price_history = original
        self.assertEqual(seen["limit"], 50)


if __name__ == "__main__":
    unittest.main()