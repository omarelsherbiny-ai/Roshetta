# server/app/services/ai_prompt.py
"""The fixed system prompt for the MicroMind agent path, kept in code (Session 109, W8 c).

`build_agent_question` is the only place the text sent to the agent flow is assembled:
the fixed prompt, the tools this member may use right now, the language, and the
already scrubbed user text. Nothing here holds data about the pharmacy or the person.
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
    "list_low_stock": "view_inventory",
    "list_categories": "view_inventory",
    "get_inventory_summary": "view_inventory",
    "list_ledger_entries": "view_reports",
    "get_sales_summary": "view_reports",
    "list_supplier_payables": "view_reports",
    "get_payables_summary": "view_reports",
    "list_records_timeline": ("view_reports", "view_inventory", "view_audit"),
    "get_my_activity": None,
    "list_roles": "owner",
}

TOOL_GUIDE: dict = {
    "search_inventory": "find products by name, active ingredient, barcode or category",
    "match_product": "find one product by a spoken or typed name",
    "get_item_batches": "stock lots of one product with expiry dates (needs the product id from a search)",
    "get_item_price_history": "selling-price changes of one product (needs the product id)",
    "list_low_stock": "products at or below their minimum level",
    "list_categories": "categories and how many products each has",
    "get_inventory_summary": "total products, units and selling value in stock",
    "list_ledger_entries": "recent sales, expenses and restocks",
    "get_sales_summary": "sales and expense totals for a day or a range",
    "list_supplier_payables": "credit restocks, what was paid and what is still owed",
    "get_payables_summary": "total still owed to suppliers",
    "list_records_timeline": "what happened lately: records, product and category changes, staff and settings changes",
    "get_my_activity": "the signed-in person's own totals for a period",
    "list_roles": "custom roles and their scopes (owner only)",
}

SYSTEM_PROMPT = """You are the assistant inside the Roshetta pharmacy app. You help one signed-in member of one pharmacy.

Language: Arabic is the default. Answer in the language of the user's question; if the app says "Answer in English", use English. Keep answers short and practical.
Money and time: every amount is in Egyptian pounds (EGP). Days and hours are Cairo time. Say "today" only for the Cairo day.
Facts: never invent numbers, products, prices, stock, people or dates. If the answer is about this pharmacy's data, call a tool first and answer only from what it returned. If a tool returned nothing, say so.
Tools: use only the tools listed under "Tools you may use now". Use at most three calls per message and prefer the narrowest call (a product name, a day, a limit). Dates are YYYY-MM-DD. Product ids come only from a search result; never guess one. Numbers may be written with Arabic-Indic digits; pass them as they are.
Missing permission: if the question needs a tool that is not in your list, say in one sentence that this account's role does not allow it and who can (the pharmacy owner). Do not try another tool to work around it.
Tool errors: if a tool answers with an error, tell the user in plain words what happened and what to do next (try again in a minute, narrow the question, or open the matching screen in the app). Never show raw error text.
Writing: you never change data. A sale, an expense or a restock is only proposed: the user writes it in the chat (for example "sell 2 Panadol") and the app shows a proposal that the user confirms. Never say a record was saved.
Out of reach: you cannot list members, read schedules or pay, change prices or products, pay suppliers, or send invitations. Say that plainly and point to the matching screen.
Privacy: never repeat phone numbers, ids, PINs or tokens, and never ask for them."""


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
    response_language: str,
    role: Optional[str],
    scopes: Optional[Iterable[str]],
) -> str:
    """Fixed prompt + this member's tool list + language + the scrubbed question."""
    lines = [f"- {name}: {TOOL_GUIDE[name]}" for name in allowed_tools(role, scopes)]
    tools = "\n".join(lines) if lines else "- (none)"
    return (
        f"{SYSTEM_PROMPT}\n\nTools you may use now:\n{tools}\n\n"
        f"Answer in {response_language}.\nUser question:\n{scrubbed_text}"
    )