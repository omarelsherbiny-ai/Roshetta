# server/app/api/ai_propose.py
"""The /ai tools that prepare something for a person to confirm (Session 119, task 9 step 5;
propose_restock added in Session 126: the model, not a local regex, prepares a restock card).

`propose_product` lets the MicroMind agent suggest a new product. It writes NOTHING to the
inventory or the ledger: it only stores a pending "add this product?" card, built by the
same function the local chat path uses, that the signed-in person reviews, edits and
confirms in the app (POST /api/actions/{id}/confirm, unchanged). The model can never
confirm it.

Rules baked in:
- Identity and pharmacy come only from the Bearer token; the body has no identity field
  and refuses any extra field.
- Needs the manage_inventory scope (the same scope confirming the card needs).
- At most MAX_PENDING_PRODUCT_CARDS cards wait per person, so a looping model cannot
  flood the pending list.
- The answer holds only the new card's id, a one-line summary and whether a similar
  product already exists; never a product name from the inventory.
"""
import json
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

# The card builder lives in the agents layer (plain Python); the chat path uses it too.
from agents.agents.verification import (
    _create_product_proposal,
    verification_agent,
    build_category_proposal,
    build_invite_proposal,
    build_product_update_proposal,
    clean_category_name,
)
from server.app.api.inventory import CATEGORY_NAME_MAX, _find_category
from server.app.api.staff import _held_scopes, _role_dict
from server.app.config import settings
from server.app.db.models import InventoryItem, PendingAction, PharmacyRole, has_permission
from server.app.db.session import get_db
from server.app.services.clock import utc_now_naive
from server.app.services.invite_roles import invitable_names, resolve_invite_role
from server.app.services.proposals import proposal_cutoff
from server.app.services.rbac import require_permission

MAX_PENDING_PRODUCT_CARDS = 5
MAX_PENDING_CATEGORY_CARDS = 5
MAX_PENDING_UPDATE_CARDS = 5
MAX_PENDING_INVITE_CARDS = 5
MAX_PENDING_RESTOCK_CARDS = 5

# No dependencies here: ai.py includes this router with its own rate limit.
propose_router = APIRouter()


class AIProductProposalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=150, description="Product name exactly as the user gave it")
    unit_sell_price: float = Field(gt=0, le=100_000_000, allow_inf_nan=False, description="Selling price in EGP")
    unit_buy_price: Optional[float] = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False, description="Buying price in EGP, only if the user gave it")
    stock_qty: Optional[float] = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False, description="Starting stock, only if the user gave it")
    min_threshold: Optional[float] = Field(default=None, ge=1, le=1_000_000, allow_inf_nan=False, description="Low-stock level, only if the user gave it")
    category: Optional[str] = Field(default=None, max_length=50)
    language: Literal["ar", "en"] = Field(default="ar", description="Language of the user's question")


class AICategoryProposalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=CATEGORY_NAME_MAX, description="Category name exactly as the user gave it")
    language: Literal["ar", "en"] = Field(default="ar", description="Language of the user's question")


class AIProductUpdateRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    item_id: int = Field(ge=1, description="Product id exactly as a search or match result returned it; never guess one")
    name_ar: Optional[str] = Field(default=None, min_length=1, max_length=150, description="New Arabic name, only if the user asked to change it")
    name_en: Optional[str] = Field(default=None, min_length=1, max_length=150, description="New English name, only if the user asked to change it")
    unit_sell_price: Optional[float] = Field(default=None, gt=0, le=100_000_000, allow_inf_nan=False, description="New selling price in EGP, only if the user asked to change it")
    unit_buy_price: Optional[float] = Field(default=None, ge=0, le=100_000_000, allow_inf_nan=False, description="New buying price in EGP, only if the user asked to change it")
    min_threshold: Optional[float] = Field(default=None, ge=1, le=1_000_000, allow_inf_nan=False, description="New low-stock level, only if the user asked to change it")
    category: Optional[str] = Field(default=None, min_length=1, max_length=40, description="New category, only if the user asked to change it")
    language: Literal["ar", "en"] = Field(default="ar", description="Language of the user's question")

    @model_validator(mode="after")
    def _needs_a_change(self):
        if all(getattr(self, field) is None for field in (
            "name_ar", "name_en", "unit_sell_price", "unit_buy_price", "min_threshold", "category",
        )):
            raise ValueError("Give at least one value to change.")
        return self


class AIInviteProposalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    role_name: str = Field(min_length=1, max_length=60, description="Name of the role to invite, exactly as the user said it (a built-in role such as cashier, pharmacist or viewer, or a custom role's name)")
    expires_in_days: int = Field(default=7, ge=1, le=30, description="Days the link stays valid; leave at 7 unless the user asked for another number")
    max_uses: int = Field(default=1, ge=1, le=50, description="How many people may use the link; leave at 1 unless the user asked for more")
    language: Literal["ar", "en"] = Field(default="ar", description="Language of the user's question")


class AIRestockProposalRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    item_id: int = Field(ge=1, description="Product id exactly as a search or match result returned it; never guess one")
    quantity: float = Field(gt=0, le=1_000_000, allow_inf_nan=False, description="How many units to ADD to the stock (not the new total), as the user said it")
    language: Literal["ar", "en"] = Field(default="ar", description="Language of the user's question")


class AIProposalResult(BaseModel):
    status: Literal["pending_review", "not_created"]
    proposal_id: Optional[str] = None
    summary: str
    similar_product_exists: bool = False


def build_product_card(req: AIProductProposalRequest, inventory: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """The pending card for this request, or None when the card builder refuses it."""
    state = {
        "language": req.language,
        "product_draft": {
            "name": req.name,
            "unit_buy_price": req.unit_buy_price,
            "unit_sell_price": req.unit_sell_price,
            "stock_qty": req.stock_qty,
            "min_threshold": req.min_threshold,
            "category": req.category,
        },
        "inventory_data": inventory,
    }
    return _create_product_proposal(state).get("proposal")


def _not_created(reason: str) -> Dict[str, Any]:
    return {"status": "not_created", "proposal_id": None, "summary": reason, "similar_product_exists": False}


@propose_router.post(
    "/propose-product",
    operation_id="propose_product",
    summary="Prepare a card for the user to review, edit and confirm that adds a NEW product. Nothing is saved until the user confirms in the app.",
    response_model=AIProposalResult,
)
async def propose_product(
    req: AIProductProposalRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_inventory")),
):
    pharmacy_id = ctx["pharmacy_id"]
    user_id = ctx.get("user_id")
    if user_id is None:
        return _not_created("No card was prepared: the signed-in user could not be identified.")

    waiting = await db.execute(
        select(func.count())
        .select_from(PendingAction)
        .where(
            PendingAction.pharmacy_id == pharmacy_id,
            PendingAction.created_by == user_id,
            PendingAction.action_type == "create_product",
            PendingAction.status == "pending_confirmation",
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
    )
    if (waiting.scalar_one() or 0) >= MAX_PENDING_PRODUCT_CARDS:
        return _not_created("No card was prepared: too many product cards are already waiting. Ask the user to confirm or cancel them first.")

    result = await db.execute(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id))
    inventory = [
        {
            "id": item.id,
            "name_ar": item.name_ar,
            "name_en": item.name_en,
            "stock_qty": item.stock_qty,
            "unit_sell_price": item.unit_sell_price,
            "category": item.category,
        }
        for item in result.scalars().all()
    ]

    proposal = build_product_card(req, inventory)
    if not proposal:
        return _not_created("No card was prepared: the product name or the sell price is missing.")

    now = utc_now_naive()
    db.add(PendingAction(
        id=proposal["id"],
        pharmacy_id=pharmacy_id,
        created_by=user_id,
        action_type="create_product",
        status="pending_confirmation",
        payload_json=json.dumps(proposal, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    ))
    await db.commit()
    return {
        "status": "pending_review",
        "proposal_id": proposal["id"],
        "summary": proposal.get("summary_en") or "",
        "similar_product_exists": bool(proposal.get("duplicates")),
    }


@propose_router.post(
    "/propose-product-update",
    operation_id="propose_product_update",
    summary="Prepare a card for the user to review, edit and confirm that CHANGES an existing product's name, prices, low-stock level or category. Stock cannot be changed this way. Nothing is saved until the user confirms in the app.",
    response_model=AIProposalResult,
)
async def propose_product_update(
    req: AIProductUpdateRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_inventory")),
):
    pharmacy_id = ctx["pharmacy_id"]
    user_id = ctx.get("user_id")
    if user_id is None:
        return _not_created("No card was prepared: the signed-in user could not be identified.")

    waiting = await db.execute(
        select(func.count())
        .select_from(PendingAction)
        .where(
            PendingAction.pharmacy_id == pharmacy_id,
            PendingAction.created_by == user_id,
            PendingAction.action_type == "update_product",
            PendingAction.status == "pending_confirmation",
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
    )
    if (waiting.scalar_one() or 0) >= MAX_PENDING_UPDATE_CARDS:
        return _not_created("No card was prepared: too many update cards are already waiting. Ask the user to confirm or cancel them first.")

    result = await db.execute(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id))
    rows = [
        {
            "id": item.id,
            "name_ar": item.name_ar,
            "name_en": item.name_en,
            "stock_qty": item.stock_qty,
            "min_threshold": item.min_threshold,
            "unit_buy_price": item.unit_buy_price,
            "unit_sell_price": item.unit_sell_price,
            "category": item.category,
        }
        for item in result.scalars().all()
    ]
    current = next((row for row in rows if row["id"] == req.item_id), None)
    if current is None:
        return _not_created("No card was prepared: no product with this id exists. Search for the product again and use the id the search returned.")

    changes = {
        field: getattr(req, field)
        for field in ("name_ar", "name_en", "unit_buy_price", "unit_sell_price", "min_threshold", "category")
        if getattr(req, field) is not None
    }
    proposal = build_product_update_proposal(current, changes, req.language, [row for row in rows if row["id"] != req.item_id])
    if not proposal:
        return _not_created("No card was prepared: every value asked for is already what the product has.")

    now = utc_now_naive()
    db.add(PendingAction(
        id=proposal["id"],
        pharmacy_id=pharmacy_id,
        created_by=user_id,
        action_type="update_product",
        status="pending_confirmation",
        payload_json=json.dumps(proposal, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    ))
    await db.commit()
    # The answer names the changed fields only: never the product's old or new buy price.
    return {
        "status": "pending_review",
        "proposal_id": proposal["id"],
        "summary": "Update card prepared for product #%d: %s." % (req.item_id, ", ".join(proposal["changed_fields"])),
        "similar_product_exists": any("already has this name" in w for w in proposal["warnings"]),
    }


@propose_router.post(
    "/propose-invite",
    operation_id="propose_invite",
    summary="Prepare a card for the user to review, edit and confirm that creates an invitation link for a role. The link does not exist until the user confirms in the app and is never shown to you.",
    response_model=AIProposalResult,
)
async def propose_invite(
    req: AIInviteProposalRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_staff")),
):
    pharmacy_id = ctx["pharmacy_id"]
    user_id = ctx.get("user_id")
    if user_id is None:
        return _not_created("No card was prepared: the signed-in user could not be identified.")

    waiting = await db.execute(
        select(func.count())
        .select_from(PendingAction)
        .where(
            PendingAction.pharmacy_id == pharmacy_id,
            PendingAction.created_by == user_id,
            PendingAction.action_type == "create_invite",
            PendingAction.status == "pending_confirmation",
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
    )
    if (waiting.scalar_one() or 0) >= MAX_PENDING_INVITE_CARDS:
        return _not_created("No card was prepared: too many invitation cards are already waiting. Ask the user to confirm or cancel them first.")

    # The roles of this pharmacy and whether this member may hand each one out: the same
    # rule as POST /api/pharmacies/{id}/invitations (nobody grants a scope they do not hold).
    is_owner = ctx["role"] == "owner"
    held = _held_scopes(ctx["role"], ctx.get("scopes"))
    roles = []
    for built_in in ("pharmacist", "cashier", "viewer"):
        scopes = _held_scopes(built_in, None)
        roles.append({
            "name": built_in, "kind": "built_in", "fixed_role": built_in, "custom_role_id": None,
            "scopes": sorted(scopes), "grantable": is_owner or scopes <= held,
        })
    custom = await db.execute(
        select(PharmacyRole).where(PharmacyRole.pharmacy_id == pharmacy_id, PharmacyRole.is_active.is_(True))
    )
    for role in custom.scalars().all():
        scopes = _held_scopes("custom", _role_dict(role)["scopes"])
        roles.append({
            "name": role.name, "kind": "custom", "fixed_role": None, "custom_role_id": role.id,
            "scopes": sorted(scopes), "grantable": is_owner or scopes <= held,
        })

    chosen, matches = resolve_invite_role(req.role_name, roles)
    options = ", ".join(invitable_names(roles)) or "none"
    if chosen is None and len(matches) > 1:
        return _not_created("No card was prepared: more than one role has this name. Roles this member may invite: %s. Ask the user which one." % options)
    if chosen is None:
        return _not_created("No card was prepared: no role has this name. Roles this member may invite: %s. Ask the user which one." % options)
    if not chosen["grantable"]:
        return _not_created("No card was prepared: this member cannot invite that role because it holds permissions this member does not hold. Roles this member may invite: %s." % options)

    proposal = build_invite_proposal(chosen, req.expires_in_days, req.max_uses, req.language)
    if not proposal:
        return _not_created("No card was prepared: the role or the numbers are not valid.")

    now = utc_now_naive()
    db.add(PendingAction(
        id=proposal["id"],
        pharmacy_id=pharmacy_id,
        created_by=user_id,
        action_type="create_invite",
        status="pending_confirmation",
        payload_json=json.dumps(proposal, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    ))
    await db.commit()
    # No link exists yet and none is ever returned here.
    return {
        "status": "pending_review",
        "proposal_id": proposal["id"],
        "summary": proposal["summary_en"],
        "similar_product_exists": False,
    }


@propose_router.post(
    "/propose-category",
    operation_id="propose_category",
    summary="Prepare a card for the user to review, edit and confirm that creates a NEW product category. Nothing is saved until the user confirms in the app.",
    response_model=AIProposalResult,
)
async def propose_category(
    req: AICategoryProposalRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("manage_inventory")),
):
    pharmacy_id = ctx["pharmacy_id"]
    user_id = ctx.get("user_id")
    if user_id is None:
        return _not_created("No card was prepared: the signed-in user could not be identified.")

    name = clean_category_name(req.name)
    if not name:
        return _not_created("No card was prepared: the category name is blank.")

    waiting = await db.execute(
        select(func.count())
        .select_from(PendingAction)
        .where(
            PendingAction.pharmacy_id == pharmacy_id,
            PendingAction.created_by == user_id,
            PendingAction.action_type == "create_category",
            PendingAction.status == "pending_confirmation",
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
    )
    if (waiting.scalar_one() or 0) >= MAX_PENDING_CATEGORY_CARDS:
        return _not_created("No card was prepared: too many category cards are already waiting. Ask the user to confirm or cancel them first.")

    if await _find_category(db, pharmacy_id, name) is not None:
        return {
            "status": "not_created",
            "proposal_id": None,
            "summary": "No card was prepared: a category with this name already exists.",
            "similar_product_exists": False,
        }

    proposal = build_category_proposal(name, req.language)
    if not proposal:
        return _not_created("No card was prepared: the category name is blank.")

    now = utc_now_naive()
    db.add(PendingAction(
        id=proposal["id"],
        pharmacy_id=pharmacy_id,
        created_by=user_id,
        action_type="create_category",
        status="pending_confirmation",
        payload_json=json.dumps(proposal, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    ))
    await db.commit()
    return {
        "status": "pending_review",
        "proposal_id": proposal["id"],
        "summary": proposal["summary_en"],
        "similar_product_exists": False,
    }


@propose_router.post(
    "/propose-restock",
    operation_id="propose_restock",
    summary="Prepare a card for the user to review, edit and confirm that ADDS units to an existing product's stock. The buy price is taken from the product and the user can edit it on the card. Nothing is saved until the user confirms in the app.",
    response_model=AIProposalResult,
)
async def propose_restock(
    req: AIRestockProposalRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(require_permission("log_restock")),
):
    pharmacy_id = ctx["pharmacy_id"]
    user_id = ctx.get("user_id")
    if user_id is None:
        return _not_created("No card was prepared: the signed-in user could not be identified.")
    # Confirming a restock needs the inventory view as well (same rule as the chat path).
    if not has_permission(ctx["role"], "view_inventory", ctx.get("scopes")):
        return _not_created("No card was prepared: this member may not view the inventory.")

    waiting = await db.execute(
        select(func.count())
        .select_from(PendingAction)
        .where(
            PendingAction.pharmacy_id == pharmacy_id,
            PendingAction.created_by == user_id,
            PendingAction.action_type == "log_restock",
            PendingAction.status == "pending_confirmation",
            PendingAction.created_at >= proposal_cutoff(utc_now_naive(), settings.PENDING_ACTION_TTL_HOURS),
        )
    )
    if (waiting.scalar_one() or 0) >= MAX_PENDING_RESTOCK_CARDS:
        return _not_created("No card was prepared: too many restock cards are already waiting. Ask the user to confirm or cancel them first.")

    result = await db.execute(select(InventoryItem).where(InventoryItem.pharmacy_id == pharmacy_id))
    rows = [
        {
            "id": item.id,
            "name_ar": item.name_ar,
            "name_en": item.name_en,
            "stock_qty": item.stock_qty,
            "min_threshold": item.min_threshold,
            "unit_buy_price": item.unit_buy_price,
            "unit_sell_price": item.unit_sell_price,
            "price_batches": [],
            "category": item.category,
        }
        for item in result.scalars().all()
    ]
    current = next((row for row in rows if row["id"] == req.item_id), None)
    if current is None:
        return _not_created("No card was prepared: no product with this id exists. Search for the product again and use the id the search returned.")

    # The same card builder the local restock path uses, so the card, its warnings and its
    # confirm step are identical. The price is left at 0: the builder fills in the product's
    # own buy price, and the person can edit it on the card.
    state = {
        "intent": "log_restock",
        "language": req.language,
        "payment_method": "cash",
        "inventory_data": rows,
        "extracted_items": [{
            "item_name": current["name_ar"],
            "quantity": req.quantity,
            "unit_price": 0.0,
            "subtotal": 0.0,
        }],
    }
    proposal = verification_agent(state).get("proposal")
    if not proposal or not proposal.get("items"):
        return _not_created("No card was prepared: the product or the quantity could not be used.")
    # Two products can share an Arabic name: pin the line to the id the model chose.
    line = proposal["items"][0]
    line["matched_inventory_id"] = current["id"]
    line["stock_available"] = current["stock_qty"]

    now = utc_now_naive()
    db.add(PendingAction(
        id=proposal["id"],
        pharmacy_id=pharmacy_id,
        created_by=user_id,
        action_type="log_restock",
        status="pending_confirmation",
        payload_json=json.dumps(proposal, ensure_ascii=False),
        created_at=now,
        updated_at=now,
    ))
    await db.commit()
    # No price or total in the answer: the buy price stays out of the model's view.
    return {
        "status": "pending_review",
        "proposal_id": proposal["id"],
        "summary": "Restock card prepared for product #%d: add %s units." % (req.item_id, ("%g" % req.quantity)),
        "similar_product_exists": False,
    }