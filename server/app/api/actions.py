# server/app/api/actions.py
import json
import math
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.config import settings
from server.app.db.models import (
    AuditLog,
    InventoryBatch,
    InventoryItem,
    LedgerEntry,
    LedgerEntryItem,
    PendingAction,
    User,
    has_permission,
)
from server.app.db.session import get_db
from server.app.services.rbac import get_current_user
from server.app.services.clock import utc_now_naive
from server.app.services.expiry import sync_item_expiry
from server.app.services.proposals import proposal_cutoff, proposal_is_expired
from server.app.services.stock import overdrawn_inventory_quantities

router = APIRouter(prefix="/api/actions", tags=["Actions"])
ALLOWED_ACTION_TYPES = {"log_sale", "log_expense", "log_restock"}
ALLOWED_PAYMENT_METHODS = {"cash", "card", "credit"}


class ProposedItemModel(BaseModel):
    item_name: str = Field(min_length=1, max_length=150)
    quantity: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    unit_price: float = Field(ge=0, le=100_000_000, allow_inf_nan=False)
    subtotal: Optional[float] = Field(default=None, ge=0, allow_inf_nan=False)
    matched_inventory_id: Optional[int] = None


class ActionConfirmRequest(BaseModel):
    edited_items: Optional[List[ProposedItemModel]] = Field(default=None, max_length=100)
    payment_method: Optional[str] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class InventorySuggestionResponse(BaseModel):
    id: int
    name_ar: str
    stock_qty: float
    unit_sell_price: float


class ProposedItemResponse(BaseModel):
    id: Optional[int] = None
    item_name: str
    quantity: float
    unit_price: float
    subtotal: float
    matched_inventory_id: Optional[int] = None
    stock_available: Optional[float] = None
    category: Optional[str] = None
    not_in_inventory: Optional[bool] = None
    suggestions: List[InventorySuggestionResponse] = Field(default_factory=list)


class ActionProposalResponse(BaseModel):
    id: str
    action_type: Literal["log_sale", "log_expense", "log_restock"]
    title: str
    summary_ar: str
    summary_en: str
    items: List[ProposedItemResponse]
    total_amount: float
    payment_method: str
    confidence: float = 1.0
    status: Literal["pending_confirmation", "confirmed", "cancelled", "rejected"]
    created_at: Optional[str]
    raw_text: Optional[str] = None
    source_image_url: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)


class PendingActionsResponse(BaseModel):
    actions: List[ActionProposalResponse]
    unavailable_count: int


class ConfirmedActionResponse(BaseModel):
    success: bool
    message: str
    proposal: ActionProposalResponse


class CancelledProposalResponse(BaseModel):
    id: str
    status: Literal["cancelled"]


class CancelledActionResponse(BaseModel):
    success: bool
    message: str
    proposal: CancelledProposalResponse


def _load_proposal(pending: PendingAction) -> dict:
    try:
        proposal = json.loads(pending.payload_json)
    except (TypeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=409, detail="The saved proposal is unreadable.") from exc
    if not isinstance(proposal, dict) or not isinstance(proposal.get("items"), list):
        raise HTTPException(status_code=409, detail="The saved proposal is incomplete.")
    return proposal


@router.get("/pending", response_model=PendingActionsResponse)
async def list_pending_actions(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    """Recover this pharmacy's still-actionable proposals after navigation or reload."""
    result = await db.execute(
        select(PendingAction)
        .where(
            PendingAction.pharmacy_id == ctx["pharmacy_id"],
            PendingAction.status == "pending_confirmation",
            # Expired proposals keep their old prices: they are not offered again.
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
        .order_by(PendingAction.created_at.desc())
        .limit(100)
    )
    actions = []
    unavailable_count = 0
    for pending in result.scalars().all():
        if pending.action_type not in ALLOWED_ACTION_TYPES or not has_permission(ctx["role"], pending.action_type, ctx.get("scopes")):
            continue
        try:
            proposal = _load_proposal(pending)
            items = [ProposedItemModel.model_validate(item).model_dump() for item in proposal["items"]]
            for item in items:
                item["subtotal"] = item["quantity"] * item["unit_price"]
            payment_method = proposal.get("payment_method", "cash")
            if payment_method not in ALLOWED_PAYMENT_METHODS:
                raise ValueError("Unsupported saved payment method")
            total_amount = sum(item["quantity"] * item["unit_price"] for item in items)
            if not math.isfinite(total_amount) or total_amount <= 0:
                raise ValueError("Invalid saved action total")
        except (HTTPException, TypeError, ValueError):
            unavailable_count += 1
            continue
        action = {
            **proposal,
            "items": items,
            "total_amount": total_amount,
            "payment_method": payment_method,
            "id": pending.id,
            "action_type": pending.action_type,
            "status": pending.status,
            "created_at": pending.created_at.isoformat() + "Z" if pending.created_at else None,
        }
        try:
            actions.append(ActionProposalResponse.model_validate(action).model_dump())
        except ValidationError:
            unavailable_count += 1
    return {"actions": actions, "unavailable_count": unavailable_count}


@router.post("/{action_id}/confirm", response_model=ConfirmedActionResponse)
async def confirm_action(
    action_id: str,
    req: ActionConfirmRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    pending_result = await db.execute(
        select(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.pharmacy_id == ctx["pharmacy_id"],
        )
        .with_for_update()
    )
    pending = pending_result.scalars().first()
    if not pending:
        raise HTTPException(status_code=404, detail="Action proposal not found.")
    if pending.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail=f"Action is already {pending.status}.")
    if proposal_is_expired(pending.created_at, utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS):
        # Nothing has changed yet. Cancel stays allowed so the person can clear it.
        raise HTTPException(status_code=409, detail="This proposal has expired. Ask the assistant again.")

    claimed = await db.execute(
        update(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.pharmacy_id == ctx["pharmacy_id"],
            PendingAction.status == "pending_confirmation",
        )
        .values(status="processing", updated_at=utc_now_naive())
    )
    if claimed.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This action is already being processed.")
    pending.status = "processing"

    entry_type = pending.action_type
    if entry_type not in ALLOWED_ACTION_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported action type.")
    if not has_permission(ctx["role"], entry_type, ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="Your role cannot confirm this action.")

    proposal = _load_proposal(pending)
    original_items = proposal["items"]
    raw_items = req.edited_items if req.edited_items is not None else original_items
    try:
        items = [ProposedItemModel.model_validate(item) for item in raw_items]
    except Exception as exc:
        raise HTTPException(status_code=422, detail="The proposal contains invalid line items.") from exc
    if not items or len(items) != len(original_items):
        raise HTTPException(status_code=422, detail="The proposal line items cannot be added or removed during confirmation.")

    payment_method = req.payment_method or proposal.get("payment_method") or "cash"
    if payment_method not in ALLOWED_PAYMENT_METHODS:
        raise HTTPException(status_code=422, detail="Unsupported payment method.")

    resolved = []
    total_amount = 0.0
    for index, item in enumerate(items):
        original = original_items[index]
        original_id = original.get("matched_inventory_id")
        if item.item_name.strip() != str(original.get("item_name", "")).strip():
            raise HTTPException(status_code=422, detail="Product names cannot be changed during confirmation.")
        if item.matched_inventory_id != original_id:
            raise HTTPException(status_code=422, detail="Inventory matches cannot be changed during confirmation.")

        inventory_item = None
        if entry_type in {"log_sale", "log_restock"}:
            if item.matched_inventory_id is None:
                raise HTTPException(status_code=422, detail="Match each product to pharmacy inventory before confirming.")
            inventory_result = await db.execute(
                select(InventoryItem)
                .where(
                    InventoryItem.id == item.matched_inventory_id,
                    InventoryItem.pharmacy_id == ctx["pharmacy_id"],
                )
                .with_for_update()
            )
            inventory_item = inventory_result.scalars().first()
            if not inventory_item:
                raise HTTPException(status_code=422, detail="A proposed product no longer exists in this pharmacy's inventory.")
            if entry_type == "log_sale" and item.quantity > inventory_item.stock_qty:
                raise HTTPException(status_code=409, detail=f"Insufficient stock for {inventory_item.name_ar}.")

        subtotal = item.quantity * item.unit_price
        total_amount += subtotal
        resolved.append({
            "request_item": item,
            "inventory_item": inventory_item,
            "name": inventory_item.name_ar if inventory_item else item.item_name.strip(),
            "subtotal": subtotal,
        })

    if entry_type == "log_sale":
        available_by_inventory: dict[int, float] = {}
        quantity_lines = []
        item_names: dict[int, str] = {}
        for item_data in resolved:
            inventory_item = item_data["inventory_item"]
            inventory_id = inventory_item.id
            quantity_lines.append((inventory_id, item_data["request_item"].quantity))
            available_by_inventory[inventory_id] = inventory_item.stock_qty
            item_names[inventory_id] = item_data["name"]
        for inventory_id in overdrawn_inventory_quantities(quantity_lines, available_by_inventory):
            item_name = item_names[inventory_id]
            requested_quantity = sum(
                quantity for line_id, quantity in quantity_lines if line_id == inventory_id
            )
            available_quantity = available_by_inventory[inventory_id]
            if requested_quantity > available_quantity:
                raise HTTPException(
                    status_code=409,
                    detail=f"Insufficient stock for {item_name}.",
                )

    if total_amount <= 0:
        raise HTTPException(status_code=422, detail="The action total must be greater than zero.")

    user_result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = user_result.scalars().first()
    now = utc_now_naive()
    entry = LedgerEntry(
        id=action_id,
        pharmacy_id=ctx["pharmacy_id"],
        entry_type=entry_type,
        total_amount=total_amount,
        payment_method=payment_method,
        notes=req.notes or proposal.get("notes"),
        created_by=pending.created_by,
        confirmed_by=ctx["user_id"],
        confirmed_at=now,
        # A ledger entry is booked when it is confirmed, not when its proposal
        # was first drafted (which may have crossed a business-day boundary).
        created_at=now,
    )
    db.add(entry)

    for item_data in resolved:
        item = item_data["request_item"]
        inventory_item = item_data["inventory_item"]
        inventory_id = inventory_item.id if inventory_item else None
        # ── FIFO batch deduction / cost capture ───────────────────────────────
        actual_unit_cost: Optional[float] = None

        if entry_type == "log_sale" and inventory_item:
            batches_result = await db.execute(
                select(InventoryBatch)
                .where(
                    InventoryBatch.item_id == inventory_id,
                    InventoryBatch.pharmacy_id == ctx["pharmacy_id"],
                    InventoryBatch.quantity > 0,
                )
                .order_by(InventoryBatch.created_at.asc(), InventoryBatch.id.asc())
                .with_for_update()
            )
            batches = batches_result.scalars().all()

            qty_to_deduct = item.quantity
            weighted_cost_sum = 0.0
            has_known_cost = False
            for batch in batches:
                if qty_to_deduct <= 0:
                    break
                take = min(batch.quantity, qty_to_deduct)
                if batch.unit_buy_price > 0:
                    has_known_cost = True
                weighted_cost_sum += take * batch.unit_buy_price
                batch.quantity -= take
                qty_to_deduct -= take

            if qty_to_deduct > 0:
                fallback = inventory_item.unit_buy_price or 0.0
                if fallback > 0:
                    has_known_cost = True
                weighted_cost_sum += qty_to_deduct * fallback

            # Only record a cost when at least one batch had a real price;
            # otherwise leave it None so profit_complete stays False.
            if has_known_cost and item.quantity > 0:
                actual_unit_cost = round(weighted_cost_sum / item.quantity, 6)
            else:
                actual_unit_cost = None


            sale_result = await db.execute(
                update(InventoryItem)
                .where(
                    InventoryItem.id == inventory_id,
                    InventoryItem.pharmacy_id == ctx["pharmacy_id"],
                    InventoryItem.stock_qty >= item.quantity,
                )
                .values(stock_qty=InventoryItem.stock_qty - item.quantity)
            )
            if sale_result.rowcount != 1:
                await db.rollback()
                raise HTTPException(status_code=409, detail="Inventory changed during confirmation. Review the proposal again.")
            # Lots were just depleted: move the catalog date to the earliest lot still in stock.
            await sync_item_expiry(db, ctx["pharmacy_id"], inventory_item)

        elif entry_type == "log_restock" and inventory_item:
            update_result = await db.execute(
                update(InventoryItem)
                .where(
                    InventoryItem.id == inventory_id,
                    InventoryItem.pharmacy_id == ctx["pharmacy_id"],
                )
                .values(stock_qty=InventoryItem.stock_qty + item.quantity)
            )
            if update_result.rowcount != 1:
                await db.rollback()
                raise HTTPException(status_code=409, detail="Inventory changed during confirmation. Review the proposal again.")
            actual_unit_cost = item.unit_price  # for restock, cost = buy price supplied
            # Same as a direct restock: every confirmed restock is its own lot, so
            # lot totals keep matching stock_qty and later sales cost from real lots.
            db.add(InventoryBatch(
                pharmacy_id=ctx["pharmacy_id"],
                item_id=inventory_id,
                batch_number=None,
                quantity=item.quantity,
                unit_buy_price=item.unit_price or 0.0,
                unit_sell_price=inventory_item.unit_sell_price,
                # The proposal carries no expiry, and the product's date now mirrors
                # the earliest lot, so the new lot must not inherit it.
                expiry_date=None,
                created_at=now,
                updated_at=now,
            ))
            await sync_item_expiry(db, ctx["pharmacy_id"], inventory_item)

        db.add(LedgerEntryItem(
            entry_id=action_id,
            item_id=inventory_id,
            item_name=item_data["name"],
            quantity=item.quantity,
            unit_price=item.unit_price,
            unit_cost=actual_unit_cost,
            subtotal=item_data["subtotal"],
        ))



    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CONFIRM_ACTION",
        entity_type="ledger_entry",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=user.name if user else f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": entry_type,
            "total_amount": total_amount,
            "items_count": len(items),
            "payment_method": payment_method,
            "role_name": ctx.get("role_name"),
        }, ensure_ascii=False),
        timestamp=now,
    ))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This action has already been confirmed.") from exc

    return {
        "success": True,
        "message": "Action confirmed and saved.",
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": entry_type,
            "status": "confirmed",
            "total_amount": total_amount,
            "payment_method": payment_method,
            "items": [
                {
                    "item_name": x["name"],
                    "quantity": x["request_item"].quantity,
                    "unit_price": x["request_item"].unit_price,
                    "subtotal": x["subtotal"],
                    "matched_inventory_id": x["inventory_item"].id if x["inventory_item"] else None,
                }
                for x in resolved
            ],
        },
    }


@router.post("/{action_id}/cancel", response_model=CancelledActionResponse)
async def cancel_action(
    action_id: str,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    result = await db.execute(
        select(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.pharmacy_id == ctx["pharmacy_id"],
        )
        .with_for_update()
    )
    pending = result.scalars().first()
    if not pending:
        raise HTTPException(status_code=404, detail="Action proposal not found.")
    if pending.status != "pending_confirmation":
        raise HTTPException(status_code=409, detail=f"Action is already {pending.status}.")
    if pending.action_type not in ALLOWED_ACTION_TYPES or not has_permission(ctx["role"], pending.action_type, ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="Your role cannot cancel this action.")

    now = utc_now_naive()
    claimed = await db.execute(
        update(PendingAction)
        .where(
            PendingAction.id == action_id,
            PendingAction.pharmacy_id == ctx["pharmacy_id"],
            PendingAction.status == "pending_confirmation",
        )
        .values(status="cancelled", updated_at=now)
    )
    if claimed.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This action is already being processed.")
    pending.status = "cancelled"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CANCEL_ACTION",
        entity_type="proposal",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name"),
        user_role=ctx["role"],
        details_json=json.dumps({"cancelled_action_id": action_id, "role_name": ctx.get("role_name")}),
        timestamp=now,
    ))
    await db.commit()
    return {"success": True, "message": "Action cancelled. No business data was changed.", "proposal": {"id": action_id, "status": "cancelled"}}