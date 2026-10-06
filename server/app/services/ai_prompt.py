# server/app/services/ai_prompt.py
"""What the MicroMind agent path sends (Session 109, W8 c; prompt removed in Session 126).

There is NO prompt in code: the assistant's prompt lives in the MicroMind website (the flow's
system message) and is pasted there; see "MicroMind / AI integration contract" in
ROSHETTA_PROJECT.md. It is not sent with each question because the Groq free tier allows only
8000 tokens per minute.
`build_agent_question` is the only place the text sent to the agent flow is assembled: the
already scrubbed user text, nothing else. The tool list is the OpenAPI spec
the toolkit imports; the member's scopes are enforced by the /ai routes (a 403 answer).
Nothing here holds data about the pharmacy or the person.
"""
from typing import Iterable, Optional

from server.app.db.models import has_permission

# operation_id of every /ai tool -> what the signed-in member must hold.
#   a scope name     -> has_permission(role, scope, scopes)
#   "owner"          -> the built-in owner role only (the endpoint enforces it)
#   a tuple          -> any one of those scopes (the endpoint also gates each source)
#   None             -> any member with a selected pharmacy (own figures only)
# tests/test_ai_prompt.py fails if a /ai operation is missing here.
TOOL_SCOPES: dict = {
    "search_inventory": "view_inventory",
    "match_product": "view_inventory",
    "get_item_batches": "view_inventory",
    "get_item_price_history": "view_inventory",
    "list_categories": "view_inventory",
    "get_inventory_summary": "view_inventory",
    "get_pharmacy_summary": ("view_inventory", "view_reports"),
    "list_ledger_entries": "view_reports",
    "get_sales_summary": "view_reports",
    "list_supplier_payables": "view_reports",
    "get_payables_summary": "view_reports",
    "list_records_timeline": ("view_reports", "view_inventory", "view_audit"),
    "get_my_activity": None,
    "list_roles": "owner",
    "propose_product": "manage_inventory",
    "propose_category": "manage_inventory",
    "propose_product_update": "manage_inventory",
    "propose_restock": "log_restock",
    "propose_invite": "manage_staff",
}

# Kept for the tests that tie the tables to the spec; no longer sent to the model (Session 126).
TOOL_GUIDE: dict = {
    "search_inventory": "list or search products by name, active ingredient, barcode or category; with no search and no category it lists every product alphabetically (limit up to 50, offset to read the next page)",
    "match_product": "find one product by a spoken or typed name; when the spelling is off it returns the closest products as suggestions",
    "get_item_batches": "stock lots of one product with expiry dates (needs the product id from a search)",
    "get_item_price_history": "selling-price changes of one product (needs the product id)",
    "list_categories": "categories and how many products each has",
    "get_inventory_summary": "total products, units and selling value in stock",
    "get_pharmacy_summary": "one-call overview for today: stock totals, low, out-of-stock and expiring counts, today's sales and expenses, what is owed to suppliers; `omitted` lists the parts this role may not see",
    "list_ledger_entries": "recent sales, expenses and restocks",
    "get_sales_summary": "sales and expense totals for a day or a range",
    "list_supplier_payables": "credit restocks, what was paid and what is still owed",
    "get_payables_summary": "total still owed to suppliers",
    "list_records_timeline": "what happened lately: records, product and category changes, staff and settings changes",
    "get_my_activity": "the signed-in person's own totals for a period",
    "list_roles": "custom roles and their scopes (owner only)",
    "propose_product": "prepare a card to add a NEW product (needs name and sell price); the user reviews and confirms it in the app",
    "propose_category": "prepare a card to create a NEW product category (needs only the name); the user reviews and confirms it in the app",
    "propose_product_update": "prepare a card to CHANGE an existing product's name, sell price, buy price, low-stock level or category (needs the product id from a search or match result and at least one new value; stock cannot be changed); the user reviews and confirms it in the app",
    "propose_restock": "prepare a card that ADDS units to an existing product's stock (needs the product id from a search or match result and the quantity to add, not the new total; the buy price comes from the product and the user can edit it on the card); the user reviews and confirms it in the app",
    "propose_invite": "prepare a card that creates an invitation link for a role (needs the role name: a built-in role or a custom role's name; expires in 7 days unless the user says otherwise); the link does not exist until the user confirms in the app and you never see it",
}


def allowed_tools(role: Optional[str], scopes: Optional[Iterable[str]]) -> list:
    """The /ai operations this member may use now, in a stable order."""
    held = list(scopes) if scopes is not None else None
    names = []
    for name, need in TOOL_SCOPES.items():
        if need is None:
            names.append(name)
        elif need == "owner":
            if role == "owner":
                names.append(name)
        elif isinstance(need, tuple):
            if any(has_permission(role, scope, held) for scope in need):
                names.append(name)
        elif has_permission(role, need, held):
            names.append(name)
    return names


def build_agent_question(
    scrubbed_text: str,
    response_language: Optional[str] = None,
    role: Optional[str] = None,
    scopes: Optional[Iterable[str]] = None,
) -> str:
    """The user message for the agent flow: the scrubbed question and nothing else.

    No language line is added (Omar, Session 126): the model answers in the language of the
    question (the rule is in the website prompt). `response_language`, `role` and `scopes`
    stay in the signature for the callers; none of them is sent. The prompt lives in the
    flow's system message (MicroMind website) and the /ai routes refuse what the member may
    not read or prepare.
    """
    return scrubbed_text