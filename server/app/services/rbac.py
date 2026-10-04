# server/app/services/rbac.py
"""Resolve signed account and pharmacy tokens against live records."""

import json
from datetime import timezone

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from server.app.db.models import PharmacyMember, RevokedAccessToken, User, has_permission
from server.app.db.session import get_db
from server.app.services.security import AI_TOKEN_AUDIENCE, decode_access_token


async def _identity_from_header(
    authorization: str | None,
    db: AsyncSession,
    allow_ai_token: bool,
) -> dict:
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required.")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="Invalid authorization header.")

    identity = decode_access_token(token.strip())
    # Tokens made for the external AI flow work only on the /ai sub-app. Every other
    # route (including sign-in, pharmacy switching and staff) refuses them here.
    if identity.get("audience") == AI_TOKEN_AUDIENCE and not allow_ai_token:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    revoked_result = await db.execute(
        select(RevokedAccessToken).where(RevokedAccessToken.token_id == identity["token_id"])
    )
    if revoked_result.scalars().first():
        raise HTTPException(status_code=401, detail="This session has been signed out.")
    user_result = await db.execute(
        select(User).where(User.id == identity["user_id"], User.is_active.is_(True))
    )
    user = user_result.scalars().first()
    if not user:
        raise HTTPException(status_code=401, detail="User account is inactive or no longer exists.")
    if user.tokens_valid_after is not None:
        # A PIN change signs out every token issued before it (milliseconds, naive UTC).
        cutoff_ms = int(user.tokens_valid_after.replace(tzinfo=timezone.utc).timestamp() * 1000)
        if identity["issued_at_ms"] < cutoff_ms:
            raise HTTPException(status_code=401, detail="This session has been signed out.")

    pharmacy_id = identity["pharmacy_id"]
    membership = None
    if pharmacy_id is not None:
        member_result = await db.execute(
            select(PharmacyMember).options(selectinload(PharmacyMember.custom_role)).where(
                PharmacyMember.user_id == user.id,
                PharmacyMember.pharmacy_id == pharmacy_id,
                PharmacyMember.is_active.is_(True),
            )
        )
        membership = member_result.scalars().first()
        if not membership:
            raise HTTPException(status_code=401, detail="Pharmacy access is inactive or no longer exists.")
        if membership.custom_role_id and (not membership.custom_role or not membership.custom_role.is_active):
            raise HTTPException(status_code=403, detail="The assigned pharmacy role is no longer active.")

    custom_scopes = None
    custom_role_name = None
    if membership and membership.custom_role:
        try:
            parsed = json.loads(membership.custom_role.scopes_json)
            custom_scopes = parsed if isinstance(parsed, list) else []
        except (TypeError, ValueError):
            custom_scopes = []
        custom_role_name = membership.custom_role.name

    return {
        "user_id": user.id,
        "pharmacy_id": membership.pharmacy_id if membership else None,
        "role": ("custom" if membership.custom_role_id else membership.role) if membership else None,
        "role_name": custom_role_name or (membership.role if membership else None),
        "scopes": custom_scopes,
        "user_name": user.name,
        "token_id": identity["token_id"],
        "token_expires_at": identity["token_expires_at"],
        "audience": identity.get("audience"),
    }


async def get_current_identity(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await _identity_from_header(authorization, db, allow_ai_token=False)


async def get_current_identity_allow_ai(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Used only by the /ai sub-app (through its dependency_overrides)."""
    return await _identity_from_header(authorization, db, allow_ai_token=True)


async def get_current_user(ctx: dict = Depends(get_current_identity)) -> dict:
    """Require a selected, active pharmacy for tenant-scoped operations."""
    if ctx["pharmacy_id"] is None:
        raise HTTPException(status_code=409, detail="Select a pharmacy before using this operation.")
    return ctx


def require_permission(permission: str):
    """FastAPI dependency factory enforcing permissions from the current membership."""
    async def _checker(ctx: dict = Depends(get_current_user)) -> dict:
        if not has_permission(ctx["role"], permission, ctx.get("scopes")):
            raise HTTPException(
                status_code=403,
                detail=f"Current role ({ctx['role']}) cannot perform this operation ({permission}).",
            )
        return ctx
    return _checker