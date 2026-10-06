# tests/test_agent_routing.py
import unittest

from server.app.services.agent_routing import (
    AGENT_CARD_SCOPES,
    LOCAL_WRITE_INTENTS,
    should_use_agent,
)


def route(intent, **kw):
    args = dict(tools_enabled=True, can_view_inventory=True, can_view_reports=True, is_cashier=False)
    args.update(kw)
    return should_use_agent(intent, **args)


class AgentRoutingTests(unittest.TestCase):
    def test_tools_off_never_uses_agent(self):
        for intent in ("general_chat", "query_stock", "query_finance", "log_sale", "log_restock"):
            self.assertFalse(route(intent, tools_enabled=False), intent)
        self.assertFalse(route("create_product", tools_enabled=False, local_card_missing=True))

    def test_general_chat_for_every_member_even_without_view_scopes(self):
        self.assertTrue(route("general_chat", can_view_inventory=False, can_view_reports=False))

    def test_local_write_intents_stay_local(self):
        for intent in LOCAL_WRITE_INTENTS:
            self.assertFalse(route(intent), intent)

    def test_restock_goes_to_the_agent_unless_the_write_is_denied(self):
        self.assertNotIn("log_restock", LOCAL_WRITE_INTENTS)
        self.assertTrue(route("log_restock"))
        self.assertTrue(route("log_restock", can_view_inventory=False, can_view_reports=False))
        self.assertFalse(route("log_restock", write_denied=True))
        self.assertFalse(route("log_restock", tools_enabled=False))

    def test_new_product_goes_to_agent_only_when_local_card_is_missing(self):
        self.assertFalse(route("create_product"))
        self.assertFalse(route("create_product", local_card_missing=False))
        self.assertTrue(route("create_product", local_card_missing=True))

    def test_local_card_missing_does_not_affect_other_write_intents(self):
        for intent in LOCAL_WRITE_INTENTS - {"create_product"}:
            self.assertFalse(route(intent, local_card_missing=True), intent)

    def test_stock_question_needs_view_inventory(self):
        self.assertTrue(route("query_stock"))
        self.assertFalse(route("query_stock", can_view_inventory=False))

    def test_finance_question_needs_view_reports_and_not_cashier(self):
        self.assertTrue(route("query_finance"))
        self.assertFalse(route("query_finance", can_view_reports=False))
        self.assertFalse(route("query_finance", is_cashier=True))

    def test_other_local_intents_keep_local_answer(self):
        for intent in ("prescription_scan", "invoice_scan", "something_new", None):
            self.assertFalse(route(intent), intent)

    def test_agent_cards_have_a_scope(self):
        self.assertEqual(AGENT_CARD_SCOPES["create_product"], "manage_inventory")
        self.assertEqual(AGENT_CARD_SCOPES["create_category"], "manage_inventory")
        self.assertEqual(AGENT_CARD_SCOPES["update_product"], "manage_inventory")
        self.assertEqual(AGENT_CARD_SCOPES["create_invite"], "manage_staff")
        self.assertEqual(AGENT_CARD_SCOPES["log_restock"], "log_restock")
        self.assertNotIn("adjust_stock", AGENT_CARD_SCOPES)


if __name__ == "__main__":
    unittest.main()