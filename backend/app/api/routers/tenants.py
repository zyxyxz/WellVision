from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import Membership, Tenant
from app.schemas.tenant import TenantSummary

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.get("/mine", response_model=list[TenantSummary], summary="Tenants available to the user")
def list_my_tenants(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[TenantSummary]:
    stmt = (
        select(Tenant, Membership.role)
        .join(Membership, Membership.tenant_id == Tenant.id)
        .where(Membership.user_id == ctx.user.id)
        .order_by(Tenant.name.asc())
    )

    rows = db.execute(stmt).all()
    return [
        TenantSummary(id=tenant.id, name=tenant.name, slug=tenant.slug, role=role)
        for tenant, role in rows
    ]
