# server/app/api/pharmacies.py
"""Personal pharmacy hub endpoints. All records are database-backed."""

import json
from datetime import datetime
from typing import Optional, List, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from server.app.db.models import AuditLog, PharmacyMember, PharmacyOwnershipSlot, PharmacyProfile, RevokedAccessToken, User, ROLE_PERMISSIONS, has_permission
from server.app.db.session import get_db
from server.app.services.rbac import get_current_identity
from server.app.services.clock import utc_from_timestamp_naive, utc_now_naive
from server.app.services.security import create_access_token
from server.app.services.financials import BUSINESS_TIMEZONE, local_day_bounds_utc

router = APIRouter(prefix="/api/pharmacies", tags=["Pharmacies"])
MAX_OWNED_PHARMACIES = 5


class PharmacyCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    pharmacy_name: str = Field(min_length=1, max_length=150)
    address: Optional[str] = Field(default=None, max_length=255)
    phone: Optional[str] = Field(default=None, max_length=20)
    license_number: Optional[str] = Field(default=None, max_length=50)
    tax_id: Optional[str] = Field(default=None, max_length=50)


class HubPharmacyResponse(BaseModel):
    id: int
    pharmacy_name: str
    address: Optional[str]
    currency: str
    language: str
    role: str
    role_name: str
    is_owner: bool
    joined_at: Optional[str]


class MyPharmaciesResponse(BaseModel):
    pharmacies: List[HubPharmacyResponse]
    owned_count: int
    owned_limit: int


class CreatePharmacyResponse(BaseModel):
    success: bool
    pharmacy: HubPharmacyResponse
    owned_count: int
    owned_limit: int


class SelectedPharmacyResponse(BaseModel):
    id: int
    pharmacy_name: str
    address: Optional[str]
    currency: str
    language: str


class PharmacySelectionResponse(BaseModel):
    success: bool
    scope: Literal["pharmacy"]
    token: str
    role: str
    role_name: str
    permissions: List[str]
    pharmacy: SelectedPharmacyResponse


class PharmacySummaryResponse(BaseModel):
    pharmacy_id: int
    pharmacy_name: str
    address: Optional[str]
    member_count: int
    product_count: Optional[int]
    low_stock_count: Optional[int]
    today_revenue: Optional[float]
    currency: str
    user_role: str
    permissions: List[str]


def _hub_pharmacy(membership: PharmacyMember) -> dict:
    pharmacy = membership.pharmacy
    role_name = membership.custom_role.name if membership.custom_role else membership.role
    return {
        "id": pharmacy.id,
        "pharmacy_name": pharmacy.pharmacy_name,
        "address": pharmacy.address,
        "currency": pharmacy.currency,
        "language": pharmacy.language,
        "role": "custom" if membership.custom_role_id else membership.role,
        "role_name": role_name,
        "is_owner": membership.role == "owner",
        "joined_at": membership.joined_at.isoformat() if membership.joined_at else None,
    }


def _member_permissions(membership: PharmacyMember) -> list[str]:
    if not membership.custom_role:
        return sorted(ROLE_PERMISSIONS.get(membership.role, set()))
    try:
        scopes = json.loads(membership.custom_role.scopes_json)
        return sorted(scope for scope in scopes if isinstance(scope, str)) if isinstance(scopes, list) else []
    except (TypeError, ValueError):
        return []


@router.get("", response_model=MyPharmaciesResponse)
async def list_my_pharmacies(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    result = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.pharmacy), selectinload(PharmacyMember.custom_role))
        .where(PharmacyMember.user_id == ctx["user_id"], PharmacyMember.is_active.is_(True))
        .order_by(PharmacyMember.joined_at.desc(), PharmacyMember.id.desc())
    )
    memberships = result.scalars().all()
    owned_count = sum(1 for item in memberships if item.role == "owner")
    return {
        "pharmacies": [_hub_pharmacy(item) for item in memberships if item.pharmacy],
        "owned_count": owned_count,
        "owned_limit": MAX_OWNED_PHARMACIES,
    }


@router.post("", response_model=CreatePharmacyResponse)
async def create_pharmacy(
    req: PharmacyCreate,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Create a pharmacy separately from personal-account registration."""
    # Serialize ownership checks per account on databases that support row locks.
    owner_result = await db.execute(
        select(User).where(User.id == ctx["user_id"]).with_for_update()
    )
    owner = owner_result.scalars().first()
    if not owner or not owner.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive or no longer exists.")

    count_result = await db.execute(
        select(func.count(PharmacyMember.id)).where(
            PharmacyMember.user_id == ctx["user_id"],
            PharmacyMember.role == "owner",
            PharmacyMember.is_active.is_(True),
        )
    )
    owned_count = int(count_result.scalar_one())
    if owned_count >= MAX_OWNED_PHARMACIES:
        raise HTTPException(status_code=409, detail="An account can own up to five pharmacies.")

    slot_result = await db.execute(select(PharmacyOwnershipSlot.slot_number).where(PharmacyOwnershipSlot.user_id == owner.id))
    occupied_slots = set(slot_result.scalars().all())
    available_slots = set(range(1, MAX_OWNED_PHARMACIES + 1)) - occupied_slots
    if not available_slots:
        raise HTTPException(status_code=409, detail="An account can own up to five pharmacies.")

    pharmacy = PharmacyProfile(
        pharmacy_name=req.pharmacy_name,
        owner_name=owner.name,
        phone=req.phone or owner.phone,
        address=req.address,
        license_number=req.license_number,
        tax_id=req.tax_id,
        currency="EGP",
        numerals_format="western",
        low_stock_default=5.0,
        language=owner.language_pref or "ar",
        is_initialized=True,
    )
    db.add(pharmacy)
    await db.flush()
    db.add(PharmacyOwnershipSlot(user_id=owner.id, pharmacy_id=pharmacy.id, slot_number=min(available_slots)))
    membership = PharmacyMember(
        pharmacy_id=pharmacy.id,
        user_id=owner.id,
        role="owner",
        is_active=True,
    )
    db.add(membership)
    db.add(AuditLog(
        pharmacy_id=pharmacy.id,
        action_type="CREATE_PHARMACY",
        entity_type="pharmacy",
        entity_id=str(pharmacy.id),
        user_id=owner.id,
        user_name=owner.name,
        user_role="owner",
        timestamp=utc_now_naive(),
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="The ownership limit was reached by another request. Refresh the pharmacy list.") from exc
    await db.refresh(pharmacy)
    await db.refresh(membership)
    membership.pharmacy = pharmacy
    return {
        "success": True,
        "pharmacy": _hub_pharmacy(membership),
        "owned_count": owned_count + 1,
        "owned_limit": MAX_OWNED_PHARMACIES,
    }


@router.post("/{pharmacy_id}/select", response_model=PharmacySelectionResponse)
async def select_pharmacy(
    pharmacy_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    result = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.pharmacy), selectinload(PharmacyMember.custom_role))
        .where(
            PharmacyMember.user_id == ctx["user_id"],
            PharmacyMember.pharmacy_id == pharmacy_id,
            PharmacyMember.is_active.is_(True),
        )
    )
    membership = result.scalars().first()
    if not membership or not membership.pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found in this account's memberships.")

    now = utc_now_naive()
    await db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now))
    if ctx.get("pharmacy_id") is not None:
        db.add(RevokedAccessToken(
            token_id=ctx["token_id"],
            expires_at=utc_from_timestamp_naive(ctx["token_expires_at"]),
            revoked_at=now,
        ))
    db.add(AuditLog(
        pharmacy_id=pharmacy_id, action_type="SELECT_PHARMACY", entity_type="pharmacy",
        entity_id=str(pharmacy_id), user_id=ctx["user_id"], user_name=ctx.get("user_name"),
        # AuditLog.user_role is String(20); a custom role's display name can be 60 characters.
        user_role="custom" if membership.custom_role_id else membership.role,
        timestamp=now,
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        # The same token was used for two parallel selections: only one may win.
        await db.rollback()
        raise HTTPException(status_code=401, detail="This session has been signed out.") from exc

    return {
        "success": True,
        "scope": "pharmacy",
        "token": create_access_token(ctx["user_id"], pharmacy_id),
        "role": "custom" if membership.custom_role_id else membership.role,
        "role_name": membership.custom_role.name if membership.custom_role else membership.role,
        "permissions": _member_permissions(membership),
        "pharmacy": {
            "id": membership.pharmacy.id,
            "pharmacy_name": membership.pharmacy.pharmacy_name,
            "address": membership.pharmacy.address,
            "currency": membership.pharmacy.currency,
            "language": membership.pharmacy.language,
        },
    }


@router.get("/{pharmacy_id}/summary", response_model=PharmacySummaryResponse)
async def get_pharmacy_summary(
    pharmacy_id: int,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Return a summary of metrics for a single pharmacy (members, products, revenue, low-stock)."""
    from server.app.db.models import InventoryItem, LedgerEntry

    member_result = await db.execute(
        select(PharmacyMember).options(selectinload(PharmacyMember.custom_role)).where(
            PharmacyMember.user_id == ctx["user_id"],
            PharmacyMember.pharmacy_id == pharmacy_id,
            PharmacyMember.is_active.is_(True),
        )
    )
    membership = member_result.scalars().first()
    if not membership:
        raise HTTPException(status_code=404, detail="Pharmacy not found in this account's memberships.")

    pharmacy_result = await db.execute(
        select(PharmacyProfile).where(PharmacyProfile.id == pharmacy_id)
    )
    pharmacy = pharmacy_result.scalars().first()
    if not pharmacy:
        raise HTTPException(status_code=404, detail="Pharmacy not found.")

    member_count_res = await db.execute(
        select(func.count(PharmacyMember.id)).where(
            PharmacyMember.pharmacy_id == pharmacy_id,
            PharmacyMember.is_active.is_(True),
        )
    )
    member_count = int(member_count_res.scalar_one() or 0)

    scopes = None
    if membership.custom_role:
        try:
            parsed_scopes = json.loads(membership.custom_role.scopes_json)
            scopes = parsed_scopes if isinstance(parsed_scopes, list) else []
        except (TypeError, ValueError):
            scopes = []
    can_view_inventory = has_permission(membership.role, "view_inventory", scopes)
    can_view_reports = has_permission(membership.role, "view_reports", scopes)

    product_count = None
    low_stock_count = None
    if can_view_inventory:
        product_count_res = await db.execute(
            select(func.count(InventoryItem.id)).where(InventoryItem.pharmacy_id == pharmacy_id)
        )
        product_count = int(product_count_res.scalar_one() or 0)

        low_stock_res = await db.execute(
            select(func.count(InventoryItem.id)).where(
                InventoryItem.pharmacy_id == pharmacy_id,
                InventoryItem.stock_qty <= InventoryItem.min_threshold,
            )
        )
        low_stock_count = int(low_stock_res.scalar_one() or 0)

    today_revenue = None
    if can_view_reports:
        today_start, today_end, _ = local_day_bounds_utc(datetime.now(BUSINESS_TIMEZONE).date())
        revenue_filters = [
            LedgerEntry.pharmacy_id == pharmacy_id,
            LedgerEntry.entry_type == "log_sale",
            LedgerEntry.created_at >= today_start,
            LedgerEntry.created_at < today_end,
        ]
        if membership.role == "cashier":
            revenue_filters.append(func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == ctx["user_id"])
        rev_res = await db.execute(select(func.sum(LedgerEntry.total_amount)).where(*revenue_filters))
        today_revenue = round(float(rev_res.scalar_one() or 0), 2)

    return {
        "pharmacy_id": pharmacy_id,
        "pharmacy_name": pharmacy.pharmacy_name,
        "address": pharmacy.address,
        "member_count": member_count,
        "product_count": product_count,
        "low_stock_count": low_stock_count,
        "today_revenue": today_revenue,
        "currency": pharmacy.currency or "EGP",
        "user_role": membership.role,
        "permissions": _member_permissions(membership),
    }