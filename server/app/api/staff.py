# server/app/api/staff.py
"""Pharmacy roles, invitations, schedules and staff-owned activity."""

import hashlib
import json
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from server.app.db.models import (
    AuditLog, LedgerEntry, LedgerEntryItem, PharmacyInvitation, PharmacyMember,
    PharmacyProfile, PharmacyRole, StaffCompensation, StaffShift, ROLE_PERMISSIONS, has_permission,
)
from server.app.db.session import get_db
from server.app.services.rbac import get_current_identity, get_current_user
from server.app.services.clock import utc_now_naive
from server.app.services.financials import local_day_bounds_utc
from server.app.services.security import create_access_token

router = APIRouter(tags=["Pharmacy Staff"])
CUSTOM_SCOPES = set().union(*ROLE_PERMISSIONS.values()) - {"manage_roles", "manage_schedule", "manage_compensation"}
FIXED_INVITE_ROLES = {"pharmacist", "cashier", "viewer"}
DEFAULT_PHARMACY_TIMEZONE = ZoneInfo("Africa/Cairo")


def _require_current_pharmacy(ctx: dict, pharmacy_id: int) -> None:
    if ctx["pharmacy_id"] != pharmacy_id:
        raise HTTPException(status_code=404, detail="Pharmacy not found in the selected workspace.")


def _require_owner(ctx: dict, pharmacy_id: int) -> None:
    _require_current_pharmacy(ctx, pharmacy_id)
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the pharmacy owner can manage custom roles and compensation.")


def _require_staff_manager(ctx: dict, pharmacy_id: int) -> None:
    _require_current_pharmacy(ctx, pharmacy_id)
    if not has_permission(ctx["role"], "manage_staff", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="You cannot manage pharmacy invitations.")


def _held_scopes(role: str | None, scopes: list[str] | None) -> set[str]:
    """Scopes a member holds: a custom role's own list, or a built-in role's matrix."""
    held = set(scopes) if scopes is not None else set(ROLE_PERMISSIONS.get(role or "", set()))
    if "manage_inventory" in held:
        held.add("view_inventory")
    return held


def _require_can_grant_scopes(ctx: dict, needed: set[str]) -> None:
    """Nobody can hand out a scope they do not hold themselves (the owner holds all)."""
    if ctx["role"] == "owner":
        return
    if not set(needed) <= _held_scopes(ctx["role"], ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="You can only grant a role whose permissions you already hold.")


def _require_can_grant(ctx: dict, role: str) -> None:
    """A non-owner staff manager may only hand out a built-in role whose permissions they already hold."""
    _require_can_grant_scopes(ctx, ROLE_PERMISSIONS.get(role, set()))


def _member_scopes(member: PharmacyMember) -> set[str]:
    if member.role == "owner":
        return set(ROLE_PERMISSIONS["owner"])
    if member.custom_role_id and member.custom_role:
        return _held_scopes("custom", _role_dict(member.custom_role)["scopes"])
    return _held_scopes(member.role, None)


def _require_can_manage_member(ctx: dict, member: PharmacyMember) -> None:
    """A delegate may change or remove only members whose scopes are a subset of their own."""
    if ctx["role"] == "owner":
        return
    if not _member_scopes(member) <= _held_scopes(ctx["role"], ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="You can only change members whose permissions you already hold.")


def _role_dict(role: PharmacyRole, assigned_count: int = 0) -> dict:
    try:
        scopes = json.loads(role.scopes_json)
    except (TypeError, ValueError):
        scopes = []
    return {
        "id": role.id,
        "name": role.name,
        "scopes": scopes if isinstance(scopes, list) else [],
        "is_active": role.is_active,
        "assigned_count": assigned_count,
    }


def _audit(db: AsyncSession, ctx: dict, action: str, entity: str, entity_id: str, details: dict | None = None) -> None:
    # user_role is only the word "custom" for a custom role, so keep the role's own name in the details.
    if ctx.get("role_name"):
        details = {**(details or {}), "role_name": ctx["role_name"]}
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"], action_type=action, entity_type=entity,
        entity_id=entity_id, user_id=ctx["user_id"], user_name=ctx.get("user_name"),
        # AuditLog.user_role is String(20); a custom role's display name can be 60 characters.
        user_role=ctx.get("role"),
        details_json=json.dumps(details, ensure_ascii=False) if details else None,
        timestamp=utc_now_naive(),
    ))


class RoleCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=60)
    scopes: list[str] = Field(max_length=30)

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, scopes: list[str]) -> list[str]:
        if len(set(scopes)) != len(scopes):
            raise ValueError("Duplicate scopes are not allowed.")
        invalid = set(scopes) - CUSTOM_SCOPES
        if invalid:
            raise ValueError("One or more requested scopes cannot be assigned to a custom role.")
        return scopes


class RoleAssignment(BaseModel):
    custom_role_id: int = Field(gt=0)


class FixedRoleAssignment(BaseModel):
    role: Literal["pharmacist", "cashier", "viewer"]


class InvitationCreate(BaseModel):
    fixed_role: Optional[Literal["pharmacist", "cashier", "viewer"]] = None
    custom_role_id: Optional[int] = Field(default=None, gt=0)
    expires_in_days: int = Field(default=7, ge=1, le=30)
    max_uses: int = Field(default=1, ge=1, le=50)

    @model_validator(mode="after")
    def require_one_role(self):
        if (self.fixed_role is None) == (self.custom_role_id is None):
            raise ValueError("Choose exactly one built-in role or custom role.")
        return self


class ShiftInput(BaseModel):
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end_time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    timezone: str = Field(min_length=1, max_length=64)
    effective_from: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    effective_until: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("effective_from", "effective_until")
    @classmethod
    def validate_shift_date(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value

    @model_validator(mode="after")
    def validate_shift(self):
        if time.fromisoformat(self.start_time) >= time.fromisoformat(self.end_time):
            raise ValueError("Shift end must be later than shift start on the same day.")
        try:
            ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Use a valid IANA timezone name.") from exc
        if self.effective_from and self.effective_until and self.effective_until < self.effective_from:
            raise ValueError("Schedule end date cannot precede its start date.")
        return self


class ScheduleReplace(BaseModel):
    shifts: list[ShiftInput] = Field(max_length=21)

    @model_validator(mode="after")
    def reject_overlaps(self):
        timezones = {shift.timezone for shift in self.shifts}
        if len(timezones) > 1:
            raise ValueError("All shifts in one pharmacy schedule must use the same timezone.")

        by_day: dict[int, list[ShiftInput]] = {}
        for shift in self.shifts:
            by_day.setdefault(shift.day_of_week, []).append(shift)
        for shifts in by_day.values():
            for index, current in enumerate(shifts):
                current_start = time.fromisoformat(current.start_time)
                current_end = time.fromisoformat(current.end_time)
                current_from = date.fromisoformat(current.effective_from) if current.effective_from else date.min
                current_until = date.fromisoformat(current.effective_until) if current.effective_until else date.max
                for previous in shifts[:index]:
                    previous_start = time.fromisoformat(previous.start_time)
                    previous_end = time.fromisoformat(previous.end_time)
                    previous_from = date.fromisoformat(previous.effective_from) if previous.effective_from else date.min
                    previous_until = date.fromisoformat(previous.effective_until) if previous.effective_until else date.max
                    dates_overlap = current_from <= previous_until and previous_from <= current_until
                    times_overlap = current_start < previous_end and previous_start < current_end
                    if dates_overlap and times_overlap:
                        raise ValueError("Shifts on the same weekday cannot overlap during the same effective dates.")
        return self


class CompensationInput(BaseModel):
    pay_type: Literal["monthly", "hourly", "daily", "commission", "other"]
    amount: Optional[Decimal] = Field(default=None, ge=0, le=Decimal("999999999.99"))
    # The product currently supports EGP only; accepting another currency would
    # mislabel pharmacy summaries because no exchange-rate conversion exists.
    currency: Literal["EGP"] = "EGP"
    details: Optional[str] = Field(default=None, max_length=1000)
    effective_from: Optional[str] = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")

    @field_validator("effective_from")
    @classmethod
    def validate_effective_from(cls, value: Optional[str]) -> Optional[str]:
        if value:
            date.fromisoformat(value)
        return value


class PharmacyRoleResponse(BaseModel):
    id: int
    name: str
    scopes: list[str]
    is_active: bool
    assigned_count: int = 0


class RolesListResponse(BaseModel):
    available_scopes: list[str]
    roles: list[PharmacyRoleResponse]


class RoleOverviewItem(BaseModel):
    key: str
    name: str
    kind: Literal["built_in", "custom"]
    custom_role_id: Optional[int] = None
    scopes: list[str]
    assigned_count: int = 0
    # True when the caller may hand this role out (the owner may hand out any role but owner).
    grantable: bool


class RolesOverviewResponse(BaseModel):
    all_scopes: list[str]
    roles: list[RoleOverviewItem]


class RoleMutationResponse(BaseModel):
    success: bool
    role: PharmacyRoleResponse


class RoleAssignmentResponse(BaseModel):
    success: bool
    user_id: int
    role: str
    role_name: str


class StaffRemovalResponse(BaseModel):
    success: bool
    user_id: int


class InvitationCreatedResponse(BaseModel):
    success: bool
    invitation_id: int
    token: str
    join_path: str
    expires_at: str
    max_uses: int


class InvitationResponse(BaseModel):
    id: int
    role: str
    role_name: str
    expires_at: str
    max_uses: int
    used_count: int
    is_active: bool
    created_at: Optional[str]


class InvitationRevokedResponse(BaseModel):
    success: bool


class AcceptedInvitationPharmacyResponse(BaseModel):
    id: int
    pharmacy_name: str
    address: Optional[str]
    currency: str
    language: str


class AcceptedInvitationResponse(BaseModel):
    success: bool
    scope: Literal["pharmacy"]
    token: str
    pharmacy_id: int
    role: str
    role_name: str
    pharmacy: Optional[AcceptedInvitationPharmacyResponse]


class PersonalAuditEntryResponse(BaseModel):
    id: int
    pharmacy_id: Optional[int]
    pharmacy_name: Optional[str]
    action_type: str
    entity_type: str
    entity_id: str
    details: dict[str, Any]
    timestamp: Optional[str]


class WorkSummaryResponse(BaseModel):
    period_days: int
    from_: str = Field(alias="from")
    through: str
    sales_count: int
    sales_amount: float
    sold_quantity: float
    expenses_count: int
    expenses_amount: float
    restock_count: int
    restock_amount: float
    restocked_quantity: float

    model_config = ConfigDict(populate_by_name=True)


class StaffShiftResponse(BaseModel):
    id: int
    day_of_week: int
    start_time: str
    end_time: str
    timezone: str
    effective_from: Optional[str]
    effective_until: Optional[str]
    is_active: bool


class ScheduleReplaceResponse(BaseModel):
    success: bool
    shift_count: int


class StaffCompensationResponse(BaseModel):
    id: int
    pay_type: str
    amount: Optional[float]
    currency: str
    details: Optional[str]
    effective_from: Optional[str]
    effective_until: Optional[str]
    is_active: bool


class CompensationCreatedResponse(BaseModel):
    success: bool
    id: int


async def _staff_member(db: AsyncSession, pharmacy_id: int, user_id: int) -> PharmacyMember:
    result = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.user), selectinload(PharmacyMember.custom_role))
        .where(
            PharmacyMember.pharmacy_id == pharmacy_id,
            PharmacyMember.user_id == user_id,
            PharmacyMember.is_active.is_(True),
        )
    )
    member = result.scalars().first()
    if not member or not member.user:
        raise HTTPException(status_code=404, detail="Active staff member not found.")
    return member


@router.get("/api/pharmacies/{pharmacy_id}/roles", response_model=RolesListResponse)
async def list_roles(pharmacy_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    result = await db.execute(
        select(PharmacyRole).where(PharmacyRole.pharmacy_id == pharmacy_id, PharmacyRole.is_active.is_(True)).order_by(PharmacyRole.name)
    )
    roles = result.scalars().all()
    # One grouped count for every role instead of one query per role.
    counts = dict((await db.execute(
        select(PharmacyMember.custom_role_id, func.count(PharmacyMember.id))
        .where(
            PharmacyMember.pharmacy_id == pharmacy_id,
            PharmacyMember.custom_role_id.is_not(None),
            PharmacyMember.is_active.is_(True),
        )
        .group_by(PharmacyMember.custom_role_id)
    )).all())
    output = [_role_dict(role, int(counts.get(role.id, 0))) for role in roles]
    return {"available_scopes": sorted(CUSTOM_SCOPES), "roles": output}


@router.get("/api/pharmacies/{pharmacy_id}/roles/overview", response_model=RolesOverviewResponse)
async def roles_overview(pharmacy_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    """Read-only who-can-do-what list for staff managers: built-in roles and active custom roles with
    their scopes, how many active members hold each, and whether the caller may hand each one out.
    Counts only, never names or ids of members. `GET .../roles` stays owner-only."""
    _require_staff_manager(ctx, pharmacy_id)
    held = _held_scopes(ctx["role"], ctx.get("scopes"))
    is_owner = ctx["role"] == "owner"
    counts = await db.execute(
        select(PharmacyMember.role, PharmacyMember.custom_role_id, func.count(PharmacyMember.id))
        .where(PharmacyMember.pharmacy_id == pharmacy_id, PharmacyMember.is_active.is_(True))
        .group_by(PharmacyMember.role, PharmacyMember.custom_role_id)
    )
    built_in_counts: dict[str, int] = {}
    custom_counts: dict[int, int] = {}
    for member_role, custom_role_id, number in counts.all():
        if custom_role_id is not None:
            custom_counts[custom_role_id] = custom_counts.get(custom_role_id, 0) + int(number)
        else:
            built_in_counts[member_role] = built_in_counts.get(member_role, 0) + int(number)
    roles: list[dict] = []
    for name in ("owner", "pharmacist", "cashier", "viewer"):
        scopes = _held_scopes(name, None)
        roles.append({
            "key": name, "name": name, "kind": "built_in", "custom_role_id": None,
            "scopes": sorted(scopes), "assigned_count": built_in_counts.get(name, 0),
            "grantable": name != "owner" and (is_owner or scopes <= held),
        })
    result = await db.execute(
        select(PharmacyRole).where(PharmacyRole.pharmacy_id == pharmacy_id, PharmacyRole.is_active.is_(True)).order_by(PharmacyRole.name)
    )
    for role in result.scalars().all():
        scopes = _held_scopes("custom", _role_dict(role)["scopes"])
        roles.append({
            "key": f"custom:{role.id}", "name": role.name, "kind": "custom", "custom_role_id": role.id,
            "scopes": sorted(scopes), "assigned_count": custom_counts.get(role.id, 0),
            "grantable": is_owner or scopes <= held,
        })
    return {"all_scopes": sorted(set().union(*ROLE_PERMISSIONS.values())), "roles": roles}


@router.post("/api/pharmacies/{pharmacy_id}/roles", response_model=RoleMutationResponse)
async def create_role(pharmacy_id: int, req: RoleCreate, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    if req.name.casefold() in {"owner", "مالك", "المالك"}:
        raise HTTPException(status_code=422, detail="The protected owner role cannot be created as a custom role.")
    role = PharmacyRole(
        pharmacy_id=pharmacy_id, name=req.name, scopes_json=json.dumps(sorted(req.scopes)), created_by=ctx["user_id"]
    )
    db.add(role)
    try:
        await db.flush()
        _audit(db, ctx, "CREATE_PHARMACY_ROLE", "pharmacy_role", str(role.id), {"name": role.name, "scopes": sorted(req.scopes)})
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A role with this name already exists in the pharmacy.") from exc
    await db.refresh(role)
    return {"success": True, "role": _role_dict(role)}


@router.put("/api/pharmacies/{pharmacy_id}/roles/{role_id}", response_model=RoleMutationResponse)
async def update_role(pharmacy_id: int, role_id: int, req: RoleCreate, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    result = await db.execute(select(PharmacyRole).where(PharmacyRole.id == role_id, PharmacyRole.pharmacy_id == pharmacy_id, PharmacyRole.is_active.is_(True)))
    role = result.scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    if req.name.casefold() in {"owner", "مالك", "المالك"}:
        raise HTTPException(status_code=422, detail="The protected owner role cannot be renamed.")
    role.name = req.name
    role.scopes_json = json.dumps(sorted(req.scopes))
    _audit(db, ctx, "UPDATE_PHARMACY_ROLE", "pharmacy_role", str(role.id), {"name": role.name, "scopes": sorted(req.scopes)})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A role with this name already exists in the pharmacy.") from exc
    await db.refresh(role)
    return {"success": True, "role": _role_dict(role)}


@router.delete("/api/pharmacies/{pharmacy_id}/roles/{role_id}", response_model=InvitationRevokedResponse)
async def deactivate_role(pharmacy_id: int, role_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    result = await db.execute(select(PharmacyRole).where(PharmacyRole.id == role_id, PharmacyRole.pharmacy_id == pharmacy_id, PharmacyRole.is_active.is_(True)))
    role = result.scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
    assigned = await db.execute(select(func.count(PharmacyMember.id)).where(PharmacyMember.custom_role_id == role_id, PharmacyMember.is_active.is_(True)))
    if assigned.scalar_one():
        raise HTTPException(status_code=409, detail="Reassign active staff before removing this role.")
    role.is_active = False
    _audit(db, ctx, "DEACTIVATE_PHARMACY_ROLE", "pharmacy_role", str(role.id), {"name": role.name})
    await db.commit()
    return {"success": True}


@router.put("/api/pharmacies/{pharmacy_id}/staff/{user_id}/role", response_model=RoleAssignmentResponse)
async def assign_custom_role(pharmacy_id: int, user_id: int, req: RoleAssignment, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_staff_manager(ctx, pharmacy_id)
    if ctx["role"] != "owner" and user_id == ctx["user_id"]:
        raise HTTPException(status_code=403, detail="You cannot change your own role.")
    member = await _staff_member(db, pharmacy_id, user_id)
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="The protected owner membership cannot be reassigned.")
    _require_can_manage_member(ctx, member)
    result = await db.execute(select(PharmacyRole).where(
        PharmacyRole.id == req.custom_role_id,
        PharmacyRole.pharmacy_id == pharmacy_id,
        PharmacyRole.is_active.is_(True),
    ))
    role = result.scalars().first()
    if not role:
        raise HTTPException(status_code=404, detail="Active custom role not found in this pharmacy.")
    _require_can_grant_scopes(ctx, set(_role_dict(role)["scopes"]))
    old_role = member.custom_role.name if member.custom_role else member.role
    member.role = "custom"
    member.custom_role_id = role.id
    _audit(db, ctx, "ASSIGN_PHARMACY_ROLE", "staff_member", str(user_id), {"old_role": old_role, "new_role": role.name})
    await db.commit()
    return {"success": True, "user_id": user_id, "role": "custom", "role_name": role.name}


@router.patch("/api/pharmacies/{pharmacy_id}/staff/{user_id}/role", response_model=RoleAssignmentResponse)
async def assign_fixed_role(pharmacy_id: int, user_id: int, req: FixedRoleAssignment, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_staff_manager(ctx, pharmacy_id)
    if ctx["role"] != "owner" and user_id == ctx["user_id"]:
        raise HTTPException(status_code=403, detail="You cannot change your own role.")
    _require_can_grant(ctx, req.role)
    member = await _staff_member(db, pharmacy_id, user_id)
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="The protected owner membership cannot be reassigned.")
    _require_can_manage_member(ctx, member)
    old_role = member.custom_role.name if member.custom_role else member.role
    member.role = req.role
    member.custom_role_id = None
    _audit(db, ctx, "ASSIGN_FIXED_PHARMACY_ROLE", "staff_member", str(user_id), {"old_role": old_role, "new_role": req.role})
    await db.commit()
    return {"success": True, "user_id": user_id, "role": req.role, "role_name": req.role}


@router.delete("/api/pharmacies/{pharmacy_id}/staff/{user_id}", response_model=StaffRemovalResponse)
async def deactivate_staff_member(pharmacy_id: int, user_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_staff_manager(ctx, pharmacy_id)
    if ctx["role"] != "owner" and user_id == ctx["user_id"]:
        raise HTTPException(status_code=403, detail="You cannot remove your own membership.")
    member = await _staff_member(db, pharmacy_id, user_id)
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="The protected owner membership cannot be removed.")
    _require_can_manage_member(ctx, member)
    member.is_active = False
    _audit(db, ctx, "DEACTIVATE_STAFF_MEMBERSHIP", "staff_member", str(user_id), {"previous_role": member.custom_role.name if member.custom_role else member.role})
    await db.commit()
    return {"success": True, "user_id": user_id}


@router.post("/api/pharmacies/{pharmacy_id}/invitations", response_model=InvitationCreatedResponse)
async def create_invitation(pharmacy_id: int, req: InvitationCreate, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_staff_manager(ctx, pharmacy_id)
    if req.fixed_role is not None:
        _require_can_grant(ctx, req.fixed_role)
    if req.custom_role_id is not None:
        result = await db.execute(select(PharmacyRole).where(
            PharmacyRole.id == req.custom_role_id,
            PharmacyRole.pharmacy_id == pharmacy_id,
            PharmacyRole.is_active.is_(True),
        ))
        invite_role = result.scalars().first()
        if not invite_role:
            raise HTTPException(status_code=404, detail="Active custom role not found in this pharmacy.")
        _require_can_grant_scopes(ctx, set(_role_dict(invite_role)["scopes"]))
    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
    invitation = PharmacyInvitation(
        pharmacy_id=pharmacy_id,
        token_hash=token_hash,
        fixed_role=req.fixed_role,
        custom_role_id=req.custom_role_id,
        expires_at=utc_now_naive() + timedelta(days=req.expires_in_days),
        max_uses=req.max_uses,
        created_by=ctx["user_id"],
    )
    db.add(invitation)
    await db.flush()
    _audit(db, ctx, "CREATE_PHARMACY_INVITATION", "pharmacy_invitation", str(invitation.id), {"expires_at": invitation.expires_at.isoformat(), "max_uses": invitation.max_uses})
    await db.commit()
    return {
        "success": True,
        "invitation_id": invitation.id,
        "token": raw_token,
        # The token sits in the #fragment: browsers never send it to the server, so tunnels
        # and proxies cannot log it. The web client also still reads the old ?invite= form.
        "join_path": f"/onboarding#invite={raw_token}",
        "expires_at": invitation.expires_at.isoformat() + "Z",
        "max_uses": invitation.max_uses,
    }


@router.get("/api/pharmacies/{pharmacy_id}/invitations", response_model=list[InvitationResponse])
async def list_invitations(
    pharmacy_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    _require_staff_manager(ctx, pharmacy_id)
    result = await db.execute(
        select(PharmacyInvitation)
        .options(selectinload(PharmacyInvitation.custom_role))
        .where(PharmacyInvitation.pharmacy_id == pharmacy_id)
        .order_by(PharmacyInvitation.created_at.desc(), PharmacyInvitation.id.desc())
        .limit(limit)
    )
    now = utc_now_naive()
    return [{
        "id": item.id,
        "role": item.fixed_role or "custom",
        "role_name": item.custom_role.name if item.custom_role else item.fixed_role,
        "expires_at": item.expires_at.isoformat() + "Z",
        "max_uses": item.max_uses,
        "used_count": item.used_count,
        "is_active": item.is_active and item.expires_at > now and item.used_count < item.max_uses,
        "created_at": item.created_at.isoformat() + "Z" if item.created_at else None,
    } for item in result.scalars().all()]


@router.delete("/api/pharmacies/{pharmacy_id}/invitations/{invitation_id}", response_model=InvitationRevokedResponse)
async def revoke_invitation(pharmacy_id: int, invitation_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_staff_manager(ctx, pharmacy_id)
    result = await db.execute(
        select(PharmacyInvitation)
        .options(selectinload(PharmacyInvitation.custom_role))
        .where(
            PharmacyInvitation.id == invitation_id,
            PharmacyInvitation.pharmacy_id == pharmacy_id,
        )
    )
    invitation = result.scalars().first()
    if not invitation:
        raise HTTPException(status_code=404, detail="Invitation not found.")
    # Same rule as creating one: a delegate revokes only invitations for roles within its own scopes.
    if invitation.fixed_role:
        _require_can_grant(ctx, invitation.fixed_role)
    elif invitation.custom_role:
        _require_can_grant_scopes(ctx, set(_role_dict(invitation.custom_role)["scopes"]))
    invitation.is_active = False
    _audit(db, ctx, "REVOKE_PHARMACY_INVITATION", "pharmacy_invitation", str(invitation.id))
    await db.commit()
    return {"success": True}


class AcceptInvitation(BaseModel):
    token: str = Field(min_length=32, max_length=128)


@router.post("/api/pharmacies/invitations/accept", response_model=AcceptedInvitationResponse)
async def accept_invitation(req: AcceptInvitation, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_identity)):
    if ctx["pharmacy_id"] is not None:
        raise HTTPException(status_code=409, detail="Return to the pharmacy hub before accepting an invitation.")
    token_hash = hashlib.sha256(req.token.encode("utf-8")).hexdigest()
    result = await db.execute(
        select(PharmacyInvitation)
        .options(selectinload(PharmacyInvitation.custom_role))
        .where(PharmacyInvitation.token_hash == token_hash)
        .with_for_update()
    )
    invitation = result.scalars().first()
    now = utc_now_naive()
    if not invitation or not invitation.is_active or invitation.expires_at <= now or invitation.used_count >= invitation.max_uses:
        raise HTTPException(status_code=404, detail="Invitation is invalid, expired, or already used.")
    if invitation.custom_role_id and (not invitation.custom_role or not invitation.custom_role.is_active or invitation.custom_role.pharmacy_id != invitation.pharmacy_id):
        raise HTTPException(status_code=409, detail="The invitation role is no longer available.")
    existing = await db.execute(select(PharmacyMember).where(
        PharmacyMember.user_id == ctx["user_id"],
        PharmacyMember.pharmacy_id == invitation.pharmacy_id,
    ).with_for_update())
    member = existing.scalars().first()
    if member and member.is_active:
        raise HTTPException(status_code=409, detail="This account already has a membership in that pharmacy.")
    consumed = await db.execute(
        update(PharmacyInvitation)
        .where(
            PharmacyInvitation.id == invitation.id,
            PharmacyInvitation.is_active.is_(True),
            PharmacyInvitation.expires_at > now,
            PharmacyInvitation.used_count < PharmacyInvitation.max_uses,
        )
        .values(
            used_count=PharmacyInvitation.used_count + 1,
            is_active=(PharmacyInvitation.used_count + 1) < PharmacyInvitation.max_uses,
        )
    )
    if consumed.rowcount != 1:
        await db.rollback()
        raise HTTPException(status_code=404, detail="Invitation is invalid, expired, or already used.")
    role = invitation.fixed_role or "custom"
    if member:
        # A removed employee keeps the unique membership row. A fresh, valid
        # invitation is the explicit authorization to restore access.
        member.role = role
        member.custom_role_id = invitation.custom_role_id
        member.invited_by = invitation.created_by
        member.is_active = True
        member.joined_at = now
    else:
        member = PharmacyMember(
            pharmacy_id=invitation.pharmacy_id,
            user_id=ctx["user_id"],
            role=role,
            custom_role_id=invitation.custom_role_id,
            invited_by=invitation.created_by,
        )
        db.add(member)
    _audit(db, {**ctx, "pharmacy_id": invitation.pharmacy_id}, "ACCEPT_PHARMACY_INVITATION", "staff_member", str(ctx["user_id"]), {"invitation_id": invitation.id, "role": role})
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This account already has a membership in that pharmacy.") from exc
    pharmacy_result = await db.execute(select(PharmacyProfile).where(PharmacyProfile.id == invitation.pharmacy_id))
    pharmacy = pharmacy_result.scalars().first()
    return {
        "success": True,
        "scope": "pharmacy",
        "token": create_access_token(ctx["user_id"], invitation.pharmacy_id),
        "pharmacy_id": invitation.pharmacy_id,
        "role": role,
        "role_name": invitation.custom_role.name if invitation.custom_role else role,
        "pharmacy": {
            "id": pharmacy.id,
            "pharmacy_name": pharmacy.pharmacy_name,
            "address": pharmacy.address,
            "currency": pharmacy.currency,
            "language": pharmacy.language,
        } if pharmacy else None,
    }


@router.get("/api/staff/me/activity", response_model=list[PersonalAuditEntryResponse])
async def my_activity(limit: int = Query(default=50, ge=1, le=200), db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_identity)):
    result = await db.execute(
        select(AuditLog, PharmacyProfile.pharmacy_name)
        .outerjoin(PharmacyProfile, PharmacyProfile.id == AuditLog.pharmacy_id)
        .where(AuditLog.user_id == ctx["user_id"])
        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
        .limit(limit)
    )
    output = []
    for row, pharmacy_name in result.all():
        try:
            details = json.loads(row.details_json) if row.details_json else {}
        except (TypeError, ValueError):
            details = {}
        output.append({
            "id": row.id, "pharmacy_id": row.pharmacy_id, "pharmacy_name": pharmacy_name,
            "action_type": row.action_type, "entity_type": row.entity_type,
            "entity_id": row.entity_id, "details": details,
            "timestamp": row.timestamp.isoformat() + "Z" if row.timestamp else None,
        })
    return output


async def _work_summary(db: AsyncSession, pharmacy_id: int, user_id: int, days: int) -> dict:
    # "Last N days" means whole Cairo business days with today included, like the other rollups.
    first_day = datetime.now(DEFAULT_PHARMACY_TIMEZONE).date() - timedelta(days=days - 1)
    start = local_day_bounds_utc(first_day)[0]
    filters = [
        LedgerEntry.pharmacy_id == pharmacy_id,
        func.coalesce(LedgerEntry.confirmed_by, LedgerEntry.created_by) == user_id,
        LedgerEntry.created_at >= start,
    ]
    # Counts and sums per entry type come from one grouped query; no entry rows are loaded.
    amounts = {"log_sale": 0.0, "log_expense": 0.0, "log_restock": 0.0}
    counts = {key: 0 for key in amounts}
    totals_result = await db.execute(
        select(LedgerEntry.entry_type, func.count(LedgerEntry.id), func.coalesce(func.sum(LedgerEntry.total_amount), 0))
        .where(*filters, LedgerEntry.entry_type.in_(list(amounts)))
        .group_by(LedgerEntry.entry_type)
    )
    for kind, number, total in totals_result.all():
        if kind in amounts:
            amounts[kind] = float(total or 0)
            counts[kind] = int(number)
    found = any(counts.values())
    quantities = {"log_sale": 0.0, "log_expense": 0.0, "log_restock": 0.0}
    if found:
        # Same filters as the entry list, not an id list: a busy account over 365 days
        # could exceed the driver's bind-parameter limit (32,767 on asyncpg).
        quantity_result = await db.execute(
            select(LedgerEntry.entry_type, func.coalesce(func.sum(LedgerEntryItem.quantity), 0))
            .join(LedgerEntryItem, LedgerEntryItem.entry_id == LedgerEntry.id)
            .where(*filters, LedgerEntry.entry_type.in_(list(amounts)))
            .group_by(LedgerEntry.entry_type)
        )
        quantities.update({kind: float(total or 0) for kind, total in quantity_result.all() if kind in quantities})
    return {
        "period_days": days,
        "from": start.isoformat() + "Z",
        "through": utc_now_naive().isoformat() + "Z",
        "sales_count": counts["log_sale"],
        "sales_amount": amounts["log_sale"],
        "sold_quantity": quantities["log_sale"],
        "expenses_count": counts["log_expense"],
        "expenses_amount": amounts["log_expense"],
        "restock_count": counts["log_restock"],
        "restock_amount": amounts["log_restock"],
        "restocked_quantity": quantities["log_restock"],
    }


@router.get("/api/staff/me/summary", response_model=WorkSummaryResponse)
async def my_work_summary(days: int = Query(default=7, ge=1, le=365), db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    return await _work_summary(db, ctx["pharmacy_id"], ctx["user_id"], days)


@router.get("/api/pharmacies/{pharmacy_id}/staff/{user_id}/summary", response_model=WorkSummaryResponse)
async def staff_work_summary(pharmacy_id: int, user_id: int, days: int = Query(default=7, ge=1, le=365), db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_current_pharmacy(ctx, pharmacy_id)
    if user_id != ctx["user_id"] and not has_permission(ctx["role"], "view_staff_activity", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="You cannot view another staff member's work summary.")
    await _staff_member(db, pharmacy_id, user_id)
    return await _work_summary(db, pharmacy_id, user_id, days)


@router.get("/api/pharmacies/{pharmacy_id}/staff/{user_id}/schedule", response_model=list[StaffShiftResponse])
async def staff_schedule(pharmacy_id: int, user_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_current_pharmacy(ctx, pharmacy_id)
    if user_id != ctx["user_id"] and not has_permission(ctx["role"], "manage_schedule", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="You cannot view this staff schedule.")
    await _staff_member(db, pharmacy_id, user_id)
    result = await db.execute(select(StaffShift).where(StaffShift.pharmacy_id == pharmacy_id, StaffShift.user_id == user_id).order_by(StaffShift.effective_from.desc(), StaffShift.day_of_week, StaffShift.start_time))
    return [{
        "id": row.id, "day_of_week": row.day_of_week, "start_time": row.start_time,
        "end_time": row.end_time, "timezone": row.timezone,
        "effective_from": row.effective_from, "effective_until": row.effective_until,
        "is_active": row.is_active,
    } for row in result.scalars().all()]


@router.put("/api/pharmacies/{pharmacy_id}/staff/{user_id}/schedule", response_model=ScheduleReplaceResponse)
async def replace_staff_schedule(pharmacy_id: int, user_id: int, req: ScheduleReplace, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    member = await _staff_member(db, pharmacy_id, user_id)
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="Owner availability is managed outside staff shifts.")
    schedule_timezone = ZoneInfo(req.shifts[0].timezone) if req.shifts else DEFAULT_PHARMACY_TIMEZONE
    today = datetime.now(schedule_timezone).date()
    today_label = today.isoformat()
    start_days = [date.fromisoformat(shift.effective_from) if shift.effective_from else today for shift in req.shifts]
    new_start = min(start_days, default=today)
    old_result = await db.execute(select(StaffShift).where(
        StaffShift.pharmacy_id == pharmacy_id,
        StaffShift.user_id == user_id,
        StaffShift.is_active.is_(True),
        StaffShift.effective_until.is_(None),
    ))
    for old_shift in old_result.scalars().all():
        prior_start = date.fromisoformat(old_shift.effective_from) if old_shift.effective_from else date.min
        if new_start <= prior_start:
            old_shift.is_active = False
        else:
            old_shift.effective_until = (new_start - timedelta(days=1)).isoformat()
    for shift in req.shifts:
        db.add(StaffShift(
            pharmacy_id=pharmacy_id, user_id=user_id, day_of_week=shift.day_of_week,
            start_time=shift.start_time, end_time=shift.end_time, timezone=shift.timezone,
            effective_from=shift.effective_from or today_label, effective_until=shift.effective_until,
            created_by=ctx["user_id"],
        ))
    _audit(db, ctx, "REPLACE_STAFF_SCHEDULE", "staff_member", str(user_id), {"shift_count": len(req.shifts)})
    await db.commit()
    return {"success": True, "shift_count": len(req.shifts)}


@router.get("/api/pharmacies/{pharmacy_id}/staff/{user_id}/compensation", response_model=list[StaffCompensationResponse])
async def staff_compensation(pharmacy_id: int, user_id: int, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_current_pharmacy(ctx, pharmacy_id)
    if user_id != ctx["user_id"] and ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Compensation details are private to the employee and owner.")
    await _staff_member(db, pharmacy_id, user_id)
    result = await db.execute(select(StaffCompensation).where(
        StaffCompensation.pharmacy_id == pharmacy_id, StaffCompensation.user_id == user_id,
    ).order_by(StaffCompensation.created_at.desc(), StaffCompensation.id.desc()))
    return [{
        "id": row.id, "pay_type": row.pay_type,
        "amount": float(row.amount) if row.amount is not None else None,
        "currency": row.currency, "details": row.details,
        "effective_from": row.effective_from, "effective_until": row.effective_until,
        "is_active": row.is_active,
    } for row in result.scalars().all()]


@router.post("/api/pharmacies/{pharmacy_id}/staff/{user_id}/compensation", response_model=CompensationCreatedResponse)
async def add_staff_compensation(pharmacy_id: int, user_id: int, req: CompensationInput, db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    _require_owner(ctx, pharmacy_id)
    member = await _staff_member(db, pharmacy_id, user_id)
    if member.role == "owner":
        raise HTTPException(status_code=409, detail="Owner compensation is not managed as staff payroll.")
    effective_from = req.effective_from or datetime.now(DEFAULT_PHARMACY_TIMEZONE).date().isoformat()
    previous = await db.execute(select(StaffCompensation).where(
        StaffCompensation.pharmacy_id == pharmacy_id,
        StaffCompensation.user_id == user_id,
        StaffCompensation.is_active.is_(True),
        StaffCompensation.effective_until.is_(None),
    ).order_by(StaffCompensation.created_at.desc()))
    old = previous.scalars().first()
    if old:
        end_date = date.fromisoformat(effective_from) - timedelta(days=1)
        if old.effective_from and date.fromisoformat(old.effective_from) >= date.fromisoformat(effective_from):
            old.is_active = False
        else:
            old.effective_until = end_date.isoformat()
    row = StaffCompensation(
        pharmacy_id=pharmacy_id, user_id=user_id, pay_type=req.pay_type,
        amount=req.amount, currency=req.currency.upper(), details=req.details,
        effective_from=effective_from, created_by=ctx["user_id"],
    )
    db.add(row)
    await db.flush()
    _audit(db, ctx, "SET_STAFF_COMPENSATION", "staff_compensation", str(row.id), {"user_id": user_id, "pay_type": req.pay_type, "currency": req.currency.upper(), "effective_from": effective_from})
    await db.commit()
    return {"success": True, "id": row.id}