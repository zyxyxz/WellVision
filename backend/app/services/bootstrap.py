from __future__ import annotations

import re
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import get_password_hash
from app.models import EventMetric, Membership, ReportTemplate, Tenant, TenantRole, User, WellRun

settings = get_settings()

REPLAY_DEMO_WAREHOUSE = "Replay Digital Twin Warehouse"
REPLAY_DEMO_RUN_PREFIX = "Replay Digital Twin Demo"


def _slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "tenant"


def _ensure_roles(role: str | None, default: str) -> str:
    return role or default


def _has_replay_demo_data(db: Session, tenant_id) -> bool:
    expected_names = {
        f"{REPLAY_DEMO_RUN_PREFIX} - Normal Twin",
        f"{REPLAY_DEMO_RUN_PREFIX} - Anomaly Twin",
    }
    run_rows = (
        db.execute(
            select(WellRun.id, WellRun.name)
            .where(WellRun.tenant_id == tenant_id, WellRun.name.in_(expected_names))
        )
        .all()
    )
    if {row.name for row in run_rows} != expected_names:
        return False

    run_ids = [row.id for row in run_rows]
    metric_count = db.execute(
        select(func.count())
        .select_from(EventMetric)
        .where(EventMetric.tenant_id == tenant_id, EventMetric.well_run_id.in_(run_ids))
    ).scalar_one()
    return metric_count >= 1000


def _bootstrap_replay_demo_data(db: Session, tenant: Tenant) -> None:
    if not settings.bootstrap_replay_demo_data:
        return
    if _has_replay_demo_data(db, tenant.id):
        return

    from scripts.generate_replay_mock_data import generate_mock_data

    generate_mock_data(
        tenant_id_text=str(tenant.id),
        warehouse_name=REPLAY_DEMO_WAREHOUSE,
        well_run_name=REPLAY_DEMO_RUN_PREFIX,
        duration_minutes=120,
        step_seconds=2,
        seed=20260706,
        scenario="all",
        replace=True,
    )


def _bootstrap_replay_demo_data_for_tenants(db: Session) -> None:
    if not settings.bootstrap_replay_demo_data:
        return
    tenants = db.execute(select(Tenant).order_by(Tenant.created_at.asc())).scalars().all()
    for tenant in tenants:
        _bootstrap_replay_demo_data(db, tenant)


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
    _bootstrap_replay_demo_data_for_tenants(db)


def user_roles(memberships: Iterable[Membership]) -> list[str]:
    return [m.role for m in memberships]
