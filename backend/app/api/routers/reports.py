from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.schemas.report import (
    ReportCreateRequest,
    ReportFromRunRequest,
    ReportResponse,
    ReportReviewRequest,
    ReportUpdateRequest,
)
from app.services.audit import write_audit_log
from app.services.reports import (
    approve_report,
    create_report,
    create_report_from_run,
    get_report_or_404,
    list_reports,
    reject_report,
    submit_for_review,
    update_report,
)

router = APIRouter(prefix="/reports", tags=["reports"])


def _to_response(report) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        tenant_id=report.tenant_id,
        created_by_user_id=report.created_by_user_id,
        reviewed_by_user_id=report.reviewed_by_user_id,
        title=report.title,
        content_markdown=report.content_markdown,
        summary_json=report.summary_json or {},
        status=report.status,
        review_comment=report.review_comment,
        created_at=report.created_at,
        updated_at=report.updated_at,
        published_at=report.published_at,
    )


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


@router.get("", response_model=list[ReportResponse], summary="List reports for tenant")
def list_reports_api(
    status: str | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[ReportResponse]:
    tenant = _require_tenant(ctx)
    reports = list_reports(db, tenant_id=tenant.id, status_filter=status)
    return [_to_response(r) for r in reports]


@router.post("", response_model=ReportResponse, summary="Create report draft")
def create_report_api(
    payload: ReportCreateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    report = create_report(db, ctx=ctx, payload=payload)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.create",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id), "title": report.title},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.post(
    "/from-analysis-run",
    response_model=ReportResponse,
    summary="Create a report draft from an analysis run",
)
def create_report_from_run_api(
    payload: ReportFromRunRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    report = create_report_from_run(db, ctx=ctx, payload=payload)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.create.from_run",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id), "analysis_run_id": str(payload.run_id)},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.patch("/{report_id}", response_model=ReportResponse, summary="Update report draft")
def update_report_api(
    report_id: uuid.UUID,
    payload: ReportUpdateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    tenant = _require_tenant(ctx)
    report = get_report_or_404(db, tenant_id=tenant.id, report_id=report_id)
    report = update_report(db, ctx=ctx, report=report, payload=payload)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.update",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id), "status": report.status},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.post("/{report_id}/submit", response_model=ReportResponse, summary="Submit report for review")
def submit_report_api(
    report_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    tenant = _require_tenant(ctx)
    report = get_report_or_404(db, tenant_id=tenant.id, report_id=report_id)
    report = submit_for_review(db, ctx=ctx, report=report)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.submit",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id)},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.post("/{report_id}/approve", response_model=ReportResponse, summary="Approve and publish report")
def approve_report_api(
    report_id: uuid.UUID,
    payload: ReportReviewRequest | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    tenant = _require_tenant(ctx)
    report = get_report_or_404(db, tenant_id=tenant.id, report_id=report_id)
    comment = payload.comment if payload else None
    report = approve_report(db, ctx=ctx, report=report, comment=comment)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.approve",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id), "comment": comment},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)


@router.post("/{report_id}/reject", response_model=ReportResponse, summary="Reject report back to draft")
def reject_report_api(
    report_id: uuid.UUID,
    payload: ReportReviewRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ReportResponse:
    tenant = _require_tenant(ctx)
    report = get_report_or_404(db, tenant_id=tenant.id, report_id=report_id)
    report = reject_report(db, ctx=ctx, report=report, comment=payload.comment)
    write_audit_log(
        db,
        actor=ctx.user,
        action="report.reject",
        tenant_id=report.tenant_id,
        details={"report_id": str(report.id), "comment": payload.comment},
    )
    db.commit()
    db.refresh(report)
    return _to_response(report)
