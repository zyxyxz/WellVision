from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models import Membership, ReportTemplate, Tenant, TenantRole, User

settings = get_settings()


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "tenant"


def _ensure_roles(role: str | None, default: str) -> str:
    return role or default


def bootstrap_defaults(db: Session) -> None:
    tenant_stmt = select(Tenant).where(Tenant.slug == _slugify(settings.bootstrap_tenant_name))
    tenant = db.execute(tenant_stmt).scalar_one_or_none()
    if tenant is None:
        tenant = Tenant(name=settings.bootstrap_tenant_name, slug=_slugify(settings.bootstrap_tenant_name))
        db.add(tenant)
        db.flush()

    user_stmt = select(User).where(User.email == settings.bootstrap_admin_email)
    admin_user = db.execute(user_stmt).scalar_one_or_none()
    if admin_user is None:
        admin_user = User(
            email=settings.bootstrap_admin_email,
            full_name="Platform Admin",
            hashed_password=get_password_hash(settings.bootstrap_admin_password),
            is_platform_admin=True,
        )
        db.add(admin_user)
        db.flush()

    membership_stmt = select(Membership).where(
        Membership.user_id == admin_user.id, Membership.tenant_id == tenant.id
    )
    membership = db.execute(membership_stmt).scalar_one_or_none()
    if membership is None:
        membership = Membership(
            tenant_id=tenant.id,
            user_id=admin_user.id,
            role=TenantRole.tenant_admin.value,
        )
        db.add(membership)

    template_stmt = select(ReportTemplate).where(ReportTemplate.tenant_id == tenant.id)
    has_template = db.execute(template_stmt).first() is not None
    if not has_template:
        db.add(
            ReportTemplate(
                tenant_id=tenant.id,
                created_by_user_id=admin_user.id,
                name="标准工程报告",
                description="默认的工程分析报告模板",
                prompt_template=(
                    "# Summary\\n"
                    "- Overall status\\n"
                    "- Key metrics\\n"
                    "\\n"
                    "# Observations\\n"
                    "- 主要趋势\\n"
                    "- 异常点\\n"
                    "\\n"
                    "# Risks\\n"
                    "- 潜在风险\\n"
                    "- 影响范围\\n"
                    "\\n"
                    "# Recommendations\\n"
                    "- 建议措施\\n"
                    "- 后续监测\\n"
                ),
                enabled=True,
            )
        )
        db.add(
            ReportTemplate(
                tenant_id=tenant.id,
                created_by_user_id=admin_user.id,
                name="异常诊断报告",
                description="异常事件的专用分析模板",
                prompt_template=(
                    "# Incident\\n"
                    "- 异常时间段\\n"
                    "- 影响指标\\n"
                    "\\n"
                    "# Root Cause Hypothesis\\n"
                    "- 可能原因\\n"
                    "\\n"
                    "# Evidence\\n"
                    "- 支撑数据\\n"
                    "\\n"
                    "# Mitigation\\n"
                    "- 建议处置\\n"
                    "- 监测项\\n"
                ),
                enabled=True,
            )
        )

    db.commit()


def user_roles(memberships: Iterable[Membership]) -> list[str]:
    return [m.role for m in memberships]
