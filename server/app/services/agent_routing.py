# server/app/services/agent_routing.py
"""Which chat messages go to the MicroMind agent first (Session 123, step 4).

Pure functions, no database and no settings import, so the rules are testable alone.
`chat.py` calls `should_use_agent` once per message after the local pipeline has set
the intent. The local answer is always computed first and stays the fallback.
"""

# Intents whose confirmation card the local pipeline builds. They stay local until the
# matching propose_* tool exists (step 5 of task 9b); MicroMind only writes the sentence.
# Restock and a new product are no longer among them (Session 126, Omar: the model decides and
# prepares the card through propose_restock / propose_product, no local regex and no fixed hint).
LOCAL_WRITE_INTENTS = frozenset({"log_sale", "log_expense"})

# Intents the model handles through a propose_* tool while the tools are on (Session 126):
# restock (propose_restock) and a new product (propose_product). The local card is dropped
# for them in chat.py and the card is read back from the database.
AGENT_WRITE_INTENTS = frozenset({"log_restock", "create_product"})

# Card types an agent tool may prepare (a PendingAction row) and the scope the member
# needs to be shown one. Step 5 added create_category, update_product and create_invite,
# each with the scope its confirm needs.
AGENT_CARD_SCOPES = {
    "create_product": "manage_inventory",
    "create_category": "manage_inventory",
    "update_product": "manage_inventory",
    "create_invite": "manage_staff",
    "log_restock": "log_restock",
}


def should_use_agent(
    intent: str | None,
    *,
    tools_enabled: bool,
    can_view_inventory: bool,
    can_view_reports: bool,
    is_cashier: bool,
    local_card_missing: bool = False,
    write_denied: bool = False,
) -> bool:
    """True when this message is answered by the agent (with the /ai tools).

    `local_card_missing` is unused since Session 126 (every new-product request goes to the
    agent unless the write is denied; propose_product itself needs manage_inventory).
    """
    if not tools_enabled:
        return False
    if intent in AGENT_WRITE_INTENTS:
        # The model finds the product (or reads the new-product details) and calls the
        # propose_* tool. A member the local check already refused keeps the local refusal
        # (the tool would answer 403 anyway). `local_card_missing` is kept for old callers;
        # a new product now goes to the agent whether or not the local parser built a card.
        return not write_denied
    if intent in LOCAL_WRITE_INTENTS:
        return False
    if intent == "general_chat":
        # Every member may use the agent: each /ai route enforces the member's scopes,
        # and get_my_activity needs none.
        return True
    if intent == "query_stock":
        return can_view_inventory
    if intent == "query_finance":
        # A cashier's local summary counts only their own sales (Waiting item 16).
        return can_view_reports and not is_cashier
    # Any other local intent (prescription_scan, invoice_scan, unknown) keeps its own
    # local answer.
    return False