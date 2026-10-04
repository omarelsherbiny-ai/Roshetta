# server/app/api/me.py
"""Personal account endpoints — user profile and per-user activity."""

import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Literal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from server.app.db.models import (
    AuditLog, LedgerEntry, LedgerEntryItem, PharmacyMember, User,
)
from server.app.db.session import get_db
from server.app.services.rbac import get_current_identity
from server.app.services.financials import BUSINESS_TIMEZONE, local_day_bounds_utc
from server.app.config import settings

router = APIRouter(prefix="/api/me", tags=["My Account"])
MAX_PROFILE_PHOTO_BYTES = 5 * 1024 * 1024
PROFILE_IMAGE_TYPES = {
    "image/jpeg": ("jpg", b"\xff\xd8\xff"),
    "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
    "image/webp": ("webp", b"RIFF"),
}


def _profile_upload_dir() -> Path:
    path = Path(settings.STORAGE_LOCAL_DIR)
    if not path.is_absolute():
        path = Path(__file__).resolve().parents[3] / path
    return path.resolve()


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=160)
    birth_date: Optional[str] = Field(default=None)  # YYYY-MM-DD or None to clear
    language_pref: Optional[str] = Field(default=None, pattern="^(ar|en)$")


class MyProfileUserResponse(BaseModel):
    id: int
    name: str
    phone: str
    location: Optional[str]
    birth_date: Optional[str]
    language_pref: str
    photo_url: Optional[str]
    is_active: bool
    created_at: Optional[str]


class MyProfileResponse(BaseModel):
    user: MyProfileUserResponse
    pharmacy_count: int
    pharmacy_ids: List[int]
    roles: Dict[str, str]


class MyProfileUpdateResponse(BaseModel):
    success: bool
    user: MyProfileUserResponse


class PhotoUploadResponse(BaseModel):
    success: bool
    photo_url: str


class ActivityEntryResponse(BaseModel):
    id: str
    entry_type: str
    total_amount: float
    payment_method: str
    notes: Optional[str]
    created_at: Optional[str]


class MyActivityResponse(BaseModel):
    period: Literal["day", "week", "month", "all"]
    pharmacy_id: Optional[int]
    sales_count: int
    expenses_count: int
    restocks_count: int
    total_restock: float
    total_sales: float
    total_expenses: float
    items_sold: float
    items_restocked: float
    net: float
    recent_entries: List[ActivityEntryResponse]


def _user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "name": user.name,
        "phone": user.phone,
        "location": user.location,
        "birth_date": user.birth_date,
        "language_pref": user.language_pref or "ar",
        "photo_url": user.photo_url,
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


@router.get("", response_model=MyProfileResponse)
async def get_my_profile(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Return the full profile of the authenticated user."""
    result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    # Attach pharmacy memberships summary
    memberships_result = await db.execute(
        select(PharmacyMember).where(
            PharmacyMember.user_id == user.id,
            PharmacyMember.is_active.is_(True),
        )
    )
    memberships = memberships_result.scalars().all()

    return {
        "user": _user_dict(user),
        "pharmacy_count": len(memberships),
        "pharmacy_ids": [m.pharmacy_id for m in memberships],
        "roles": {str(m.pharmacy_id): m.role for m in memberships},
    }


@router.patch("", response_model=MyProfileUpdateResponse)
async def update_my_profile(
    req: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Update editable fields on the authenticated user's profile."""
    result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")

    changed = False
    if req.name is not None:
        user.name = req.name
        changed = True
    if req.location is not None:
        user.location = req.location or None
        changed = True
    if req.birth_date is not None:
        # Strict YYYY-MM-DD (strptime also accepts "2026-1-5", which would be stored non-ISO).
        if req.birth_date:
            try:
                if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", req.birth_date):
                    raise ValueError("not YYYY-MM-DD")
                parsed_birth = date.fromisoformat(req.birth_date)
            except ValueError:
                raise HTTPException(status_code=422, detail="birth_date must be YYYY-MM-DD.")
            if parsed_birth > datetime.now(BUSINESS_TIMEZONE).date():
                raise HTTPException(status_code=422, detail="birth_date cannot be in the future.")
        user.birth_date = req.birth_date or None
        changed = True
    if req.language_pref is not None:
        user.language_pref = req.language_pref
        changed = True

    if changed:
        db.add(AuditLog(
            pharmacy_id=ctx.get("pharmacy_id"),
            action_type="UPDATE_PROFILE",
            entity_type="user",
            entity_id=str(user.id),
            user_id=user.id,
            user_name=user.name,
            user_role=ctx.get("role"),
            details_json=None,
        ))
        await db.commit()
        await db.refresh(user)

    return {"success": True, "user": _user_dict(user)}


@router.post("/photo", response_model=PhotoUploadResponse)
async def upload_my_photo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Upload a profile photo; returns the stored URL."""
    media_type = file.content_type or ""
    image_format = PROFILE_IMAGE_TYPES.get(media_type)
    if not image_format:
        raise HTTPException(status_code=422, detail="Use a JPEG, PNG, or WebP profile image.")
    ext, signature = image_format
    content = await file.read(MAX_PROFILE_PHOTO_BYTES + 1)
    if len(content) > MAX_PROFILE_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="Profile image must be 5 MB or smaller.")
    if not content.startswith(signature) or (media_type == "image/webp" and content[8:12] != b"WEBP"):
        raise HTTPException(status_code=422, detail="The image content does not match its declared type.")

    upload_dir = _profile_upload_dir()
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = f"avatar_{ctx['user_id']}_{uuid.uuid4().hex}.{ext}"
    filepath = upload_dir / filename
    filepath.write_bytes(content)

    result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = result.scalars().first()
    if not user:
        filepath.unlink(missing_ok=True)
        raise HTTPException(status_code=404, detail="User account not found.")
    previous_photo_url = user.photo_url
    user.photo_url = f"/api/me/photo/{filename}"
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        filepath.unlink(missing_ok=True)
        raise

    if previous_photo_url and previous_photo_url.startswith(f"/api/me/photo/avatar_{ctx['user_id']}_"):
        old_name = previous_photo_url.rsplit("/", 1)[-1]
        if old_name != filename and Path(old_name).name == old_name:
            (_profile_upload_dir() / old_name).unlink(missing_ok=True)

    return {"success": True, "photo_url": user.photo_url}


@router.get(
    "/photo/{filename}",
    response_class=FileResponse,
    responses={200: {"content": {
        "image/jpeg": {"schema": {"type": "string", "format": "binary"}},
        "image/png": {"schema": {"type": "string", "format": "binary"}},
        "image/webp": {"schema": {"type": "string", "format": "binary"}},
    }}},
)
async def get_my_photo(
    filename: str,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Serve only this account's own generated profile-image key."""
    if Path(filename).name != filename or not filename.startswith(f"avatar_{ctx['user_id']}_"):
        raise HTTPException(status_code=404, detail="Profile image not found.")
    suffix = Path(filename).suffix.lower()
    media_type = {".jpg": "image/jpeg", ".png": "image/png", ".webp": "image/webp"}.get(suffix)
    if not media_type:
        raise HTTPException(status_code=404, detail="Profile image not found.")
    result = await db.execute(select(User.photo_url).where(User.id == ctx["user_id"]))
    if result.scalar_one_or_none() != f"/api/me/photo/{filename}":
        raise HTTPException(status_code=404, detail="Profile image not found.")
    filepath = _profile_upload_dir() / filename
    if not filepath.is_file():
        raise HTTPException(status_code=404, detail="Profile image not found.")
    return FileResponse(filepath, media_type=media_type, headers={"Cache-Control": "private, max-age=300"})


@router.get("/activity", response_model=MyActivityResponse)
async def get_my_activity(
    pharmacy_id: Optional[int] = Query(default=None, ge=1),
    period: str = Query(default="day", pattern="^(day|week|month|all)$"),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Return this user's sales/expenses/restock summary for the given period."""
    user_id = ctx["user_id"]
    # Use the pharmacy from the token if not overridden by query param
    effective_pharmacy_id = pharmacy_id or ctx.get("pharmacy_id")

    # Verify user is a member of the requested pharmacy
    if effective_pharmacy_id:
        member_result = await db.execute(
            select(PharmacyMember).where(
                PharmacyMember.user_id == user_id,
                PharmacyMember.pharmacy_id == effective_pharmacy_id,
                PharmacyMember.is_active.is_(True),
            )
        )
        if not member_result.scalars().first():
            raise HTTPException(status_code=403, detail="Not a member of that pharmacy.")

    # Use Cairo business-calendar boundaries for the database's naive-UTC dates.
    now = datetime.now(BUSINESS_TIMEZONE)
    if period == "day":
        start_dt = local_day_bounds_utc(now.date())[0]
    elif period == "week":
        start_dt = local_day_bounds_utc(now.date() - timedelta(days=now.weekday()))[0]
    elif period == "month":
        start_dt = local_day_bounds_utc(now.date().replace(day=1))[0]
    else:
        start_dt = None  # all time

    # Completed actions belong to their confirmer; creator is only a legacy fallback.
    filters = [func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == user_id]
    if effective_pharmacy_id:
        filters.append(LedgerEntry.pharmacy_id == effective_pharmacy_id)
    if start_dt:
        filters.append(LedgerEntry.created_at >= start_dt)

    # Counts and sums are computed by the database, so the "all" period costs the same however
    # many entries exist; only the 30 newest rows are loaded for the list.
    totals_result = await db.execute(
        select(
            LedgerEntry.entry_type,
            func.count(LedgerEntry.id),
            func.coalesce(func.sum(LedgerEntry.total_amount), 0.0),
        )
        .where(*filters, LedgerEntry.entry_type.in_(["log_sale", "log_expense", "log_restock"]))
        .group_by(LedgerEntry.entry_type)
    )
    counts = {"log_sale": 0, "log_expense": 0, "log_restock": 0}
    amounts = {"log_sale": 0.0, "log_expense": 0.0, "log_restock": 0.0}
    for kind, count, amount in totals_result.all():
        counts[kind] = int(count or 0)
        amounts[kind] = float(amount or 0)

    # Count sold and restocked units from the same actor-scoped entries.
    item_quantities = {"log_sale": 0.0, "log_restock": 0.0}
    if counts["log_sale"] or counts["log_restock"]:
        # Same filters as the entry list, not an id list: a long "all" period would
        # exceed the driver's bind-parameter limit (32,767 on asyncpg).
        items_result = await db.execute(
            select(LedgerEntry.entry_type, func.sum(LedgerEntryItem.quantity))
            .join(LedgerEntryItem, LedgerEntryItem.entry_id == LedgerEntry.id)
            .where(*filters, LedgerEntry.entry_type.in_(["log_sale", "log_restock"]))
            .group_by(LedgerEntry.entry_type)
        )
        item_quantities.update({kind: float(quantity or 0) for kind, quantity in items_result.all()})

    total_sales = amounts["log_sale"]
    total_expenses = amounts["log_expense"]

    recent_result = await db.execute(
        select(LedgerEntry)
        .where(*filters)
        .order_by(LedgerEntry.created_at.desc(), LedgerEntry.id.desc())
        .limit(30)
    )
    recent_entries = []
    for e in recent_result.scalars().all():
        recent_entries.append({
            "id": e.id,
            "entry_type": e.entry_type,
            "total_amount": e.total_amount,
            "payment_method": e.payment_method,
            "notes": e.notes,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })

    return {
        "period": period,
        "pharmacy_id": effective_pharmacy_id,
        "sales_count": counts["log_sale"],
        "expenses_count": counts["log_expense"],
        "restocks_count": counts["log_restock"],
        "total_restock": round(amounts["log_restock"], 2),
        "total_sales": round(total_sales, 2),
        "total_expenses": round(total_expenses, 2),
        "items_sold": item_quantities["log_sale"],
        "items_restocked": item_quantities["log_restock"],
        "net": round(total_sales - total_expenses, 2),
        "recent_entries": recent_entries,
    }