from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import AuthContext, get_auth_context
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import Membership, Tenant, User
from app.schemas.auth import LoginRequest, MeResponse, SwitchTenantRequest, TokenResponse, UserInfo
from app.services.tenants import resolve_membership

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _resolve_membership(db: Session, user: User, tenant_id: uuid.UUID | None) -> tuple[Tenant | None, Membership | None]:
    memberships_stmt = (
        select(Membership)
        .options(selectinload(Membership.tenant))
        .where(Membership.user_id == user.id)
    )
    memberships = db.execute(memberships_stmt).scalars().all()
    if not memberships:
        return None, None

    if tenant_id:
        for membership in memberships:
            if membership.tenant_id == tenant_id:
                return membership.tenant, membership
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to the requested tenant.",
        )

    membership = memberships[0]
    return membership.tenant, membership


@router.post("/login", response_model=TokenResponse, summary="Password login")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user_stmt = select(User).where(User.email == payload.email)
    user = db.execute(user_stmt).scalar_one_or_none()
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    tenant, membership = _resolve_membership(db, user, payload.tenant_id)

    tenant_id = tenant.id if tenant else None
    roles = [membership.role] if membership else (["platform_admin"] if user.is_platform_admin else [])

    token = create_access_token(
        subject=str(user.id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        tenant_id=str(tenant_id) if tenant_id else None,
        roles=roles,
    )
    return TokenResponse(access_token=token, tenant_id=tenant_id, roles=roles)


@router.get("/me", response_model=MeResponse, summary="Current user context")
def me(ctx: AuthContext = Depends(get_auth_context), db: Session = Depends(get_db)) -> MeResponse:
    tenant_id = ctx.tenant.id if ctx.tenant else None
    memberships_stmt = select(Membership).where(Membership.user_id == ctx.user.id)
    memberships = db.execute(memberships_stmt).scalars().all()

    context = {
        "tenants": [
            {
                "tenant_id": str(m.tenant_id),
                "role": m.role,
            }
            for m in memberships
        ]
    }

    return MeResponse(
        user=UserInfo(
            id=ctx.user.id,
            email=ctx.user.email,
            full_name=ctx.user.full_name,
            is_platform_admin=ctx.user.is_platform_admin,
        ),
        tenant_id=tenant_id,
        roles=ctx.roles,
        context=context,
    )


@router.post("/switch-tenant", response_model=TokenResponse, summary="Switch tenant context")
def switch_tenant(
    payload: SwitchTenantRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> TokenResponse:
    tenant, membership = resolve_membership(db, user=ctx.user, tenant_id=payload.tenant_id)
    if tenant is None or membership is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to the requested tenant.",
        )

    roles = [membership.role]
    token = create_access_token(
        subject=str(ctx.user.id),
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
        tenant_id=str(tenant.id),
        roles=roles,
    )
    return TokenResponse(access_token=token, tenant_id=tenant.id, roles=roles)
