# scripts/patch_ai_propose.py
"""One-time patch for Session 119 (task 9 step 5). Run once from the project root:

    python scripts/patch_ai_propose.py

It makes three small, exact insertions and refuses to touch a file whose text differs from
what it expects (it prints which anchor is missing and writes nothing for that file).
Running it twice is safe: a file that already carries the change is skipped.

  server/app/api/ai.py          mounts the propose_product router under the /ai rate limit
  server/app/api/chat.py        (a) MicroMind writes the sentence around a local add-product card
                                (b) attaches a card the agent prepared during this message
  server/app/services/ai_prompt.py  tool scope, tool guide and the Writing rule
  tests/test_ai_agent_tools.py  the two tests that counted 14 tools and one POST route
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CHAT_AGENT_START_OLD = '    agent_failed = False\n    if intent == "general_chat" or agent_read:\n'
CHAT_AGENT_START_NEW = (
    '    agent_failed = False\n'
    '    agent_started_at = utc_now_naive()  # cards the agent prepares from here on belong to this message\n'
    '    if intent == "general_chat" or agent_read:\n'
)

CHAT_SENTENCE_OLD = (
    '    proposal = result.get("proposal")\n'
    '    if proposal and proposal.get("id") and proposal.get("status") == "pending_confirmation":\n'
)
CHAT_SENTENCE_NEW = (
    '    # An add-product card is prepared locally; MicroMind writes the sentence around it.\n'
    '    # Only the typed name and the sell price leave the system (no buy price, no stock).\n'
    '    if intent == "create_product" and result.get("proposal") and settings.USE_MICROMIND:\n'
    '        from server.app.services.micromind import micromind_client\n'
    '        card_product = result["proposal"].get("product") or {}\n'
    '        card_language = "Arabic" if lang == "ar" else "English"\n'
    '        card_question = (\n'
    '            f"Answer in {card_language}.\\n"\n'
    '            "The app already prepared a confirmation card to add a new product named "\n'
    '            f"\'{scrub_for_external(str(card_product.get(\'name_en\') or \'\'))}\' with sell price "\n'
    '            f"{card_product.get(\'unit_sell_price\')} EGP. In one or two short sentences tell the user "\n'
    '            "to review the card, edit anything and press confirm. Never say the product was added or saved."\n'
    '        )\n'
    '        card_res = await micromind_client.query({"question": card_question})\n'
    '        if isinstance(card_res, dict):\n'
    '            card_text = card_res.get("text") or card_res.get("answer") or card_res.get("output")\n'
    '            if isinstance(card_text, str) and card_text.strip():\n'
    '                result["answer_text"] = card_text\n'
    '\n'
) + CHAT_SENTENCE_OLD

CHAT_ATTACH_OLD = '    # Construct response message\n    chat_response = {\n'
CHAT_ATTACH_NEW = (
    '    # A card the agent prepared with the propose_product tool during this message is read\n'
    '    # back from the database (never from the model\'s text) and shown with the reply.\n'
    '    if (\n'
    '        settings.AI_TOOLS_ENABLED\n'
    '        and result.get("proposal") is None\n'
    '        and (intent == "general_chat" or agent_read)\n'
    '        and has_permission(ctx["role"], "manage_inventory", ctx.get("scopes"))\n'
    '    ):\n'
    '        prepared = await db.execute(\n'
    '            select(PendingAction)\n'
    '            .where(\n'
    '                PendingAction.pharmacy_id == pharmacy_id,\n'
    '                PendingAction.created_by == ctx["user_id"],\n'
    '                PendingAction.action_type == "create_product",\n'
    '                PendingAction.status == "pending_confirmation",\n'
    '                PendingAction.created_at >= agent_started_at,\n'
    '            )\n'
    '            .order_by(PendingAction.created_at.desc())\n'
    '            .limit(1)\n'
    '        )\n'
    '        prepared_row = prepared.scalars().first()\n'
    '        if prepared_row is not None:\n'
    '            try:\n'
    '                prepared_card = json.loads(prepared_row.payload_json)\n'
    '                prepared_card.update({\n'
    '                    "id": prepared_row.id,\n'
    '                    "action_type": "create_product",\n'
    '                    "status": prepared_row.status,\n'
    '                    "created_at": prepared_row.created_at.isoformat() + "Z" if prepared_row.created_at else None,\n'
    '                })\n'
    '                result["proposal"] = ActionProposalResponse.model_validate(prepared_card).model_dump()\n'
    '            except (TypeError, ValueError):\n'
    '                pass\n'
    '\n'
) + CHAT_ATTACH_OLD

PROMPT_SCOPE_OLD = '    "list_roles": "owner",\n}\n'
PROMPT_SCOPE_NEW = '    "list_roles": "owner",\n    "propose_product": "manage_inventory",\n}\n'
PROMPT_GUIDE_OLD = '    "list_roles": "custom roles and their scopes (owner only)",\n}\n'
PROMPT_GUIDE_NEW = (
    '    "list_roles": "custom roles and their scopes (owner only)",\n'
    '    "propose_product": "prepare a card to add a NEW product (needs name and sell price); the user reviews and confirms it in the app",\n'
    '}\n'
)
PROMPT_WRITING_OLD = (
    'Writing: you never change data. A sale, an expense, a restock or a new product is only proposed: '
    'the user writes it in the chat (for example "sell 2 Panadol" or "add product Panadol buy 10 sell 15") '
    'and the app shows a card that the user confirms. Never say a record was saved.'
)
PROMPT_WRITING_NEW = (
    'Writing: you never change data. A sale, an expense or a restock is only proposed: the user writes it in the chat '
    '(for example "sell 2 Panadol") and the app shows a card that the user confirms. To add a NEW product, call '
    'propose_product when it is in your list (the name and the sell price are required; ask the user for them if missing; '
    'pass buy price, quantity, minimum level and category only if the user gave them). It only prepares a card that the '
    'user reviews, edits and confirms in the app, so tell the user a card is waiting for review. Never say a record was saved.'
)

AI_IMPORT_OLD = 'from server.app.api.me import get_my_activity\n'
AI_IMPORT_NEW = AI_IMPORT_OLD + 'from server.app.api.ai_propose import propose_router\n'
AI_INCLUDE_OLD = '    ai_app.include_router(router)\n'
AI_INCLUDE_NEW = AI_INCLUDE_OLD + '    ai_app.include_router(propose_router, dependencies=[Depends(ai_rate_limit)])\n'

TEST_CALL_OLD = '            "list_roles": ("get", "/ai/roles", None),\n        }\n'
TEST_CALL_NEW = (
    '            "list_roles": ("get", "/ai/roles", None),\n'
    '            "propose_product": ("post", "/ai/propose-product", {"name": "Scope Table Cetal", "unit_sell_price": 15}),\n'
    '        }\n'
)
TEST_POSTS_OLD = '        self.assertEqual(posts, [("post", "/match")])\n'
TEST_POSTS_NEW = '        self.assertEqual(sorted(posts), [("post", "/match"), ("post", "/propose-product")])\n'

PLAN = {
    "server/app/api/ai.py": [
        ("propose_router import", AI_IMPORT_OLD, AI_IMPORT_NEW, "propose_router"),
        ("propose_router mount", AI_INCLUDE_OLD, AI_INCLUDE_NEW, "include_router(propose_router"),
    ],
    "server/app/api/chat.py": [
        ("agent start time", CHAT_AGENT_START_OLD, CHAT_AGENT_START_NEW, "agent_started_at"),
        ("MicroMind sentence for the local card", CHAT_SENTENCE_OLD, CHAT_SENTENCE_NEW, "card_product = result"),
        ("attach the agent's card", CHAT_ATTACH_OLD, CHAT_ATTACH_NEW, "prepared_row"),
    ],
    "tests/test_ai_agent_tools.py": [
        ("propose_product in the scope table", TEST_CALL_OLD, TEST_CALL_NEW, '"propose_product": ("post"'),
        ("two POST routes in the spec", TEST_POSTS_OLD, TEST_POSTS_NEW, '("post", "/propose-product")'),
    ],
    "server/app/services/ai_prompt.py": [
        ("tool scope", PROMPT_SCOPE_OLD, PROMPT_SCOPE_NEW, '"propose_product": "manage_inventory"'),
        ("tool guide", PROMPT_GUIDE_OLD, PROMPT_GUIDE_NEW, '"propose_product": "prepare a card'),
        ("Writing rule", PROMPT_WRITING_OLD, PROMPT_WRITING_NEW, "call propose_product"),
    ],
}


def patch_file(relative: str, steps) -> bool:
    path = ROOT / relative
    if not path.exists():
        print(f"MISSING  {relative}")
        return False
    raw = path.read_bytes().decode("utf-8")
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")
    changed = False
    for label, old, new, marker in steps:
        if marker in text:
            print(f"skip     {relative}: {label} (already applied)")
            continue
        if text.count(old) != 1:
            print(f"STOP     {relative}: anchor for '{label}' found {text.count(old)} times (expected 1); nothing written for this file")
            return False
        text = text.replace(old, new, 1)
        changed = True
        print(f"patched  {relative}: {label}")
    if changed:
        out = text.replace("\n", "\r\n") if crlf else text
        path.write_bytes(out.encode("utf-8"))
    return True


def main() -> int:
    ok = True
    for relative, steps in PLAN.items():
        ok = patch_file(relative, steps) and ok
    print("Done." if ok else "Some files were not patched; send the STOP lines to Claude.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())