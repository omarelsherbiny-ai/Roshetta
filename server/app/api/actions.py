# server/app/api/actions.py
import json
import math
from typing import List, Optional, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import func, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.api.inventory import (
    CATEGORY_NAME_MAX,
    CategoryNamePayload,
    ProductPayload,
    ProductUpdatePayload,
    create_category as create_category_endpoint,
    create_product as create_product_endpoint,
    update_product as update_product_endpoint,
)
from server.app.api.staff import InvitationCreate, create_invitation as create_invitation_endpoint
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
from server.app.db.money import MoneyIn, money_sum, round_money
from server.app.db.session import get_db
from server.app.services.rbac import get_current_user
from server.app.services.clock import utc_now_naive
from server.app.services.expiry import sync_item_expiry
from server.app.services.proposals import proposal_cutoff, proposal_is_expired
from server.app.services.stock import overdrawn_inventory_quantities

router = APIRouter(prefix="/api/actions", tags=["Actions"])
ALLOWED_ACTION_TYPES = {"log_sale", "log_expense", "log_restock", "create_product", "create_category", "update_product", "create_invite", "reduce_stock"}
# The scope a member must hold to see, confirm or cancel each proposal type. A type
# that is not listed uses a scope of its own name (log_sale, log_expense, log_restock).
ACTION_SCOPE = {"create_product": "manage_inventory", "create_category": "manage_inventory", "update_product": "manage_inventory", "create_invite": "manage_staff", "reduce_stock": "manage_inventory"}
# Cards that carry no line items: the card is the details themselves.
ITEMLESS_TYPES = {"create_product", "create_category", "update_product", "create_invite", "reduce_stock"}
# Card types only the member who prepared them may see, confirm or cancel. The four older
# types stay open to any member with the scope: the ledger keeps created_by and
# confirmed_by apart on purpose (a cashier may propose and a pharmacist confirm).
CREATOR_ONLY_TYPES = {"create_category", "update_product", "create_invite", "reduce_stock"}


def _scope_for(action_type: str) -> str:
    return ACTION_SCOPE.get(action_type, action_type)
ALLOWED_PAYMENT_METHODS = {"cash", "card", "credit"}


class ProposedItemModel(BaseModel):
    item_name: str = Field(min_length=1, max_length=150)
    quantity: float = Field(gt=0, le=1_000_000, allow_inf_nan=False)
    unit_price: MoneyIn = Field(ge=0, le=100_000_000, allow_inf_nan=False)
    subtotal: Optional[MoneyIn] = Field(default=None, ge=0, allow_inf_nan=False)
    matched_inventory_id: Optional[int] = None


class ProductDraftModel(BaseModel):
    """Edits the person may make on an add-product card before confirming."""
    name_ar: Optional[str] = Field(default=None, min_length=1, max_length=150)
    name_en: Optional[str] = Field(default=None, min_length=1, max_length=150)
    unit_buy_price: Optional[MoneyIn] = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False)
    unit_sell_price: Optional[MoneyIn] = Field(default=None, gt=0, le=100_000_000, allow_inf_nan=False)
    stock_qty: Optional[float] = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    min_threshold: Optional[float] = Field(default=None, ge=1, le=1_000_000, allow_inf_nan=False)
    category: Optional[str] = Field(default=None, max_length=50)


class ProductDraftResponse(BaseModel):
    name_ar: str
    name_en: str
    unit_buy_price: float
    unit_sell_price: float
    stock_qty: float = 0.0
    min_threshold: float = 5.0
    category: Optional[str] = None


class DuplicateProductResponse(BaseModel):
    id: Optional[int] = None
    name_ar: str = ""
    name_en: str = ""
    stock_qty: float = 0.0
    unit_sell_price: float = 0.0
    exact: bool = False


class InviteDraftResponse(BaseModel):
    role_name: str
    kind: str = "built_in"
    fixed_role: Optional[str] = None
    custom_role_id: Optional[int] = None
    expires_in_days: int = 7
    max_uses: int = 1


class StockChangeResponse(BaseModel):
    item_name: str = ""
    before: float
    after: float
    difference: float
    reason: Optional[str] = None


class ActionConfirmRequest(BaseModel):
    edited_items: Optional[List[ProposedItemModel]] = Field(default=None, max_length=100)
    # create_product and update_product: edits made on the card (update ignores stock_qty),
    # and (create only) the person's choice to add a product whose name already exists.
    product: Optional[ProductDraftModel] = None
    allow_duplicate: bool = False
    # create_category only: the name, edited on the card.
    category_name: Optional[str] = Field(default=None, min_length=1, max_length=CATEGORY_NAME_MAX)
    # create_invite only: the settings, edited on the card (the role is not editable).
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=30)
    max_uses: Optional[int] = Field(default=None, ge=1, le=50)
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
    action_type: Literal["log_sale", "log_expense", "log_restock", "create_product", "create_category", "update_product", "create_invite", "reduce_stock"]
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
    # create_product only
    product: Optional[ProductDraftResponse] = None
    duplicates: List[DuplicateProductResponse] = Field(default_factory=list)
    created_item_id: Optional[int] = None
    # create_category only
    category_name: Optional[str] = None
    # update_product only: the product the card changes, its values before the change and
    # which fields differ (the proposed values are in `product`).
    target_item_id: Optional[int] = None
    before: Optional[ProductDraftResponse] = None
    changed_fields: List[str] = Field(default_factory=list)
    # create_invite only: the role and settings; `join_path` and `invite_expires_at` appear
    # in the confirm answer only (the link is created at confirm and never stored on the card).
    invite: Optional[InviteDraftResponse] = None
    # reduce_stock only: the count now, the count after and the difference (the product id
    # is in `target_item_id`).
    stock_change: Optional[StockChangeResponse] = None
    join_path: Optional[str] = None
    invite_expires_at: Optional[str] = None


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


async def _confirm_create_product(
    db: AsyncSession,
    ctx: dict,
    pending: PendingAction,
    proposal: dict,
    req: ActionConfirmRequest,
    action_id: str,
) -> dict:
    """Confirms an add-product card: the same creation code as POST /api/inventory/create.

    The caller already claimed the proposal (status "processing") and checked the
    manage_inventory scope. The proposal is marked confirmed before the product is
    created so that the creation's own commit saves both together; if it fails, the
    rollback leaves the proposal pending and nothing is created.
    """
    draft = dict(proposal.get("product") or {})
    if req.product is not None:
        draft.update(req.product.model_dump(exclude_none=True))
    try:
        payload = ProductPayload.model_validate(draft)
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The product details are not valid.") from exc

    if not req.allow_duplicate:
        lowered = {payload.name_ar.lower(), payload.name_en.lower()}
        existing = await db.execute(
            select(InventoryItem.id)
            .where(
                InventoryItem.pharmacy_id == ctx["pharmacy_id"],
                or_(
                    func.lower(InventoryItem.name_ar).in_(lowered),
                    func.lower(InventoryItem.name_en).in_(lowered),
                ),
            )
            .limit(1)
        )
        if existing.first() is not None:
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail="A product with this name already exists. Cancel, or confirm again with allow_duplicate to add it anyway.",
            )

    now = utc_now_naive()
    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CONFIRM_ACTION",
        entity_type="proposal",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name") or f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": "create_product",
            "name_ar": payload.name_ar,
            "role_name": ctx.get("role_name"),
        }, ensure_ascii=False),
        timestamp=now,
    ))
    result = await create_product_endpoint(req=payload, db=db, ctx=ctx)
    item = result["item"]
    return {
        "success": True,
        "message": result["message"],
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": "create_product",
            "status": "confirmed",
            "items": [],
            "total_amount": 0.0,
            "payment_method": "cash",
            "product": {
                "name_ar": item.name_ar,
                "name_en": item.name_en,
                "unit_buy_price": item.unit_buy_price,
                "unit_sell_price": item.unit_sell_price,
                "stock_qty": item.stock_qty,
                "min_threshold": item.min_threshold,
                "category": item.category,
            },
            "created_item_id": item.id,
        },
    }


async def _confirm_create_category(
    db: AsyncSession,
    ctx: dict,
    pending: PendingAction,
    proposal: dict,
    req: ActionConfirmRequest,
    action_id: str,
) -> dict:
    """Confirms a create-category card with the same code as POST /api/inventory/categories.

    The caller already claimed the proposal and checked the scope and the creator. Like
    the product card, it is marked confirmed before the creation so that the creation's
    own commit saves both; any failure rolls both back and the card stays pending.
    """
    raw_name = req.category_name if req.category_name is not None else proposal.get("category_name")
    try:
        payload = CategoryNamePayload(name=str(raw_name or ""))
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The category name is not valid.") from exc

    now = utc_now_naive()
    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CONFIRM_ACTION",
        entity_type="proposal",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name") or f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": "create_category",
            "category_name": payload.name,
            "role_name": ctx.get("role_name"),
        }, ensure_ascii=False),
        timestamp=now,
    ))
    try:
        result = await create_category_endpoint(req=payload, db=db, ctx=ctx)
    except HTTPException:
        await db.rollback()
        raise
    category = result["category"]
    return {
        "success": True,
        "message": result["message"],
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": "create_category",
            "status": "confirmed",
            "items": [],
            "total_amount": 0.0,
            "payment_method": "cash",
            "category_name": category.name,
        },
    }


async def _confirm_reduce_stock(
    db: AsyncSession,
    ctx: dict,
    pending: PendingAction,
    proposal: dict,
    req: ActionConfirmRequest,
    action_id: str,
) -> dict:
    """Confirms a reduce-stock card: lowers the count and depletes the oldest lots first.

    The caller already claimed the proposal and checked the scope and the creator. It books
    no sale and no expense (a correction has no price), writes one audit row with the counts,
    and refuses with 409 when the stock is no longer what the card was prepared against.
    """
    change = proposal.get("stock_change") or {}
    item_id = proposal.get("target_item_id")
    try:
        before = float(change["before"])
        after = float(change["after"])
        item_id = int(item_id)
    except (KeyError, TypeError, ValueError):
        await db.rollback()
        raise HTTPException(status_code=409, detail="The saved proposal is incomplete.")
    difference = before - after
    if difference <= 0 or after < 0:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The stock can only be lowered.")

    item_result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.id == item_id, InventoryItem.pharmacy_id == ctx["pharmacy_id"])
        .with_for_update()
    )
    inventory_item = item_result.scalars().first()
    if not inventory_item:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The product no longer exists in this pharmacy's inventory.")
    if abs(float(inventory_item.stock_qty) - before) > 1e-9:
        await db.rollback()
        raise HTTPException(status_code=409, detail="The stock changed since this card was prepared. Ask the assistant again.")

    batches_result = await db.execute(
        select(InventoryBatch)
        .where(
            InventoryBatch.item_id == item_id,
            InventoryBatch.pharmacy_id == ctx["pharmacy_id"],
            InventoryBatch.quantity > 0,
        )
        .order_by(InventoryBatch.created_at.asc(), InventoryBatch.id.asc())
        .with_for_update()
    )
    to_remove = difference
    for batch in batches_result.scalars().all():
        if to_remove <= 0:
            break
        take = min(batch.quantity, to_remove)
        batch.quantity -= take
        to_remove -= take

    updated = await db.execute(
        update(InventoryItem)
        .where(
            InventoryItem.id == item_id,
            InventoryItem.pharmacy_id == ctx["pharmacy_id"],
            InventoryItem.stock_qty >= difference,
        )
        .values(stock_qty=InventoryItem.stock_qty - difference)
    )
    if updated.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Inventory changed during confirmation. Review the proposal again.")
    await sync_item_expiry(db, ctx["pharmacy_id"], inventory_item)

    now = utc_now_naive()
    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="ADJUST_STOCK",
        entity_type="inventory_item",
        entity_id=str(item_id),
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name") or f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": "reduce_stock",
            "item_id": item_id,
            "before": before,
            "after": after,
            "reason": change.get("reason"),
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
        "message": "Stock updated.",
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": "reduce_stock",
            "status": "confirmed",
            "items": [],
            "total_amount": 0.0,
            "payment_method": "cash",
        },
    }


def _same_value(a, b) -> bool:
    """Equal text, or numbers within half a piaster (stored money is rounded to 2 places)."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 0.005
    return (a or None) == (b or None)


async def _confirm_update_product(
    db: AsyncSession,
    ctx: dict,
    pending: PendingAction,
    proposal: dict,
    req: ActionConfirmRequest,
    action_id: str,
) -> dict:
    """Confirms an update-product card with the same code as PUT /api/inventory/items/{id}.

    The caller already claimed the proposal and checked the scope and the creator. The
    product is loaded under a row lock and only the fields on the card change; everything
    else (barcode, active ingredient, expiry, stock) is read from the product itself.
    A product that changed after the card was prepared is refused (409) and the card
    stays pending. Like the other cards, it is marked confirmed before the update so the
    update's own commit saves both; any failure rolls both back.
    """
    editable = ("name_ar", "name_en", "unit_buy_price", "unit_sell_price", "min_threshold", "category")
    target_id = proposal.get("target_item_id")
    changed = [f for f in (proposal.get("changed_fields") or []) if f in editable]
    card_values = dict(proposal.get("product") or {})
    card_before = dict(proposal.get("before") or {})
    if not isinstance(target_id, int) or not changed:
        await db.rollback()
        raise HTTPException(status_code=409, detail="The saved proposal is incomplete.")

    item_result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.id == target_id, InventoryItem.pharmacy_id == ctx["pharmacy_id"])
        .with_for_update()
    )
    item = item_result.scalars().first()
    if item is None:
        await db.rollback()
        raise HTTPException(status_code=409, detail="The product of this card no longer exists. Cancel it and ask again.")

    current = {
        "name_ar": item.name_ar,
        "name_en": item.name_en,
        "unit_buy_price": item.unit_buy_price,
        "unit_sell_price": item.unit_sell_price,
        "min_threshold": item.min_threshold,
        "category": item.category,
    }
    for field in changed:
        if not _same_value(card_before.get(field), current[field]):
            await db.rollback()
            raise HTTPException(
                status_code=409,
                detail="This product was changed after the card was prepared. Cancel it and ask again.",
            )

    merged = {
        **current,
        "barcode": item.barcode,
        "active_ingredient": item.active_ingredient,
        "expiry_date": item.expiry_date,
    }
    for field in changed:
        merged[field] = card_values.get(field, merged[field])
    if req.product is not None:
        edits = req.product.model_dump(exclude_none=True)
        edits.pop("stock_qty", None)
        merged.update({k: v for k, v in edits.items() if k in editable})
    try:
        payload = ProductUpdatePayload.model_validate(merged)
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The product details are not valid.") from exc
    if all(getattr(payload, field) == current[field] for field in editable):
        await db.rollback()
        raise HTTPException(status_code=422, detail="Nothing would change: the product already has these values.")

    now = utc_now_naive()
    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CONFIRM_ACTION",
        entity_type="proposal",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name") or f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": "update_product",
            "item_id": target_id,
            "changed_fields": changed,
            "role_name": ctx.get("role_name"),
        }, ensure_ascii=False),
        timestamp=now,
    ))
    try:
        result = await update_product_endpoint(item_id=target_id, req=payload, db=db, ctx=ctx)
    except HTTPException:
        await db.rollback()
        raise
    updated = result["item"]
    return {
        "success": True,
        "message": result["message"],
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": "update_product",
            "status": "confirmed",
            "items": [],
            "total_amount": 0.0,
            "payment_method": "cash",
            "product": {
                "name_ar": updated.name_ar,
                "name_en": updated.name_en,
                "unit_buy_price": updated.unit_buy_price,
                "unit_sell_price": updated.unit_sell_price,
                "stock_qty": updated.stock_qty,
                "min_threshold": updated.min_threshold,
                "category": updated.category,
            },
        },
    }


async def _confirm_create_invite(
    db: AsyncSession,
    ctx: dict,
    pending: PendingAction,
    proposal: dict,
    req: ActionConfirmRequest,
    action_id: str,
) -> dict:
    """Confirms an invitation card with the same code as POST /api/pharmacies/{id}/invitations.

    The link is created here, under the confirming member's own scopes (nobody grants a
    scope they do not hold, and a role deactivated since the card is refused). The raw
    token is returned once in `join_path` and is never saved on the card. Like the other
    cards it is marked confirmed before the creation so one commit saves both.
    """
    invite = dict(proposal.get("invite") or {})
    try:
        payload = InvitationCreate(
            fixed_role=invite.get("fixed_role"),
            custom_role_id=invite.get("custom_role_id"),
            expires_in_days=req.expires_in_days if req.expires_in_days is not None else invite.get("expires_in_days", 7),
            max_uses=req.max_uses if req.max_uses is not None else invite.get("max_uses", 1),
        )
    except ValidationError as exc:
        await db.rollback()
        raise HTTPException(status_code=422, detail="The invitation details are not valid.") from exc

    now = utc_now_naive()
    pending.status = "confirmed"
    pending.updated_at = now
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"],
        action_type="CONFIRM_ACTION",
        entity_type="proposal",
        entity_id=action_id,
        user_id=ctx["user_id"],
        user_name=ctx.get("user_name") or f"User #{ctx['user_id']}",
        user_role=ctx["role"],
        details_json=json.dumps({
            "action_id": action_id,
            "entry_type": "create_invite",
            "invited_role": invite.get("role_name"),
            "role_name": ctx.get("role_name"),
        }, ensure_ascii=False),
        timestamp=now,
    ))
    try:
        result = await create_invitation_endpoint(pharmacy_id=ctx["pharmacy_id"], req=payload, db=db, ctx=ctx)
    except HTTPException:
        await db.rollback()
        raise
    return {
        "success": True,
        "message": "Invitation link created.",
        "proposal": {
            **proposal,
            "id": action_id,
            "action_type": "create_invite",
            "status": "confirmed",
            "items": [],
            "total_amount": 0.0,
            "payment_method": "cash",
            "invite": {**invite, "expires_in_days": payload.expires_in_days, "max_uses": payload.max_uses},
            "join_path": result["join_path"],
            "invite_expires_at": result["expires_at"],
        },
    }


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
        if pending.action_type not in ALLOWED_ACTION_TYPES or not has_permission(ctx["role"], _scope_for(pending.action_type), ctx.get("scopes")):
            continue
        if pending.action_type in CREATOR_ONLY_TYPES and pending.created_by != ctx["user_id"]:
            continue
        if pending.action_type in ITEMLESS_TYPES:
            # No line items and no total: the card is the details themselves.
            try:
                proposal = _load_proposal(pending)
                card = {
                    **proposal,
                    "id": pending.id,
                    "action_type": pending.action_type,
                    "status": pending.status,
                    "created_at": pending.created_at.isoformat() + "Z" if pending.created_at else None,
                }
                actions.append(ActionProposalResponse.model_validate(card).model_dump())
            except (HTTPException, ValidationError):
                unavailable_count += 1
            continue
        try:
            proposal = _load_proposal(pending)
            items = [ProposedItemModel.model_validate(item).model_dump() for item in proposal["items"]]
            for item in items:
                item["subtotal"] = round_money(item["quantity"] * item["unit_price"])
            payment_method = proposal.get("payment_method", "cash")
            if payment_method not in ALLOWED_PAYMENT_METHODS:
                raise ValueError("Unsupported saved payment method")
            total_amount = money_sum(item["subtotal"] for item in items)
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

    if pending.action_type in CREATOR_ONLY_TYPES and pending.created_by != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="Only the member who prepared this card can confirm it.")

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
    if not has_permission(ctx["role"], _scope_for(entry_type), ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="Your role cannot confirm this action.")

    proposal = _load_proposal(pending)
    if entry_type == "create_product":
        return await _confirm_create_product(db, ctx, pending, proposal, req, action_id)
    if entry_type == "create_category":
        return await _confirm_create_category(db, ctx, pending, proposal, req, action_id)
    if entry_type == "update_product":
        return await _confirm_update_product(db, ctx, pending, proposal, req, action_id)
    if entry_type == "create_invite":
        return await _confirm_create_invite(db, ctx, pending, proposal, req, action_id)
    if entry_type == "reduce_stock":
        return await _confirm_reduce_stock(db, ctx, pending, proposal, req, action_id)
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

        subtotal = round_money(item.quantity * item.unit_price)
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

    total_amount = round_money(total_amount)  # a sum of 2-place subtotals, free of float drift
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
                actual_unit_cost = round_money(weighted_cost_sum / item.quantity, 6)
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
    if pending.action_type not in ALLOWED_ACTION_TYPES or not has_permission(ctx["role"], _scope_for(pending.action_type), ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="Your role cannot cancel this action.")
    if pending.action_type in CREATOR_ONLY_TYPES and pending.created_by != ctx["user_id"]:
        raise HTTPException(status_code=403, detail="Only the member who prepared this card can cancel it.")

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