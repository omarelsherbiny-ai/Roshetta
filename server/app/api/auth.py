# server/app/api/auth.py
import json
from datetime import date, timedelta
from typing import Optional, List, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError

from server.app.db.session import get_db
from server.app.db.models import (
    AuditLog, AuthThrottle, RevokedAccessToken, User, UserCredential, PharmacyProfile, PharmacyMember, PharmacyOwnershipSlot, ROLE_PERMISSIONS,
    has_permission,
)
from server.app.services.rbac import get_current_identity, get_current_user
from server.app.services.client_address import client_address
from server.app.services.clock import utc_from_timestamp_naive, utc_now_naive
from server.app.services.security import (
    create_access_token, hash_pin, throttle_key, validate_pin, verify_legacy_pin, verify_pin,
)

router = APIRouter(prefix="/api/auth", tags=["Auth & Staff"])
AUTH_FAILURE_LIMIT = 5
AUTH_FAILURE_WINDOW = timedelta(minutes=15)
AUTH_LOCKOUT = timedelta(minutes=15)


class UserResponse(BaseModel):
    id: int
    name: str
    phone: str
    language_pref: Optional[str]
    location: Optional[str]
    photo_url: Optional[str]
    birth_date: Optional[str]
    is_active: bool


class SimpleSuccessResponse(BaseModel):
    success: bool
    message: str


class AccountSessionResponse(BaseModel):
    scope: Literal["account"]
    token: str
    user: UserResponse


class AccountRegistrationResponse(AccountSessionResponse):
    success: bool


class AccountProfileUpdateResponse(BaseModel):
    success: bool
    user: UserResponse


class PharmacyResponse(BaseModel):
    id: int
    pharmacy_name: str
    currency: str
    numerals_format: Literal["western", "eastern"]
    low_stock_default: Optional[float]
    language: Literal["ar", "en"]
    is_initialized: bool
    owner_name: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    license_number: Optional[str] = None
    tax_id: Optional[str] = None


class PharmacyStaffResponse(BaseModel):
    id: int
    name: str
    phone: str
    role: str
    role_name: str
    custom_role_id: Optional[int]
    is_active: bool
    joined_at: Optional[str]


class OtherPharmacyResponse(BaseModel):
    id: int
    name: str
    role: str
    role_name: str


class PharmacyLoginResponse(BaseModel):
    token: str
    user: UserResponse
    role: str
    role_name: str
    permissions: List[str]
    pharmacy: PharmacyResponse
    other_pharmacies: List[OtherPharmacyResponse]


class PharmacyRegistrationResponse(BaseModel):
    success: bool
    message: str
    token: str
    user: UserResponse
    pharmacy: PharmacyResponse
    role: str
    permissions: List[str]


class PharmacySwitchResponse(BaseModel):
    success: bool
    token: str
    role: str
    role_name: str
    permissions: List[str]
    pharmacy: PharmacyResponse


class PharmacyProfileUpdateResponse(BaseModel):
    success: bool
    message: str
    profile: PharmacyResponse


@router.post("/logout", response_model=SimpleSuccessResponse)
async def logout(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Revoke this signed session immediately; other devices remain signed in."""
    now = utc_now_naive()
    await db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now))
    db.add(RevokedAccessToken(
        token_id=ctx["token_id"],
        expires_at=utc_from_timestamp_naive(ctx["token_expires_at"]),
        revoked_at=now,
    ))
    await db.commit()
    return {"success": True, "message": "Session signed out."}


@router.post("/account-scope", response_model=AccountSessionResponse)
async def return_to_account_scope(
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Revoke the selected-pharmacy session and issue an account-only hub session."""
    now = utc_now_naive()
    await db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now))
    db.add(RevokedAccessToken(
        token_id=ctx["token_id"],
        expires_at=utc_from_timestamp_naive(ctx["token_expires_at"]),
        revoked_at=now,
    ))
    if ctx.get("pharmacy_id") is not None:
        db.add(AuditLog(
            pharmacy_id=ctx["pharmacy_id"], action_type="RETURN_TO_ACCOUNT_SCOPE",
            entity_type="pharmacy", entity_id=str(ctx["pharmacy_id"]),
            user_id=ctx["user_id"], user_name=ctx.get("user_name"),
            # AuditLog.user_role is String(20); a custom role's display name can be 60 characters.
            user_role=ctx["role"], timestamp=now,
            details_json=json.dumps({"role_name": ctx.get("role_name")}),
        ))
    await db.commit()
    user_result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = user_result.scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive or no longer exists.")
    return {
        "scope": "account",
        "token": create_access_token(user.id, None),
        "user": _user_dict(user),
    }


# ── Pydantic schemas ──────────────────────────────────────────

class AuthPayload(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)


class LoginRequest(AuthPayload):
    phone:       str = Field(min_length=7, max_length=20)
    pin:         str = Field(min_length=4, max_length=6)
    pharmacy_id: Optional[int] = None   # owner can omit (first pharmacy used)


class RegisterPharmacyRequest(AuthPayload):
    owner_name:     str = Field(min_length=1, max_length=100)
    phone:          str = Field(min_length=7, max_length=20)
    pin:            str = Field(min_length=4, max_length=6)
    pharmacy_name:  str = Field(min_length=1, max_length=150)
    address:        Optional[str] = Field(default=None, max_length=255)
    license_number: Optional[str] = Field(default=None, max_length=50)
    tax_id:         Optional[str] = Field(default=None, max_length=50)


class RegisterUserRequest(AuthPayload):
    name: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=7, max_length=20)
    pin: str = Field(min_length=4, max_length=6)
    language_pref: Literal["ar", "en"] = "ar"


class UserProfileUpdate(AuthPayload):
    name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    location: Optional[str] = Field(default=None, max_length=160)
    photo_url: Optional[str] = Field(default=None, max_length=500)
    birth_date: Optional[str] = Field(default=None, pattern=r"^$|^\d{4}-\d{2}-\d{2}$")
    language_pref: Optional[Literal["ar", "en"]] = None

    @field_validator("birth_date")
    @classmethod
    def validate_birth_date(cls, value: Optional[str]) -> Optional[str]:
        if not value:
            return value
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("birth_date must be a real ISO calendar date") from exc
        if parsed > date.today():
            raise ValueError("birth_date cannot be in the future")
        return value

    @field_validator("photo_url")
    @classmethod
    def validate_photo_url(cls, value: Optional[str]) -> Optional[str]:
        if not value or not value.strip():
            return value
        if not value.strip().startswith("https://"):
            raise ValueError("photo_url must use HTTPS")
        return value.strip()


class SwitchPharmacyRequest(AuthPayload):
    pharmacy_id: int = Field(gt=0)


class PharmacyProfileUpdate(AuthPayload):
    pharmacy_name:    Optional[str]   = Field(default=None, min_length=1, max_length=150)
    owner_name:       Optional[str]   = Field(default=None, min_length=1, max_length=100)
    phone:            Optional[str]   = Field(default=None, min_length=7, max_length=20)
    address:          Optional[str]   = Field(default=None, max_length=255)
    license_number:   Optional[str]   = Field(default=None, max_length=50)
    tax_id:           Optional[str]   = Field(default=None, max_length=50)
    currency:         Literal["EGP"] = "EGP"
    numerals_format:  Optional[Literal["western", "eastern"]] = "western"
    low_stock_default:Optional[float] = Field(default=5.0, gt=0, allow_inf_nan=False)
    language:         Optional[Literal["ar", "en"]] = "ar"


# ── Helpers ───────────────────────────────────────────────────

def _pharmacy_dict(
    p: PharmacyProfile,
    include_private: bool = False,
) -> dict:
    result = {
        "id":               p.id,
        "pharmacy_name":    p.pharmacy_name,
        "currency":         p.currency,
        "numerals_format":  p.numerals_format,
        "low_stock_default":p.low_stock_default,
        "language":         p.language,
        "is_initialized":   p.is_initialized,
    }
    if include_private:
        result.update({
            "owner_name": p.owner_name,
            "phone": p.phone,
            "address": p.address,
            "license_number": p.license_number,
            "tax_id": p.tax_id,
        })
    return result

def _user_dict(u: User) -> dict:
    return {
        "id":            u.id,
        "name":          u.name,
        "phone":         u.phone,
        "language_pref": u.language_pref,
        "location": u.location,
        "photo_url": u.photo_url,
        "birth_date": u.birth_date,
        "is_active":     u.is_active,
    }


def _member_access(member: PharmacyMember) -> dict:
    if member.custom_role_id and member.custom_role:
        try:
            scopes = json.loads(member.custom_role.scopes_json)
            if not isinstance(scopes, list):
                scopes = []
        except (TypeError, ValueError):
            scopes = []
        return {"role": "custom", "role_name": member.custom_role.name, "permissions": scopes, "scopes": scopes}
    permissions = sorted(ROLE_PERMISSIONS.get(member.role, set()))
    return {"role": member.role, "role_name": member.role, "permissions": permissions, "scopes": None}

def _save_pin_credential(db: AsyncSession, user: User, pin: str) -> None:
    salt, digest = hash_pin(pin)
    user.pin = ""
    db.add(UserCredential(user_id=user.id, pin_salt=salt, pin_hash=digest))


async def _verify_user_pin(db: AsyncSession, user: User, pin: str) -> bool:
    credential_result = await db.execute(
        select(UserCredential).where(UserCredential.user_id == user.id)
    )
    credential = credential_result.scalars().first()
    if credential:
        return verify_pin(pin, credential.pin_salt, credential.pin_hash)
    if not verify_legacy_pin(pin, user.pin):
        return False
    # Existing plaintext PINs are upgraded immediately after a successful login.
    _save_pin_credential(db, user, pin)
    return True


async def _check_auth_throttle(db: AsyncSession, key: str) -> None:
    """Refuse a blocked key, then count this attempt before the PIN is checked."""
    result = await db.execute(select(AuthThrottle).where(AuthThrottle.key == key))
    record = result.scalars().first()
    now = utc_now_naive()
    if record and record.blocked_until and record.blocked_until > now:
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")
    if record and now - record.window_start >= AUTH_FAILURE_WINDOW:
        record.failures = 0
        record.window_start = now
        record.blocked_until = None
        await db.commit()
    await _reserve_auth_attempt(db, key)


async def _reserve_auth_attempt(db: AsyncSession, key: str) -> None:
    """Count one sign-in attempt BEFORE the PIN is checked, with an atomic increment.

    Counting only failures after the check let parallel guesses all pass the check first
    and overwrite each other's count (Session 107, debt item 19). Here every attempt takes
    its own number: the first AUTH_FAILURE_LIMIT are checked, the next one is refused and
    locks the key. A successful sign-in deletes the row, so the count restarts."""
    now = utc_now_naive()
    exists = await db.execute(select(AuthThrottle.key).where(AuthThrottle.key == key))
    if exists.first() is None:
        try:
            db.add(AuthThrottle(key=key, failures=0, window_start=now))
            await db.commit()
        except IntegrityError:
            await db.rollback()  # a parallel request created the row first
    # Start a fresh window when the old one ended (a no-op when it already restarted).
    await db.execute(
        update(AuthThrottle)
        .where(AuthThrottle.key == key, AuthThrottle.window_start <= now - AUTH_FAILURE_WINDOW)
        .values(failures=0, window_start=now, blocked_until=None)
        .execution_options(synchronize_session=False)
    )
    await db.execute(
        update(AuthThrottle)
        .where(AuthThrottle.key == key)
        .values(failures=AuthThrottle.failures + 1)
        .execution_options(synchronize_session=False)
    )
    counted = await db.execute(select(AuthThrottle.failures).where(AuthThrottle.key == key))
    # None: a parallel successful sign-in deleted the row between the two statements.
    attempt_number = counted.scalar() or 1
    await db.commit()
    if attempt_number > AUTH_FAILURE_LIMIT:
        await db.execute(
            update(AuthThrottle)
            .where(AuthThrottle.key == key)
            .values(blocked_until=now + AUTH_LOCKOUT)
            .execution_options(synchronize_session=False)
        )
        await db.commit()
        raise HTTPException(status_code=429, detail="Too many attempts. Try again in 15 minutes.")


async def _record_auth_failure(db: AsyncSession, key: str) -> None:
    """The attempt was already counted by _reserve_auth_attempt; lock the key when this
    failure is the last one allowed."""
    await db.execute(
        update(AuthThrottle)
        .where(AuthThrottle.key == key, AuthThrottle.failures >= AUTH_FAILURE_LIMIT)
        .values(blocked_until=utc_now_naive() + AUTH_LOCKOUT)
        .execution_options(synchronize_session=False)
    )
    await db.commit()


async def _clear_auth_failures(db: AsyncSession, key: str) -> None:
    await db.execute(delete(AuthThrottle).where(AuthThrottle.key == key))


# ── Endpoints ─────────────────────────────────────────────────

@router.post("/register-user", response_model=AccountRegistrationResponse)
async def register_user(req: RegisterUserRequest, db: AsyncSession = Depends(get_db)):
    """Create a personal account without requiring a pharmacy membership."""
    pin = validate_pin(req.pin)
    phone = req.phone.strip()
    if not phone or not req.name.strip():
        raise HTTPException(status_code=400, detail="Name and phone number are required.")
    existing = await db.execute(select(User).where(User.phone == phone))
    if existing.scalars().first():
        raise HTTPException(status_code=409, detail="This phone number already has an account. Sign in instead.")
    user = User(name=req.name.strip(), phone=phone, pin="", language_pref=req.language_pref, is_active=True)
    db.add(user)
    try:
        await db.flush()
        _save_pin_credential(db, user, pin)
        db.add(AuditLog(
            pharmacy_id=None, action_type="CREATE_USER_ACCOUNT", entity_type="user",
            entity_id=str(user.id), user_id=user.id, user_name=user.name,
            user_role="account", timestamp=utc_now_naive(),
        ))
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This phone number already has an account. Sign in instead.") from exc
    await db.refresh(user)
    return {
        "success": True,
        "scope": "account",
        "token": create_access_token(user.id, None),
        "user": _user_dict(user),
    }


@router.post("/account-login", response_model=AccountSessionResponse)
async def account_login(req: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Authenticate a person independently of any pharmacy membership."""
    phone = req.phone.strip()
    pin = validate_pin(req.pin)
    client_ip = client_address(request)
    attempt_key = throttle_key("login", phone, client_ip)
    await _check_auth_throttle(db, attempt_key)
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalars().first()
    if not user or not user.is_active or not await _verify_user_pin(db, user, pin):
        await _record_auth_failure(db, attempt_key)
        raise HTTPException(status_code=401, detail="Phone number or PIN is incorrect.")
    await _clear_auth_failures(db, attempt_key)
    await db.commit()
    return {
        "scope": "account",
        "token": create_access_token(user.id, None),
        "user": _user_dict(user),
    }


@router.get("/me", response_model=UserResponse)
async def get_personal_profile(db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_identity)):
    result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")
    return _user_dict(user)


@router.patch("/me", response_model=AccountProfileUpdateResponse)
async def update_personal_profile(
    req: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    result = await db.execute(select(User).where(User.id == ctx["user_id"]))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User account not found.")
    for field, value in req.model_dump(exclude_unset=True).items():
        nullable_fields = {"location", "photo_url", "birth_date"}
        if value is None:
            if field in nullable_fields:
                setattr(user, field, None)
            continue
        cleaned = value.strip() if isinstance(value, str) else value
        setattr(user, field, cleaned or None if field in nullable_fields else cleaned)
    db.add(AuditLog(
        pharmacy_id=None, action_type="UPDATE_USER_PROFILE", entity_type="user",
        entity_id=str(user.id), user_id=user.id, user_name=user.name,
        user_role="account", timestamp=utc_now_naive(),
    ))
    await db.commit()
    await db.refresh(user)
    return {"success": True, "user": _user_dict(user)}


class ChangePinRequest(AuthPayload):
    current_pin: str = Field(min_length=4, max_length=6)
    new_pin:     str = Field(min_length=4, max_length=6)


class ChangePinResponse(BaseModel):
    success: bool
    message: str
    token: str


@router.post("/change-pin", response_model=ChangePinResponse)
async def change_pin(
    req: ChangePinRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_identity),
):
    """Change the signed-in person's PIN. The current PIN is checked through the same
    throttle as sign-in (a wrong guess here counts against login and the other way round).
    The session used for the call is revoked and a fresh token with the same scope is
    returned. Every other session of the person is signed out too: the change sets
    User.tokens_valid_after and rbac refuses tokens issued before it. A wrong current PIN answers 403, not 401, so the web client does not mistake it for a
    dead session."""
    current_pin = validate_pin(req.current_pin)
    new_pin = validate_pin(req.new_pin)
    if new_pin == current_pin:
        raise HTTPException(status_code=422, detail="The new PIN must be different from the current PIN.")
    user = (await db.execute(select(User).where(User.id == ctx["user_id"]))).scalars().first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User account is inactive or no longer exists.")
    client_ip = client_address(request)
    attempt_key = throttle_key("login", user.phone, client_ip)
    await _check_auth_throttle(db, attempt_key)
    if not await _verify_user_pin(db, user, current_pin):
        await _record_auth_failure(db, attempt_key)
        raise HTTPException(status_code=403, detail="Current PIN is incorrect.")
    await _clear_auth_failures(db, attempt_key)
    # A legacy plaintext PIN was just upgraded by _verify_user_pin (autoflush is off):
    # flush so the credential row exists before it is replaced below.
    await db.flush()
    credential = (await db.execute(
        select(UserCredential).where(UserCredential.user_id == user.id)
    )).scalars().first()
    salt, digest = hash_pin(new_pin)
    if credential:
        credential.pin_salt = salt
        credential.pin_hash = digest
    else:
        db.add(UserCredential(user_id=user.id, pin_salt=salt, pin_hash=digest))
    user.pin = ""
    now = utc_now_naive()
    user.tokens_valid_after = now
    await db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now))
    db.add(RevokedAccessToken(
        token_id=ctx["token_id"],
        expires_at=utc_from_timestamp_naive(ctx["token_expires_at"]),
        revoked_at=now,
    ))
    # Personal account event (no pharmacy), like a profile update: it shows in the person's
    # own activity and never in a pharmacy's records. The PIN itself is never stored.
    db.add(AuditLog(
        pharmacy_id=None, action_type="CHANGE_PIN", entity_type="user",
        entity_id=str(user.id), user_id=user.id, user_name=user.name,
        user_role="account", timestamp=now,
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        # The same token was used by a parallel request: only one change may win.
        await db.rollback()
        raise HTTPException(status_code=401, detail="This session has been signed out.") from exc
    return {
        "success": True,
        "message": "PIN changed.",
        "token": create_access_token(user.id, ctx.get("pharmacy_id")),
    }


# Direct aliases mounted so /api/me also works as requested
@router.get("/user/profile", include_in_schema=False)
async def get_user_profile_alias(db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_identity)):
    return await get_personal_profile(db, ctx)


@router.post("/register-pharmacy", response_model=PharmacyRegistrationResponse)
async def register_pharmacy(req: RegisterPharmacyRequest, db: AsyncSession = Depends(get_db)):
    """
    Onboards a completely new pharmacy and creates the owner account.
    """
    pin = validate_pin(req.pin)
    phone = req.phone.strip()
    if not phone or not req.pharmacy_name.strip() or not req.owner_name.strip():
        raise HTTPException(status_code=400, detail="الاسم ورقم الهاتف واسم الصيدلية مطلوبة للتسجيل.")

    user_res = await db.execute(select(User).where(User.phone == phone))
    if user_res.scalars().first():
        raise HTTPException(status_code=409, detail="This phone number already has an account. Sign in instead.")

    user = User(name=req.owner_name.strip(), phone=phone, pin="", is_active=True)
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This phone number already has an account. Sign in instead.") from exc
    _save_pin_credential(db, user, pin)

    # 2. Create PharmacyProfile
    pharmacy = PharmacyProfile(
        pharmacy_name=req.pharmacy_name.strip(),
        owner_name=req.owner_name.strip(),
        phone=phone,
        address=req.address.strip() if req.address else None,
        license_number=req.license_number.strip() if req.license_number else None,
        tax_id=req.tax_id.strip() if req.tax_id else None,
        currency="EGP",
        numerals_format="western",
        low_stock_default=5.0,
        language="ar",
        is_initialized=True,
    )
    db.add(pharmacy)
    await db.flush()

    # New legacy registrations can only create their first pharmacy. Reserve
    # the first ownership slot so the account hub sees a consistent limit.
    db.add(PharmacyOwnershipSlot(user_id=user.id, pharmacy_id=pharmacy.id, slot_number=1))

    # 3. Create PharmacyMember as Owner
    member = PharmacyMember(
        pharmacy_id=pharmacy.id,
        user_id=user.id,
        role="owner",
        is_active=True
    )
    db.add(member)
    db.add(AuditLog(
        pharmacy_id=pharmacy.id, action_type="CREATE_PHARMACY", entity_type="pharmacy",
        entity_id=str(pharmacy.id), user_id=user.id, user_name=user.name,
        user_role="owner", details_json=json.dumps({"source": "legacy_registration"}),
        timestamp=utc_now_naive(),
    ))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="This phone number already has an account. Sign in instead.") from exc
    await db.refresh(pharmacy)

    token = create_access_token(user.id, pharmacy.id)
    return {
        "success": True,
        "message": f"تم تسجيل صيدلية '{pharmacy.pharmacy_name}' بنجاح وأنت الآن المالك.",
        "token": token,
        "user": _user_dict(user),
        "pharmacy": _pharmacy_dict(pharmacy, include_private=True),
        "role": "owner",
        "permissions": list(ROLE_PERMISSIONS.get("owner", set())),
    }


@router.post("/login", response_model=PharmacyLoginResponse, response_model_exclude_unset=True)
async def login(
    req: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Works for both owner and all staff roles.
    Returns the token + full membership context (role, permissions).
    """
    phone = req.phone.strip()
    pin = validate_pin(req.pin)
    client_ip = client_address(request)
    attempt_key = throttle_key("login", phone, client_ip)
    await _check_auth_throttle(db, attempt_key)
    result = await db.execute(select(User).where(User.phone == phone))
    user = result.scalars().first()

    if not user or not user.is_active or not await _verify_user_pin(db, user, pin):
        await _record_auth_failure(db, attempt_key)
        raise HTTPException(status_code=401, detail="Phone number or PIN is incorrect.")

    # The PIN was right: clear the failures and keep a legacy plaintext-PIN upgrade now,
    # so a later "no pharmacy" or "wrong pharmacy" answer cannot lose it (Session 107).
    await _clear_auth_failures(db, attempt_key)
    await db.commit()

    # Load memberships (all pharmacies this user belongs to)
    mem_res = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.pharmacy), selectinload(PharmacyMember.custom_role))
        .where(PharmacyMember.user_id == user.id, PharmacyMember.is_active == True)
    )
    memberships = mem_res.scalars().all()

    if not memberships:
        raise HTTPException(status_code=404,
            detail="لا توجد صيدلية مرتبطة بهذا الحساب. اقبل دعوة آمنة أو أنشئ صيدلية.")

    # Pick the requested pharmacy or default to first
    if req.pharmacy_id:
        mem = next((m for m in memberships if m.pharmacy_id == req.pharmacy_id), None)
        if not mem:
            raise HTTPException(status_code=403, detail="ليس لديك صلاحية الوصول لهذه الصيدلية.")
    else:
        mem = memberships[0]

    pharmacy = mem.pharmacy
    access = _member_access(mem)
    role = access["role"]

    return {
        "token":       create_access_token(user.id, pharmacy.id),
        "user":        _user_dict(user),
        "role":        role,
        "role_name": access["role_name"],
        "permissions": access["permissions"],
        "pharmacy":    _pharmacy_dict(
            pharmacy,
            include_private=has_permission(role, "edit_settings", access["scopes"]),
        ),
        # If user belongs to multiple pharmacies, send the list so the UI can show a switcher
        "other_pharmacies": [
            {"id": m.pharmacy_id, "name": m.pharmacy.pharmacy_name, "role": _member_access(m)["role"], "role_name": _member_access(m)["role_name"]}
            for m in memberships if m.pharmacy_id != pharmacy.id
        ],
    }


@router.post("/switch-pharmacy", response_model=PharmacySwitchResponse, response_model_exclude_unset=True)
async def switch_pharmacy(
    req: SwitchPharmacyRequest,
    db: AsyncSession = Depends(get_db),
    ctx: dict = Depends(get_current_user),
):
    """Issue a tenant-scoped token only for another active membership of this user."""
    member_result = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.pharmacy), selectinload(PharmacyMember.custom_role))
        .where(
            PharmacyMember.user_id == ctx["user_id"],
            PharmacyMember.pharmacy_id == req.pharmacy_id,
            PharmacyMember.is_active.is_(True),
        )
    )
    membership = member_result.scalars().first()
    if not membership or not membership.pharmacy:
        raise HTTPException(status_code=403, detail="ليس لديك صلاحية الوصول لهذه الصيدلية.")

    now = utc_now_naive()
    await db.execute(delete(RevokedAccessToken).where(RevokedAccessToken.expires_at <= now))
    db.add(RevokedAccessToken(
        token_id=ctx["token_id"],
        expires_at=utc_from_timestamp_naive(ctx["token_expires_at"]),
        revoked_at=now,
    ))
    try:
        await db.commit()
    except IntegrityError as exc:
        # The same token was switched by a parallel request: only one switch may win.
        await db.rollback()
        raise HTTPException(status_code=401, detail="This session has been signed out.") from exc

    pharmacy = membership.pharmacy
    access = _member_access(membership)
    return {
        "success": True,
        "token": create_access_token(ctx["user_id"], pharmacy.id),
        "role": access["role"],
        "role_name": access["role_name"],
        "permissions": access["permissions"],
        "pharmacy": _pharmacy_dict(
            pharmacy,
            include_private=has_permission(access["role"], "edit_settings", access["scopes"]),
        ),
    }


@router.post("/join", status_code=410, responses={410: {"description": "Gone"}})
async def join_pharmacy():
    """Retired reusable-code admission path."""
    raise HTTPException(
        status_code=410,
        detail="Reusable invitation codes are retired. Use a secure invitation link.",
    )


@router.post("/invite", status_code=410, responses={410: {"description": "Gone"}, 403: {"description": "Owner permission required"}})
async def invite_staff(
    db: AsyncSession  = Depends(get_db),
    ctx: dict         = Depends(get_current_user),
):
    """Retired credential-issuing staff invitation path."""
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="Only the pharmacy owner can create a staff account.")
    raise HTTPException(
        status_code=410,
        detail="Staff accounts must join using a secure invitation link.",
    )


@router.patch("/staff/{user_id}/role", status_code=410, responses={410: {"description": "Gone"}, 403: {"description": "Staff management permission required"}})
async def update_staff_role(ctx: dict = Depends(get_current_user)):
    """Retired unscoped role assignment endpoint."""
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="فقط المالك يمكنه تغيير الأدوار.")
    raise HTTPException(status_code=410, detail="Use the pharmacy-scoped staff role endpoint.")


@router.delete("/staff/{user_id}", status_code=410, responses={410: {"description": "Gone"}, 403: {"description": "Staff management permission required"}})
async def remove_staff(ctx: dict = Depends(get_current_user)):
    """Retired unscoped staff removal endpoint."""
    if not has_permission(ctx["role"], "manage_staff", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="فقط المالك يمكنه إزالة موظفين.")
    raise HTTPException(status_code=410, detail="Use the pharmacy-scoped staff removal endpoint.")


@router.get("/staff", response_model=List[PharmacyStaffResponse])
async def list_staff(
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(get_current_user),
):
    """Returns all active members of the current pharmacy."""
    if not has_permission(ctx["role"], "manage_staff", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="لا تملك صلاحية عرض قائمة الموظفين.")

    mem_res = await db.execute(
        select(PharmacyMember)
        .options(selectinload(PharmacyMember.user), selectinload(PharmacyMember.custom_role))
        .where(
            PharmacyMember.pharmacy_id == ctx["pharmacy_id"],
            PharmacyMember.is_active   == True,
        )
    )
    members = mem_res.scalars().all()
    return [
        {
            "id":       m.user_id,
            "name":     m.user.name,
            "phone":    m.user.phone,
            "role":     "custom" if m.custom_role_id else m.role,
            "role_name": m.custom_role.name if m.custom_role else m.role,
            "custom_role_id": m.custom_role_id,
            "is_active": m.user.is_active,
            "joined_at": m.joined_at.isoformat() if m.joined_at else None,
        }
        for m in members
    ]


@router.get("/profile", response_model=PharmacyResponse, response_model_exclude_unset=True)
async def get_profile(db: AsyncSession = Depends(get_db), ctx: dict = Depends(get_current_user)):
    result = await db.execute(
        select(PharmacyProfile).where(PharmacyProfile.id == ctx["pharmacy_id"])
    )
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="لم يتم العثور على ملف الصيدلية.")
    return _pharmacy_dict(
        profile,
        include_private=has_permission(ctx["role"], "edit_settings", ctx.get("scopes")),
    )


@router.post("/profile", response_model=PharmacyProfileUpdateResponse)
async def update_profile(
    req: PharmacyProfileUpdate,
    db:  AsyncSession = Depends(get_db),
    ctx: dict         = Depends(get_current_user),
):
    if not has_permission(ctx["role"], "edit_settings", ctx.get("scopes")):
        raise HTTPException(status_code=403, detail="فقط المالك يمكنه تعديل إعدادات الصيدلية.")

    result = await db.execute(
        select(PharmacyProfile).where(PharmacyProfile.id == ctx["pharmacy_id"])
    )
    profile = result.scalars().first()
    if not profile:
        raise HTTPException(status_code=404, detail="لم يتم العثور على ملف الصيدلية.")

    for field, val in req.model_dump(exclude_unset=True).items():
        if val is not None:
            setattr(profile, field, val)

    profile.is_initialized = True
    db.add(AuditLog(
        pharmacy_id=ctx["pharmacy_id"], action_type="UPDATE_PHARMACY_PROFILE",
        entity_type="pharmacy", entity_id=str(profile.id), user_id=ctx["user_id"],
        user_name=ctx.get("user_name"), user_role=ctx["role"],
        details_json=json.dumps({"updated_fields": sorted(req.model_dump(exclude_unset=True).keys()), "role_name": ctx.get("role_name")}),
        timestamp=utc_now_naive(),
    ))
    await db.commit()
    await db.refresh(profile)
    return {"success": True, "message": "تم تحديث إعدادات الصيدلية بنجاح.", "profile": _pharmacy_dict(
        profile, include_private=True
    )}


@router.post("/refresh-invite-code", status_code=410, responses={410: {"description": "Gone"}, 403: {"description": "Owner permission required"}})
async def refresh_invite_code(ctx: dict = Depends(get_current_user)):
    """Retired reusable-code regeneration path."""
    if ctx["role"] != "owner":
        raise HTTPException(status_code=403, detail="فقط المالك يمكنه تجديد كود الدعوة.")
    raise HTTPException(
        status_code=410,
        detail="Reusable invitation codes are retired. Use a secure invitation link.",
    )