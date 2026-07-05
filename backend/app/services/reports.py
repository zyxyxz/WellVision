from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext
from app.models import AnalysisRun, Report, ReportStatus
from app.schemas.report import ReportCreateRequest, ReportFromRunRequest, ReportUpdateRequest


@dataclass(frozen=True)
class ReportPolicy:
    can_edit_roles: tuple[str, ...] = ("tenant_admin", "tenant_engineer")
    can_review_roles: tuple[str, ...] = ("tenant_admin", "tenant_reviewer")


POLICY = ReportPolicy()


def _ensure_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _has_any_role(ctx: AuthContext, roles: tuple[str, ...]) -> bool:
    return ctx.user.is_platform_admin or any(role in ctx.roles for role in roles)


def _ensure_edit_access(ctx: AuthContext) -> None:
    if not _has_any_role(ctx, POLICY.can_edit_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit role required.")


def _ensure_review_access(ctx: AuthContext) -> None:
    if not _has_any_role(ctx, POLICY.can_review_roles):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Review role required.")


def list_reports(db: Session, *, tenant_id, status_filter: str | None = None) -> list[Report]:
    stmt = select(Report).where(Report.tenant_id == tenant_id)
    if status_filter:
        stmt = stmt.where(Report.status == status_filter)
    stmt = stmt.order_by(Report.updated_at.desc()).limit(500)
    return db.execute(stmt).scalars().all()


def get_report_or_404(db: Session, *, tenant_id, report_id) -> Report:
    stmt = select(Report).where(Report.tenant_id == tenant_id, Report.id == report_id)
    report = db.execute(stmt).scalar_one_or_none()
    if report is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found.")
    return report


def create_report(db: Session, *, ctx: AuthContext, payload: ReportCreateRequest) -> Report:
    tenant = _ensure_tenant(ctx)
    _ensure_edit_access(ctx)

    report = Report(
        tenant_id=tenant.id,
        created_by_user_id=ctx.user.id,
        title=payload.title.strip(),
        content_markdown=payload.content_markdown.strip(),
        status=ReportStatus.draft.value,
    )
    db.add(report)
    db.flush()
    return report


def create_report_from_run(db: Session, *, ctx: AuthContext, payload: ReportFromRunRequest) -> Report:
    tenant = _ensure_tenant(ctx)
    _ensure_edit_access(ctx)

    run_stmt = select(AnalysisRun).where(
        AnalysisRun.tenant_id == tenant.id,
        AnalysisRun.id == payload.run_id,
    )
    run = db.execute(run_stmt).scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis run not found.")

    title = (payload.title or f"Analysis Report - {run.algorithm_id} / {run.field}").strip()
    base_stats = run.base_stats_json or {}
    metrics = run.metrics_json or {}
    params = run.params_json or {}

    def _kv_lines(prefix: str, data: dict) -> list[str]:
        if not data:
            return [f"- {prefix}: (none)"] if prefix else []
        return [f"- {prefix}{k}: {v}" for k, v in data.items()]

    lines: list[str] = [
        f"# {title}",
        "",
        "## Analysis Context",
        f"- algorithm: {run.algorithm_id}",
        f"- field: {run.field}",
        f"- run_id: {run.id}",
        "",
        "## Base Stats",
        *(_kv_lines("", base_stats)),
        "",
        "## Algorithm Parameters",
        *(_kv_lines("", params)),
        "",
        "## Algorithm Metrics",
        *(_kv_lines("", metrics)),
    ]
    if payload.notes:
        lines.extend(["", "## Notes", payload.notes.strip()])

    report = Report(
        tenant_id=tenant.id,
        created_by_user_id=ctx.user.id,
        title=title,
        content_markdown="\n".join(lines).strip(),
        status=ReportStatus.draft.value,
        summary_json={
            "source": "analysis.run",
            "analysis_run_id": str(run.id),
            "algorithm_id": run.algorithm_id,
            "field": run.field,
            "params": params,
            "base_stats": base_stats,
            "metrics": metrics,
        },
    )
    db.add(report)
    db.flush()
    return report


def update_report(db: Session, *, ctx: AuthContext, report: Report, payload: ReportUpdateRequest) -> Report:
    _ensure_tenant(ctx)
    _ensure_edit_access(ctx)

    if report.status not in {ReportStatus.draft.value, ReportStatus.rejected.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or rejected reports can be edited.",
        )

    report.title = payload.title.strip()
    report.content_markdown = payload.content_markdown.strip()
    report.review_comment = None
    db.flush()
    return report


def submit_for_review(db: Session, *, ctx: AuthContext, report: Report) -> Report:
    _ensure_tenant(ctx)
    _ensure_edit_access(ctx)

    if report.status not in {ReportStatus.draft.value, ReportStatus.rejected.value}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only draft or rejected reports can be submitted.",
        )

    report.status = ReportStatus.in_review.value
    report.review_comment = None
    report.reviewed_by_user_id = None
    db.flush()
    return report


def approve_report(db: Session, *, ctx: AuthContext, report: Report, comment: str | None = None) -> Report:
    _ensure_tenant(ctx)
    _ensure_review_access(ctx)

    if report.status != ReportStatus.in_review.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in_review reports can be approved.",
        )

    report.status = ReportStatus.published.value
    report.review_comment = comment
    report.reviewed_by_user_id = ctx.user.id
    report.published_at = datetime.utcnow()
    db.flush()
    return report


def reject_report(db: Session, *, ctx: AuthContext, report: Report, comment: str | None = None) -> Report:
    _ensure_tenant(ctx)
    _ensure_review_access(ctx)

    if report.status != ReportStatus.in_review.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only in_review reports can be rejected.",
        )

    report.status = ReportStatus.rejected.value
    report.review_comment = comment
    report.reviewed_by_user_id = ctx.user.id
    report.published_at = None
    db.flush()
    return report
