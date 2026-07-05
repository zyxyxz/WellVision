from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Membership, Tenant, User


def get_user_memberships(db: Session, user_id: uuid.UUID) -> list[Membership]:
    stmt = select(Membership).where(Membership.user_id == user_id)
    return db.execute(stmt).scalars().all()


def resolve_membership(db: Session, *, user: User, tenant_id: uuid.UUID) -> tuple[Tenant | None, Membership | None]:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        return None, None
    stmt = select(Membership).where(Membership.user_id == user.id, Membership.tenant_id == tenant.id)
    membership = db.execute(stmt).scalar_one_or_none()
    return tenant, membership
