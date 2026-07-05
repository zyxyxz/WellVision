from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import decode_token
from app.db.session import get_db
from app.models import Membership, Tenant, User

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    tenant: Tenant | None
    membership: Membership | None
    roles: list[str]


def _unauthorized(detail: str = "Not authenticated") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[Session, Depends(get_db)],
) -> User:
    if credentials is None:
        raise _unauthorized()

    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise _unauthorized("Invalid token payload")
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise _unauthorized("Invalid token")

    user = db.get(User, user_uuid)
    if not user or not user.is_active:
        raise _unauthorized("User not found or inactive")
    return user


def get_auth_context(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthContext:
    if credentials is None:
        raise _unauthorized()

    try:
        payload = decode_token(credentials.credentials)
    except ValueError:
        raise _unauthorized("Invalid token")

    tenant_id_raw = payload.get("tenant_id")
    roles = payload.get("roles") or []

    if not tenant_id_raw:
        return AuthContext(user=user, tenant=None, membership=None, roles=list(roles))

    try:
        tenant_uuid = uuid.UUID(str(tenant_id_raw))
    except (ValueError, TypeError):
        raise _unauthorized("Invalid tenant context")

    tenant = db.get(Tenant, tenant_uuid)
    if tenant is None:
        raise _unauthorized("Tenant not found")

    membership_stmt = select(Membership).where(
        Membership.user_id == user.id, Membership.tenant_id == tenant.id
    )
    membership = db.execute(membership_stmt).scalar_one_or_none()
    if membership is None and not user.is_platform_admin:
        raise _unauthorized("No access to tenant")

    membership_roles = roles if roles else ([membership.role] if membership else [])
    return AuthContext(
        user=user,
        tenant=tenant,
        membership=membership,
        roles=list(membership_roles),
    )


def require_roles(*required_roles: str):
    def _checker(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
        if ctx.user.is_platform_admin:
            return ctx
        if not required_roles:
            return ctx
        if not any(role in ctx.roles for role in required_roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires one of roles: {', '.join(required_roles)}",
            )
        return ctx

    return _checker


def require_platform_admin(ctx: Annotated[AuthContext, Depends(get_auth_context)]) -> AuthContext:
    if not ctx.user.is_platform_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Platform admin role required.",
        )
    return ctx
