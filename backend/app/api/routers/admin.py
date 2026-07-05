from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, require_platform_admin
from app.core.security import get_password_hash
from app.db.session import get_db
from app.models import AIChatMessage, AIChatSession, Membership, SystemSetting, Tenant, TenantRole, User
from app.schemas.admin import (
    MembershipAssignRequest,
    MembershipResponse,
    TenantCreateRequest,
    TenantResponse,
    UserCreateRequest,
    UserResponse,
)
from app.schemas.ai_chat import AIChatMessageResponse, AIChatSessionResponse
from app.schemas.system_setting import SystemSettingResponse, SystemSettingUpsert
from app.services.audit import write_audit_log
from app.services.system_settings import upsert_setting

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/tenants", response_model=list[TenantResponse], summary="List tenants")
def list_tenants(
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[TenantResponse]:
    tenants = db.execute(select(Tenant).order_by(Tenant.created_at.desc())).scalars().all()
    return [TenantResponse(id=t.id, name=t.name, slug=t.slug) for t in tenants]


@router.post("/tenants", response_model=TenantResponse, summary="Create tenant")
def create_tenant(
    payload: TenantCreateRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TenantResponse:
    existing = db.execute(select(Tenant).where(Tenant.slug == payload.slug)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Tenant slug already exists.")

    tenant = Tenant(name=payload.name, slug=payload.slug)
    db.add(tenant)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="tenant.create",
        tenant_id=tenant.id,
        details={"name": tenant.name, "slug": tenant.slug},
    )
    db.commit()
    return TenantResponse(id=tenant.id, name=tenant.name, slug=tenant.slug)


@router.get("/users", response_model=list[UserResponse], summary="List users")
def list_users(
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[UserResponse]:
    users = db.execute(select(User).order_by(User.created_at.desc())).scalars().all()
    return [
        UserResponse(
            id=u.id,
            email=u.email,
            full_name=u.full_name,
            is_active=u.is_active,
            is_platform_admin=u.is_platform_admin,
        )
        for u in users
    ]


@router.post("/users", response_model=UserResponse, summary="Create user")
def create_user(
    payload: UserCreateRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    existing = db.execute(select(User).where(User.email == payload.email)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User email already exists.")

    user = User(
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=get_password_hash(payload.password),
        is_platform_admin=payload.is_platform_admin,
    )
    db.add(user)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="user.create",
        tenant_id=None,
        details={"email": user.email, "is_platform_admin": user.is_platform_admin},
    )
    db.commit()
    return UserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        is_platform_admin=user.is_platform_admin,
    )


@router.post(
    "/memberships",
    response_model=MembershipResponse,
    summary="Assign user to tenant with a role",
)
def assign_membership(
    payload: MembershipAssignRequest,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> MembershipResponse:
    user = db.get(User, payload.user_id)
    tenant = db.get(Tenant, payload.tenant_id)
    if not user or not tenant:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User or tenant not found.")

    role_value = payload.role
    allowed_roles = {r.value for r in TenantRole}
    if role_value not in allowed_roles:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role must be one of: {', '.join(sorted(allowed_roles))}",
        )

    stmt = select(Membership).where(
        Membership.user_id == payload.user_id,
        Membership.tenant_id == payload.tenant_id,
    )
    membership = db.execute(stmt).scalar_one_or_none()
    if membership is None:
        membership = Membership(user_id=user.id, tenant_id=tenant.id, role=role_value)
        db.add(membership)
    else:
        membership.role = role_value

    db.flush()
    write_audit_log(
        db,
        actor=ctx.user,
        action="membership.assign",
        tenant_id=tenant.id,
        details={"user_id": str(user.id), "role": membership.role},
    )
    db.commit()

    return MembershipResponse(
        id=membership.id,
        user_id=membership.user_id,
        tenant_id=membership.tenant_id,
        role=membership.role,
    )


@router.get("/system-settings", response_model=list[SystemSettingResponse], summary="List system settings")
def list_system_settings(
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[SystemSettingResponse]:
    rows = db.execute(select(SystemSetting).order_by(SystemSetting.key.asc())).scalars().all()
    return [
        SystemSettingResponse(
            key=row.key,
            value=row.value_json or {},
            updated_at=row.updated_at,
            updated_by_user_id=row.updated_by_user_id,
        )
        for row in rows
    ]


@router.get("/system-settings/{key}", response_model=SystemSettingResponse, summary="Get system setting")
def get_system_setting(
    key: str,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SystemSettingResponse:
    row = db.get(SystemSetting, key)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found.")
    return SystemSettingResponse(
        key=row.key,
        value=row.value_json or {},
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
    )


@router.put("/system-settings/{key}", response_model=SystemSettingResponse, summary="Upsert system setting")
def upsert_system_setting(
    key: str,
    payload: SystemSettingUpsert,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> SystemSettingResponse:
    row = upsert_setting(db, key=key, value=payload.value or {}, updated_by_user_id=ctx.user.id)
    write_audit_log(
        db,
        actor=ctx.user,
        action="system_setting.upsert",
        tenant_id=None,
        details={"key": key},
    )
    db.commit()
    db.refresh(row)
    return SystemSettingResponse(
        key=row.key,
        value=row.value_json or {},
        updated_at=row.updated_at,
        updated_by_user_id=row.updated_by_user_id,
    )


@router.get("/ai-chat/sessions", response_model=list[AIChatSessionResponse], summary="List AI chat sessions")
def list_ai_chat_sessions(
    limit: int = 50,
    offset: int = 0,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[AIChatSessionResponse]:
    stmt = select(AIChatSession).order_by(AIChatSession.created_at.desc()).limit(limit).offset(offset)
    rows = db.execute(stmt).scalars().all()
    return [
        AIChatSessionResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            warehouse_id=row.warehouse_id,
            title=row.title,
            context=row.context_json or {},
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.get(
    "/ai-chat/sessions/{session_id}/messages",
    response_model=list[AIChatMessageResponse],
    summary="List AI chat session messages",
)
def list_ai_chat_session_messages(
    session_id: str,
    ctx: AuthContext = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> list[AIChatMessageResponse]:
    session = db.get(AIChatSession, session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    stmt = (
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session.id)
        .order_by(AIChatMessage.created_at.asc())
        .limit(500)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AIChatMessageResponse(id=row.id, role=row.role, content=row.content, created_at=row.created_at)
        for row in rows
    ]
