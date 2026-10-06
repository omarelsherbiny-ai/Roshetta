# server/app/api/chat.py
from datetime import datetime, timezone
import logging
import time
import json
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.config import settings
from server.app.db.session import get_db
from server.app.db.models import InventoryBatch, InventoryItem, PendingAction, has_permission
from server.app.services.financials import daily_financial_summary
from server.app.services.rbac import get_current_user
from server.app.services.clock import utc_now_naive
from server.app.services.rate_limit import chat_limiter
from server.app.services.scrub import scrub_for_external
from server.app.services.ai_prompt import build_agent_question
from server.app.services.ai_session import agent_session_id
from server.app.services.security import create_ai_access_token
from server.app.services.agent_routing import AGENT_CARD_SCOPES, should_use_agent
from server.app.services.inventory_prefetch import build_inventory_question, prefetch_mode
from server.app.api.actions import ActionProposalResponse
from agents.orchestrator import run_orchestration
from agents.state import AgentState

router = APIRouter(prefix="/api/chat", tags=["Chat"])
logger = logging.getLogger(__name__)


def _agent_failure_reason(client: Any) -> str:
    """The short failure kind the MicroMind client recorded for its last call (for example
    'empty_answer' or 'http_status 401'). It never holds a URL, a token or message text."""
    last = getattr(client, "last_error", None)
    if isinstance(last, dict):
        text = f"{last.get('kind') or ''} {last.get('detail') or ''}".strip()
        return text[:80]
    return ""


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    text:       str = Field(min_length=1, max_length=4000)
    context_id: Optional[str] = Field(default="default", max_length=128)
    language:   Literal["ar", "en"] = "ar"


class ChatResponse(BaseModel):
    id: str
    sender: Literal["assistant"]
    text: str
    timestamp: str
    proposal: Optional[ActionProposalResponse] = None
    prescription: Optional[dict[str, Any]] = None
    grounded_data: dict[str, Optional[str]]


@router.post("", response_model=ChatResponse)
async def handle_chat(
    req: ChatRequest,
    response: Response,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(get_current_user),
):
    # A chat answer is for this request only: no browser, proxy or tunnel may keep it.
    response.headers["Cache-Control"] = "no-store"
    pharmacy_id = ctx["pharmacy_id"]
    lang = req.language

    # Each message loads the whole inventory and may call an external service.
    retry_after = chat_limiter.check((pharmacy_id, ctx["user_id"]))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail=(
                f"رسائل كثيرة في وقت قصير. حاول مرة أخرى بعد {retry_after} ثانية."
                if lang == "ar"
                else f"Too many messages in a short time. Try again in {retry_after} seconds."
            ),
            headers={"Retry-After": str(retry_after)},
        )

    can_view_inventory = has_permission(ctx["role"], "view_inventory", ctx.get("scopes"))
    can_view_reports = has_permission(ctx["role"], "view_reports", ctx.get("scopes"))

    # Do not pass inventory data to the assistant unless this membership may view it.
    inventory_data = []
    if can_view_inventory:
        inv_res = await db.execute(
            select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id)
        )
        items = inv_res.scalars().all()
        item_ids = [item.id for item in items]
        batches_by_item: dict[int, list[dict]] = {item_id: [] for item_id in item_ids}
        if item_ids:
            batch_res = await db.execute(
                select(InventoryBatch)
                .where(
                    InventoryBatch.pharmacy_id == pharmacy_id,
                    InventoryBatch.item_id.in_(item_ids),
                    InventoryBatch.quantity > 0,
                )
                .order_by(InventoryBatch.created_at.asc(), InventoryBatch.id.asc())
            )
            for batch in batch_res.scalars().all():
                batches_by_item[batch.item_id].append({
                    "quantity": batch.quantity,
                    "unit_sell_price": batch.unit_sell_price,
                })
        inventory_data = [
            {
                "id": it.id,
                "name_ar": it.name_ar,
                "name_en": it.name_en,
                "stock_qty": it.stock_qty,
                "min_threshold": it.min_threshold,
                "unit_sell_price": it.unit_sell_price,
                "unit_buy_price": it.unit_buy_price,
                "price_batches": batches_by_item[it.id],
                "category": it.category
            }
            for it in items
        ]

    # 2. Fetch today's local-date ledger summary scoped strictly to this pharmacy
    financial_data = None
    if can_view_reports:
        financial_data = await daily_financial_summary(
            db,
            pharmacy_id,
            user_id=ctx["user_id"] if ctx["role"] == "cashier" else None,
        )

    # Run local intent parsing and scoped pharmacy-data agents first.
    state: AgentState = {
        "user_query": req.text,
        "context_id": req.context_id or "default",
        "inventory_data": inventory_data,
        "financial_data": financial_data,
        "language": lang
    }

    result = await run_orchestration(state)

    intent = result.get("intent")
    # The scope a write needs: a sale, expense or restock needs the scope of its own
    # name; adding a product needs manage_inventory.
    required_action_scope = None
    if intent in {"log_sale", "log_expense", "log_restock"}:
        required_action_scope = intent
    elif intent == "create_product":
        required_action_scope = "manage_inventory"
    write_denied = bool(required_action_scope) and (
        not has_permission(ctx["role"], required_action_scope, ctx.get("scopes"))
        or (required_action_scope in {"log_sale", "log_restock"} and not can_view_inventory)
    )
    if write_denied:
        result["proposal"] = None
        result["answer_text"] = "صلاحيات حسابك لا تسمح بهذا الإجراء." if lang == "ar" else "Your account does not have permission for this action."
    elif intent == "query_stock" and not can_view_inventory:
        result["answer_text"] = "صلاحيات حسابك لا تسمح بعرض المخزون." if lang == "ar" else "Your account does not have permission to view inventory."
    elif intent == "query_finance" and not can_view_reports:
        result["answer_text"] = "صلاحيات حسابك لا تسمح بعرض الملخص المالي." if lang == "ar" else "Your account does not have permission to view financial summaries."

    # Agent first (Session 123): when the data tools are on (AI_TOOLS_ENABLED) MicroMind
    # answers every message the local pipeline does not turn into its own confirmation
    # card, for every member (the /ai routes enforce each member's scopes, and every
    # member holds at least the get_my_activity tool). Local write cards (sale, expense,
    # restock, new product), denied requests and a cashier's finance question stay local
    # (agent_routing.py). Session 126 (Omar): when the agent does NOT answer, the local
    # answer is no longer shown; the person gets one short error line with the reason.
    is_cashier = ctx["role"] == "cashier"
    use_agent = should_use_agent(
        intent,
        tools_enabled=settings.AI_TOOLS_ENABLED,
        can_view_inventory=can_view_inventory,
        can_view_reports=can_view_reports,
        is_cashier=is_cashier,
        # Session 126: when the local parser cannot build the new-product card (an Arabic
        # sentence it does not know), the model reads the sentence and calls propose_product.
        local_card_missing=(
            intent == "create_product" and not write_denied and not result.get("proposal")
        ),
        write_denied=write_denied,
    )
    # Restock (Session 126): the model prepares the card with propose_restock, so the local
    # card (and its fixed texts) is dropped; the card is read back from the database below.
    # A new product (Session 126) is the same: the model calls propose_product. The local card
    # is dropped only when MicroMind is on, so with it off the local card still works.
    if use_agent and intent in {"log_restock", "create_product"} and settings.USE_MICROMIND:
        result["proposal"] = None
    # Speed (Session 125): a plain inventory read (list, low stock, stock summary) is answered
    # from the data this server already loaded, in ONE short model turn with no tool call.
    # It sends what the /ai tools return (no buy prices, no ids), so nothing new leaves the
    # system. Any other question keeps the tools (inventory_prefetch.py). Off by default.
    prefetch_question = None
    if use_agent and settings.AI_PREFETCH_READS and intent == "query_stock" and can_view_inventory:
        prefetch_kind = prefetch_mode(req.text)
        if prefetch_kind is not None:
            prefetch_question = build_inventory_question(
                scrub_for_external(req.text),
                "Arabic" if lang == "ar" else "English",
                inventory_data,
                lang,
                prefetch_kind,
            )
            if prefetch_question is not None:
                use_agent = False
    agent_failed = False
    agent_called = False
    agent_started_at = utc_now_naive()  # cards the agent prepares from here on belong to this message
    if intent == "general_chat" or use_agent or prefetch_question is not None:
        from server.app.services.micromind import micromind_client
        response_language = "Arabic" if lang == "ar" else "English"
        # Only these messages leave the system, and personal identifiers (phone
        # numbers, national IDs, emails) are removed from them first.
        question = f"Answer in {response_language}.\nUser question:\n{scrub_for_external(req.text)}"
        if use_agent:
            agent_called = True
            # The flow may read this pharmacy's data through the /ai tools. It gets a
            # 5 minute read-only token made for this user and pharmacy, valid only on
            # /ai (the main API refuses it), and the user's own scopes still apply.
            ai_token = create_ai_access_token(ctx["user_id"], pharmacy_id)
            # The user message for the flow: the scrubbed question only (ai_prompt.py).
            agent_question = build_agent_question(
                scrub_for_external(req.text), response_language, ctx["role"], ctx.get("scopes"),
            )
            # Chat memory: a server-made session id (None for the placeholder context).
            session_id = agent_session_id(
                pharmacy_id, ctx["user_id"], ctx["role"], ctx.get("scopes"), req.context_id,
            )
            micromind_res = await micromind_client.query_agent(
                agent_question, ai_token, session_id=session_id,
            )
            # Only a configured flow that failed deserves an error; with MicroMind off
            # (the default) the local answer is the expected one.
            agent_failed = micromind_res is None and settings.USE_MICROMIND
        elif prefetch_question is not None:
            micromind_res = await micromind_client.query(
                {"question": prefetch_question}, timeout=settings.AI_AGENT_TIMEOUT_SECONDS,
            )
            prefetch_text = (
                micromind_res.get("text") or micromind_res.get("answer") or micromind_res.get("output")
                if isinstance(micromind_res, dict) else None
            )
            agent_failed = settings.USE_MICROMIND and not (isinstance(prefetch_text, str) and prefetch_text.strip())
        else:
            micromind_res = await micromind_client.query({"question": question})
        if isinstance(micromind_res, dict):
            remote_text = micromind_res.get("text") or micromind_res.get("answer") or micromind_res.get("output")
            if isinstance(remote_text, str) and remote_text.strip():
                result["answer_text"] = remote_text
        if agent_failed:
            # The flow did not answer (timeout, error, empty text). No local answer is shown:
            # one short line says so and names the failure kind, so the cause can be found.
            reason = _agent_failure_reason(micromind_client)
            logger.warning("Assistant did not answer (intent=%s, reason=%s)", intent, reason or "unknown")
            suffix = f" ({reason})" if reason else ""
            result["answer_text"] = (
                f"لم يرد المساعد الآن. حاول مرة أخرى بعد قليل.{suffix}"
                if lang == "ar"
                else f"The assistant did not answer. Try again in a moment.{suffix}"
            )

    # A confirmation card (sale, expense, restock or new product) is always prepared
    # locally, because only a person confirms a write; MicroMind writes the sentence
    # around it. What leaves the system: the kind of card, and for a new product only the
    # typed name and the sell price. Never buy prices, stock, amounts or line items.
    if intent in {"log_sale", "log_expense", "log_restock", "create_product"} and result.get("proposal") and settings.USE_MICROMIND:
        from server.app.services.micromind import micromind_client
        card_language = "Arabic" if lang == "ar" else "English"
        if intent == "create_product":
            card_product = result["proposal"].get("product") or {}
            card_what = (
                "a confirmation card to add a new product named "
                f"'{scrub_for_external(str(card_product.get('name_en') or ''))}' with sell price "
                f"{card_product.get('unit_sell_price')} EGP"
            )
        else:
            card_what = {
                "log_sale": "a confirmation card for a sale",
                "log_expense": "a confirmation card for an expense",
                "log_restock": "a confirmation card for a restock",
            }[intent]
        card_question = (
            f"Answer in {card_language}.\n"
            f"The app already prepared {card_what}. In one or two short sentences tell the user "
            "to review the card and press confirm or cancel. Never mention editing, and never "
            "say anything was added, sold or saved."
        )
        card_res = await micromind_client.query({"question": card_question})
        if isinstance(card_res, dict):
            card_text = card_res.get("text") or card_res.get("answer") or card_res.get("output")
            if isinstance(card_text, str) and card_text.strip():
                result["answer_text"] = card_text

    proposal = result.get("proposal")
    if proposal and proposal.get("id") and proposal.get("status") == "pending_confirmation":
        db.add(PendingAction(
            id=proposal["id"],
            pharmacy_id=pharmacy_id,
            created_by=ctx["user_id"],
            action_type=proposal.get("action_type", ""),
            status="pending_confirmation",
            payload_json=json.dumps(proposal, ensure_ascii=False),
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        ))
        await db.commit()

    # A card the agent prepared with a propose_* tool during this message is read back
    # from the database (never from the model's text) and shown with the reply. Only the
    # card types in AGENT_CARD_SCOPES whose scope this member holds are looked up.
    if agent_called and result.get("proposal") is None:
        card_types = [
            card_type
            for card_type, card_scope in AGENT_CARD_SCOPES.items()
            if has_permission(ctx["role"], card_scope, ctx.get("scopes"))
        ]
        prepared_row = None
        if card_types:
            prepared = await db.execute(
                select(PendingAction)
                .where(
                    PendingAction.pharmacy_id == pharmacy_id,
                    PendingAction.created_by == ctx["user_id"],
                    PendingAction.action_type.in_(card_types),
                    PendingAction.status == "pending_confirmation",
                    PendingAction.created_at >= agent_started_at,
                )
                .order_by(PendingAction.created_at.desc())
                .limit(1)
            )
            prepared_row = prepared.scalars().first()
        if prepared_row is not None:
            try:
                prepared_card = json.loads(prepared_row.payload_json)
                prepared_card.update({
                    "id": prepared_row.id,
                    "action_type": prepared_row.action_type,
                    "status": prepared_row.status,
                    "created_at": prepared_row.created_at.isoformat() + "Z" if prepared_row.created_at else None,
                })
                result["proposal"] = ActionProposalResponse.model_validate(prepared_card).model_dump()
            except (TypeError, ValueError) as exc:
                # Never silent (Session 126): a prepared card that cannot be shown is logged
                # with its type, so "the card did not appear" can be told from "no card made".
                logger.warning(
                    "Prepared card not shown (type=%s, error=%s)", prepared_row.action_type, type(exc).__name__,
                )
        else:
            logger.info("Agent answered with no new card (card types checked: %s)", ",".join(card_types) or "none")
    # Construct response message
    chat_response = {
        "id": f"asst-{time.time_ns() // 1_000_000}",
        "sender": "assistant",
        "text": result.get("answer_text", "تم استلام الطلب." if lang == "ar" else "Request received."),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "proposal": result.get("proposal"),
        "prescription": result.get("prescription"),
        "grounded_data": {
            "intent": result.get("intent"),
        }
    }

    return chat_response