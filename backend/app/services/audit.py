from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit_log(
    db: Session,
    *,
    actor: User | None,
    action: str,
    tenant_id: uuid.UUID | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    entry = AuditLog(
        tenant_id=tenant_id,
        actor_user_id=actor.id if actor else None,
        action=action,
        details=details or {},
    )
    db.add(entry)
    db.flush()
