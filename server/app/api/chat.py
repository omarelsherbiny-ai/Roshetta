# server/app/api/chat.py
from datetime import datetime, timezone
import time
import json
from typing import Any, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field
from fastapi import APIRouter, Depends, HTTPException
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
from server.app.services.security import create_ai_access_token
from server.app.api.actions import ActionProposalResponse
from agents.orchestrator import run_orchestration
from agents.state import AgentState

router = APIRouter(prefix="/api/chat", tags=["Chat"])


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
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(get_current_user),
):
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
    required_action_scope = intent if intent in {"log_sale", "log_expense", "log_restock"} else None
    if required_action_scope and (
        not has_permission(ctx["role"], required_action_scope, ctx.get("scopes"))
        or (required_action_scope in {"log_sale", "log_restock"} and not can_view_inventory)
    ):
        result["proposal"] = None
        result["answer_text"] = "صلاحيات حسابك لا تسمح بهذا الإجراء." if lang == "ar" else "Your account does not have permission for this action."
    elif intent == "query_stock" and not can_view_inventory:
        result["answer_text"] = "صلاحيات حسابك لا تسمح بعرض المخزون." if lang == "ar" else "Your account does not have permission to view inventory."
    elif intent == "query_finance" and not can_view_reports:
        result["answer_text"] = "صلاحيات حسابك لا تسمح بعرض الملخص المالي." if lang == "ar" else "Your account does not have permission to view financial summaries."

    # MicroMind is only needed for general chat. Keep structured operations and
    # pharmacy-data questions local, and do not call it for denied requests.
    agent_failed = False
    if result.get("intent") == "general_chat":
        from server.app.services.micromind import micromind_client
        response_language = "Arabic" if lang == "ar" else "English"
        # Only general chat leaves the system, and personal identifiers (phone
        # numbers, national IDs, emails) are removed from it first.
        question = f"Answer in {response_language}.\nUser question:\n{scrub_for_external(req.text)}"
        if settings.AI_TOOLS_ENABLED and (can_view_inventory or can_view_reports):
            # The flow may read this pharmacy's data through the /ai tools. It gets a
            # 5 minute read-only token made for this user and pharmacy, valid only on
            # /ai (the main API refuses it), and the user's own scopes still apply.
            ai_token = create_ai_access_token(ctx["user_id"], pharmacy_id)
            # The fixed prompt and this member's tool list go first (ai_prompt.py).
            agent_question = build_agent_question(
                scrub_for_external(req.text), response_language, ctx["role"], ctx.get("scopes"),
            )
            micromind_res = await micromind_client.query_agent(agent_question, ai_token)
            # Only a configured flow that failed deserves the note; with MicroMind off
            # (the default) the local answer is the expected one.
            agent_failed = micromind_res is None and settings.USE_MICROMIND
        else:
            micromind_res = await micromind_client.query({"question": question})
        if isinstance(micromind_res, dict):
            remote_text = micromind_res.get("text") or micromind_res.get("answer") or micromind_res.get("output")
            if remote_text:
                result["answer_text"] = remote_text
        if agent_failed:
            # The agent flow did not answer (off, timeout, error): keep the local answer
            # and say so, so a plain reply is not mistaken for a data-backed one.
            note = (
                "\n\n(تعذّر الوصول إلى أدوات بيانات الصيدلية الآن، وهذا رد عام. حاول مرة أخرى بعد قليل.)"
                if lang == "ar"
                else "\n\n(The pharmacy data tools could not be reached right now, so this is a general reply. Try again in a moment.)"
            )
            result["answer_text"] = (result.get("answer_text") or "") + note

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