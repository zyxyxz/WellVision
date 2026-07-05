from __future__ import annotations

import json
import logging
import uuid
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context, require_roles
from app.core.config import get_settings
from app.db.session import SessionLocal, get_db
from app.models import (
    AIChatMessage,
    AIChatSession,
    DataWarehouse,
    Project,
    Report,
    ReportStatus,
    ReportTemplate,
    User,
    WellRun,
)
from app.schemas.ai_chat import (
    AIChatMessageResponse,
    AIChatRequest,
    AIChatResponse,
    AIChatSessionResponse,
)
from app.schemas.analysis import (
    AIReportRequest,
    AIReportResponse,
    AlgorithmInfo,
    AnalysisRunResponse,
    AlgorithmRunRequest,
    AlgorithmRunResponse,
    CompareResponse,
    FieldSummary,
    SeriesQuery,
    SeriesResponse,
)
from app.schemas.report_template import ReportTemplateCreate, ReportTemplateResponse, ReportTemplateUpdate
from app.services.analysis import (
    discover_numeric_fields,
    list_analysis_runs,
    list_algorithms,
    load_series,
    persist_analysis_run,
    run_custom_algorithm,
    run_algorithm,
    run_algorithm_pushdown,
    summarize,
    summarize_query,
)
from app.services.audit import write_audit_log
from app.services.system_settings import get_setting_value

router = APIRouter(prefix="/analysis", tags=["analysis"])
settings = get_settings()
EDIT_ROLES = {"tenant_admin", "tenant_engineer"}
logger = logging.getLogger(__name__)


def _resolve_ai_config(db: Session) -> dict:
    config = get_setting_value(db, "ai_config", {}) or {}
    provider = (config.get("provider") or "openai").lower()
    base_url = config.get("base_url")
    if not base_url:
        base_url = {
            "qwen": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "deepseek": "https://api.deepseek.com/v1",
            "kimi": "https://api.moonshot.cn/v1",
        }.get(provider)
    return {
        "provider": provider,
        "enabled": config.get("enabled", True),
        "api_key": config.get("api_key") or settings.openai_api_key,
        "base_url": base_url,
        "model": config.get("model") or settings.openai_model,
        "temperature": config.get("temperature"),
        "max_output_tokens": config.get("max_output_tokens"),
        "timeout_seconds": config.get("timeout_seconds"),
    }


def _ai_complete(
    ai_config: dict,
    *,
    system_prompt: str,
    user_prompt: str,
    max_tokens: int,
    messages: list[dict[str, str]] | None = None,
) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=ai_config["api_key"],
        base_url=ai_config.get("base_url") or None,
        timeout=ai_config.get("timeout_seconds") or None,
    )
    provider = (ai_config.get("provider") or "openai").lower()
    temperature = ai_config.get("temperature")
    if provider in {"qwen", "deepseek", "kimi"}:
        if messages is None:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": user_prompt})
        request_kwargs = {
            "model": ai_config["model"],
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            request_kwargs["temperature"] = temperature
        resp = client.chat.completions.create(**request_kwargs)
        if not resp.choices:
            return "(no output)"
        return resp.choices[0].message.content or "(no output)"

    prompt = f"{system_prompt}\n\n{user_prompt}" if system_prompt else user_prompt
    request_kwargs = {
        "model": ai_config["model"],
        "input": prompt,
        "max_output_tokens": max_tokens,
    }
    if temperature is not None:
        request_kwargs["temperature"] = temperature
    resp = client.responses.create(**request_kwargs)
    return resp.output_text or "(no output)"


def _ai_chat_complete(
    ai_config: dict,
    *,
    messages: list[dict[str, str]],
    max_tokens: int,
) -> str:
    from openai import OpenAI

    client = OpenAI(
        api_key=ai_config["api_key"],
        base_url=ai_config.get("base_url") or None,
        timeout=ai_config.get("timeout_seconds") or None,
    )
    request_kwargs: dict[str, Any] = {
        "model": ai_config["model"],
        "messages": messages,
        "max_tokens": max_tokens,
    }
    if ai_config.get("temperature") is not None:
        request_kwargs["temperature"] = ai_config.get("temperature")
    resp = client.chat.completions.create(**request_kwargs)
    if not resp.choices:
        return "(no output)"
    return resp.choices[0].message.content or "(no output)"


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _validate_warehouse(db: Session, tenant_id, warehouse_id: uuid.UUID | None):
    if warehouse_id is None:
        return None
    warehouse = db.get(DataWarehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")
    return warehouse


def _validate_well_run(db: Session, tenant_id, well_run_id: uuid.UUID | None):
    if well_run_id is None:
        return None
    run = db.get(WellRun, well_run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Well run not found.")
    return run


def _series_response(field: str, points, stats: dict[str, float | int]) -> SeriesResponse:
    return SeriesResponse(field=field, points=list(points), stats=stats)


@router.get("/algorithms", response_model=list[AlgorithmInfo], summary="List available analysis algorithms")
def algorithms(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AlgorithmInfo]:
    tenant = _require_tenant(ctx)
    return list_algorithms(db, tenant.id)


@router.get("/fields", response_model=list[FieldSummary], summary="Discover numeric fields")
def fields(
    limit: int = 1000,
    warehouse_id: uuid.UUID | None = None,
    well_run_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[FieldSummary]:
    tenant = _require_tenant(ctx)
    warehouse = _validate_warehouse(db, tenant.id, warehouse_id)
    run = _validate_well_run(db, tenant.id, well_run_id)
    if warehouse is not None and run is not None and run.warehouse_id and run.warehouse_id != warehouse.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="well_run_id does not belong to warehouse_id.",
        )
    return discover_numeric_fields(
        db,
        tenant_id=tenant.id,
        limit=limit,
        warehouse_id=warehouse.id if warehouse else None,
        well_run_id=run.id if run else None,
    )


@router.get("/runs", response_model=list[AnalysisRunResponse], summary="List recent analysis runs")
def runs(
    algorithm_id: str | None = None,
    field: str | None = None,
    limit: int = 100,
    warehouse_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AnalysisRunResponse]:
    tenant = _require_tenant(ctx)
    warehouse = _validate_warehouse(db, tenant.id, warehouse_id)
    return list_analysis_runs(
        db,
        tenant_id=tenant.id,
        warehouse_id=warehouse.id if warehouse else None,
        algorithm_id=algorithm_id,
        field=field,
        limit=limit,
    )


@router.post("/series", response_model=SeriesResponse, summary="Load a time series by field")
def series(
    query: SeriesQuery,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> SeriesResponse:
    tenant = _require_tenant(ctx)
    warehouse = _validate_warehouse(db, tenant.id, query.warehouse_id)
    run = _validate_well_run(db, tenant.id, query.well_run_id)
    if warehouse is not None and run is not None and run.warehouse_id and run.warehouse_id != warehouse.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="well_run_id does not belong to warehouse_id.",
        )
    points = load_series(db, tenant_id=tenant.id, query=query)
    stats = summarize_query(db, tenant_id=tenant.id, query=query)
    return _series_response(query.field, points, stats)


@router.post("/compare", response_model=CompareResponse, summary="Compare two time segments")
def compare(
    payload: dict[str, SeriesQuery],
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> CompareResponse:
    tenant = _require_tenant(ctx)
    left = payload.get("left")
    right = payload.get("right")
    if not left or not right:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="left and right queries are required.")
    if left.field != right.field:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="left and right fields must match.")
    if left.warehouse_id != right.warehouse_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="left and right warehouse_id must match.")
    if left.well_run_id != right.well_run_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="left and right well_run_id must match.")
    warehouse = _validate_warehouse(db, tenant.id, left.warehouse_id)
    run = _validate_well_run(db, tenant.id, left.well_run_id)
    if warehouse is not None and run is not None and run.warehouse_id and run.warehouse_id != warehouse.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="well_run_id does not belong to warehouse_id.",
        )

    left_points = load_series(db, tenant_id=tenant.id, query=left)
    right_points = load_series(db, tenant_id=tenant.id, query=right)
    left_stats = summarize_query(db, tenant_id=tenant.id, query=left)
    right_stats = summarize_query(db, tenant_id=tenant.id, query=right)
    return CompareResponse(
        field=left.field,
        left=_series_response(left.field, left_points, left_stats),
        right=_series_response(right.field, right_points, right_stats),
    )


@router.post("/run", response_model=AlgorithmRunResponse, summary="Run an analysis algorithm")
def run(
    payload: AlgorithmRunRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AlgorithmRunResponse:
    tenant = _require_tenant(ctx)
    warehouse = _validate_warehouse(db, tenant.id, payload.series.warehouse_id)
    run_scope = _validate_well_run(db, tenant.id, payload.series.well_run_id)
    if warehouse is not None and run_scope is not None and run_scope.warehouse_id and run_scope.warehouse_id != warehouse.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="well_run_id does not belong to warehouse_id.",
        )

    base_stats = summarize_query(db, tenant_id=tenant.id, query=payload.series)
    base_count = int(base_stats.get("count", 0) or 0)
    if base_count <= 0:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No data points found for the given query.")

    params = payload.params or {}
    result = run_algorithm_pushdown(
        db,
        tenant_id=tenant.id,
        algorithm_id=payload.algorithm_id,
        query=payload.series,
        params=params,
    )
    points_count = base_count

    if result is None:
        points = load_series(db, tenant_id=tenant.id, query=payload.series)
        if not points:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No data points found for the given query.")
        points_count = len(points)

        run_params = dict(params)
        secondary_field = params.get("secondary_field")
        if secondary_field:
            secondary_query = payload.series.model_copy(update={"field": secondary_field})
            secondary_points = load_series(db, tenant_id=tenant.id, query=secondary_query)
            if not secondary_points:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No data points found for the secondary field.",
                )
            run_params["_secondary_series"] = secondary_points

        try:
            result = run_algorithm(payload.algorithm_id, points, run_params)
        except KeyError:
            result = run_custom_algorithm(
                db,
                tenant_id=tenant.id,
                algorithm_id=payload.algorithm_id,
                series=points,
                params=params,
            )

    run_row = persist_analysis_run(
        db,
        tenant_id=tenant.id,
        user_id=ctx.user.id,
        warehouse_id=payload.series.warehouse_id,
        algorithm_id=payload.algorithm_id,
        field=payload.series.field,
        params=params,
        base_stats=base_stats,
        metrics=result.metrics,
        result_series=result.result_series,
    )
    write_audit_log(
        db,
        actor=ctx.user,
        action="analysis.run",
        tenant_id=tenant.id,
        details={
            "algorithm_id": payload.algorithm_id,
            "field": payload.series.field,
            "points": points_count,
            "run_id": str(run_row.id),
        },
    )
    db.commit()

    return AlgorithmRunResponse(
        algorithm_id=payload.algorithm_id,
        run_id=run_row.id,
        result_series=result.result_series,
        result_points=result.result_points or [],
        x_axis=result.x_axis,
        metrics=result.metrics,
    )


@router.post("/ai-report", response_model=AIReportResponse, summary="Generate an AI analysis report")
def ai_report(
    payload: AIReportRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AIReportResponse:
    tenant = _require_tenant(ctx)
    ai_config = _resolve_ai_config(db)
    if not ai_config.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI feature is disabled.")
    if not ai_config.get("api_key"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI API key is not configured.")

    template: ReportTemplate | None = None
    if payload.template_id is not None:
        template = db.get(ReportTemplate, payload.template_id)
        if template is None or template.tenant_id != tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    warehouse = None
    project = None
    if payload.series.warehouse_id is not None:
        warehouse = _validate_warehouse(db, tenant.id, payload.series.warehouse_id)
        if warehouse.project_id:
            project = db.get(Project, warehouse.project_id)
    points = load_series(db, tenant_id=tenant.id, query=payload.series)
    stats = summarize(points)
    algo_metrics: dict[str, Any] = payload.algorithm_result.metrics if payload.algorithm_result else {}

    try:
        project_context = ""
        if project is not None:
            project_context = (
                f"Project: {project.name} ({project.code})\n"
                f"Project background: {project.background or project.description or '-'}\n"
            )
        base_prompt = (
            "You are a drilling data analyst. Produce a concise markdown report with: "
            "1) data summary, 2) key observations, 3) risks/anomalies, 4) next actions.\n\n"
            f"Title: {payload.title}\n"
            f"{project_context}"
            f"Field: {payload.series.field}\n"
            f"Stats: {stats}\n"
            f"Algorithm metrics: {algo_metrics}\n"
            f"Notes: {payload.notes or '-'}\n"
        )
        template_prompt = ""
        if template:
            template_prompt = (
                "\nFollow this report template strictly. Use markdown headings and bullet points.\n"
                f"{template.prompt_template}\n"
            )
        prompt = base_prompt + template_prompt
        report_markdown = _ai_complete(
            ai_config,
            system_prompt="",
            user_prompt=prompt,
            max_tokens=int(ai_config.get("max_output_tokens") or 800),
        )
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("AI report failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI report failed: {exc}") from exc

    write_audit_log(
        db,
        actor=ctx.user,
        action="analysis.ai_report",
        tenant_id=tenant.id,
        details={"field": payload.series.field, "points": len(points)},
    )
    report_id = None
    if payload.save_as_report:
        has_edit_role = ctx.user.is_platform_admin or any(role in EDIT_ROLES for role in ctx.roles)
        if not has_edit_role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Edit role required to save report.")
        report = Report(
            tenant_id=tenant.id,
            created_by_user_id=ctx.user.id,
            title=(payload.report_title or payload.title).strip(),
            content_markdown=report_markdown,
            status=ReportStatus.draft.value,
            summary_json={
                "source": "analysis.ai_report",
                "field": payload.series.field,
                "stats": stats,
                "algorithm_metrics": algo_metrics,
                "template_id": str(template.id) if template else None,
            },
        )
        db.add(report)
        db.flush()
        report_id = report.id
        write_audit_log(
            db,
            actor=ctx.user,
            action="report.create.ai",
            tenant_id=tenant.id,
            details={"report_id": str(report_id), "field": payload.series.field},
        )

    db.commit()

    return AIReportResponse(model=ai_config["model"], report_markdown=report_markdown, report_id=report_id)


@router.get(
    "/report-templates",
    response_model=list[ReportTemplateResponse],
    summary="List report templates",
)
def list_report_templates(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[ReportTemplateResponse]:
    tenant = _require_tenant(ctx)
    stmt = (
        select(ReportTemplate)
        .where(ReportTemplate.tenant_id == tenant.id)
        .order_by(ReportTemplate.created_at.desc())
    )
    rows = db.execute(stmt).scalars().all()
    return [
        ReportTemplateResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            created_by_user_id=row.created_by_user_id,
            name=row.name,
            description=row.description,
            prompt_template=row.prompt_template,
            enabled=row.enabled,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


@router.post(
    "/report-templates",
    response_model=ReportTemplateResponse,
    summary="Create report template",
)
def create_report_template(
    payload: ReportTemplateCreate,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    tenant = _require_tenant(ctx)
    template = ReportTemplate(
        tenant_id=tenant.id,
        created_by_user_id=ctx.user.id,
        name=payload.name.strip(),
        description=(payload.description or "").strip() or None,
        prompt_template=payload.prompt_template.strip(),
        enabled=payload.enabled,
    )
    db.add(template)
    db.flush()
    write_audit_log(
        db,
        actor=ctx.user,
        action="report_template.create",
        tenant_id=tenant.id,
        details={"template_id": str(template.id), "name": template.name},
    )
    db.commit()
    db.refresh(template)
    return ReportTemplateResponse(
        id=template.id,
        tenant_id=template.tenant_id,
        created_by_user_id=template.created_by_user_id,
        name=template.name,
        description=template.description,
        prompt_template=template.prompt_template,
        enabled=template.enabled,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.patch(
    "/report-templates/{template_id}",
    response_model=ReportTemplateResponse,
    summary="Update report template",
)
def update_report_template(
    template_id: uuid.UUID,
    payload: ReportTemplateUpdate,
    ctx: AuthContext = Depends(require_roles(*EDIT_ROLES)),
    db: Session = Depends(get_db),
) -> ReportTemplateResponse:
    tenant = _require_tenant(ctx)
    template = db.get(ReportTemplate, template_id)
    if template is None or template.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found.")

    if payload.name is not None:
        template.name = payload.name.strip() or template.name
    if payload.description is not None:
        template.description = payload.description.strip() or None
    if payload.prompt_template is not None:
        template.prompt_template = payload.prompt_template.strip()
    if payload.enabled is not None:
        template.enabled = payload.enabled

    write_audit_log(
        db,
        actor=ctx.user,
        action="report_template.update",
        tenant_id=tenant.id,
        details={"template_id": str(template.id)},
    )
    db.commit()
    db.refresh(template)
    return ReportTemplateResponse(
        id=template.id,
        tenant_id=template.tenant_id,
        created_by_user_id=template.created_by_user_id,
        name=template.name,
        description=template.description,
        prompt_template=template.prompt_template,
        enabled=template.enabled,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.get(
    "/chat/sessions",
    response_model=list[AIChatSessionResponse],
    summary="List AI chat sessions",
)
def list_chat_sessions(
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AIChatSessionResponse]:
    tenant = _require_tenant(ctx)
    stmt = (
        select(AIChatSession)
        .where(AIChatSession.tenant_id == tenant.id)
        .order_by(AIChatSession.updated_at.desc())
        .limit(50)
    )
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
    "/chat/sessions/{session_id}/messages",
    response_model=list[AIChatMessageResponse],
    summary="List chat messages",
)
def list_chat_messages(
    session_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[AIChatMessageResponse]:
    tenant = _require_tenant(ctx)
    session = db.get(AIChatSession, session_id)
    if session is None or session.tenant_id != tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    stmt = (
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session_id)
        .order_by(AIChatMessage.created_at.asc())
        .limit(200)
    )
    rows = db.execute(stmt).scalars().all()
    return [
        AIChatMessageResponse(id=row.id, role=row.role, content=row.content, created_at=row.created_at)
        for row in rows
    ]


@router.post("/chat", response_model=AIChatResponse, summary="Send an AI chat message")
def chat(
    payload: AIChatRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> AIChatResponse:
    tenant = _require_tenant(ctx)
    ai_config = _resolve_ai_config(db)
    if not ai_config.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI feature is disabled.")
    if not ai_config.get("api_key"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI API key is not configured.")

    warehouse_id = payload.context.warehouse_id if payload.context else None
    warehouse = _validate_warehouse(db, tenant.id, warehouse_id)
    project = db.get(Project, warehouse.project_id) if warehouse and warehouse.project_id else None

    session = None
    if payload.session_id:
        session = db.get(AIChatSession, payload.session_id)
        if session is None or session.tenant_id != tenant.id:
            logger.warning("AI chat stream session not found; creating new session. session_id=%s", payload.session_id)
            session = None
    if session is None:
        session = AIChatSession(
            tenant_id=tenant.id,
            user_id=ctx.user.id,
            warehouse_id=warehouse.id if warehouse else None,
            title=(payload.title or payload.message[:40]).strip(),
            context_json=(jsonable_encoder(payload.context) if payload.context else {}),
        )
        db.add(session)
        db.flush()

    user_msg = AIChatMessage(session_id=session.id, role="user", content=payload.message.strip())
    db.add(user_msg)
    db.commit()
    db.refresh(session)

    stmt = (
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session.id)
        .order_by(AIChatMessage.created_at.asc())
        .limit(30)
    )
    history = db.execute(stmt).scalars().all()

    context_lines = []
    if warehouse:
        context_lines.append(f"Warehouse: {warehouse.name} ({warehouse.id})")
    if project:
        context_lines.append(f"Project: {project.name} ({project.code})")
        context_lines.append(f"Project background: {project.background or project.description or '-'}")
    if payload.context:
        if payload.context.field:
            context_lines.append(f"Field: {payload.context.field}")
        if payload.context.start or payload.context.end:
            context_lines.append(f"Range: {payload.context.start} - {payload.context.end}")
        if payload.context.algorithm_result:
            context_lines.append(f"Algorithm metrics: {payload.context.algorithm_result.metrics}")
        if payload.context.notes:
            context_lines.append(f"Notes: {payload.context.notes}")

        if payload.context.field:
            try:
                series_query = SeriesQuery(
                    field=payload.context.field,
                    start=payload.context.start,
                    end=payload.context.end,
                    limit=1200,
                    warehouse_id=payload.context.warehouse_id,
                )
                points = load_series(db, tenant_id=tenant.id, query=series_query)
                stats = summarize(points)
                context_lines.append(f"Stats: {stats}")
            except Exception:
                pass

    context_block = "\n".join(context_lines) if context_lines else "(no structured context)"
    conversation = "\n".join([f"{m.role.capitalize()}: {m.content}" for m in history if m.content])
    base_system_prompt = (
        "You are WellVision AI assistant for drilling data analysis. "
        "Reply in Chinese by default. Keep responses concise, structured, and actionable. "
        "Always use the conversation history to resolve follow-up questions and references."
    )
    system_prompt = f"{base_system_prompt}\n\nContext:\n{context_block}\n\nConversation so far:\n{conversation or '(none)'}"

    try:
        messages = [{"role": "system", "content": system_prompt}]
        messages.extend({"role": m.role, "content": m.content} for m in history if m.content)
        if not history or history[-1].role != "user" or history[-1].content != payload.message.strip():
            messages.append({"role": "user", "content": payload.message.strip()})
        logger.info(
            "AI chat request: model=%s provider=%s messages=%s",
            ai_config["model"],
            ai_config["provider"],
            [
                {
                    "role": m["role"],
                    "content": (m["content"][:200] + "...") if len(m["content"]) > 200 else m["content"],
                }
                for m in messages
            ],
        )
        reply = _ai_chat_complete(
            ai_config,
            messages=messages,
            max_tokens=int(ai_config.get("max_output_tokens") or 600),
        )
    except Exception as exc:  # pragma: no cover - network dependent
        logger.exception("AI chat failed")
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"AI chat failed: {exc}") from exc

    assistant_msg = AIChatMessage(
        session_id=session.id,
        role="assistant",
        content=reply,
        model=ai_config["model"],
    )
    db.add(assistant_msg)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="analysis.ai_chat",
        tenant_id=tenant.id,
        details={"session_id": str(session.id), "message_id": str(assistant_msg.id)},
    )
    db.commit()
    db.refresh(assistant_msg)

    return AIChatResponse(
        session_id=session.id,
        model=ai_config["model"],
        reply=reply,
        message_id=assistant_msg.id,
    )


@router.post("/chat/stream", summary="Send an AI chat message (streaming)")
def chat_stream(
    payload: AIChatRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    tenant = _require_tenant(ctx)
    user_id = ctx.user.id
    ai_config = _resolve_ai_config(db)
    if not ai_config.get("enabled", True):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI feature is disabled.")
    if not ai_config.get("api_key"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="AI API key is not configured.")

    warehouse_id = payload.context.warehouse_id if payload.context else None
    warehouse = _validate_warehouse(db, tenant.id, warehouse_id)
    project = db.get(Project, warehouse.project_id) if warehouse and warehouse.project_id else None

    session = None
    if payload.session_id:
        session = db.get(AIChatSession, payload.session_id)
        if session is None or session.tenant_id != tenant.id:
            logger.warning("AI chat session not found; creating new session. session_id=%s", payload.session_id)
            session = None
    if session is None:
        session = AIChatSession(
            tenant_id=tenant.id,
            user_id=user_id,
            warehouse_id=warehouse.id if warehouse else None,
            title=(payload.title or payload.message[:40]).strip(),
            context_json=(jsonable_encoder(payload.context) if payload.context else {}),
        )
        db.add(session)
        db.flush()

    user_msg = AIChatMessage(session_id=session.id, role="user", content=payload.message.strip())
    db.add(user_msg)
    db.flush()
    db.commit()
    db.refresh(session)

    stmt = (
        select(AIChatMessage)
        .where(AIChatMessage.session_id == session.id)
        .order_by(AIChatMessage.created_at.asc())
        .limit(30)
    )
    history = db.execute(stmt).scalars().all()

    context_lines = []
    if warehouse:
        context_lines.append(f"Warehouse: {warehouse.name} ({warehouse.id})")
    if project:
        context_lines.append(f"Project: {project.name} ({project.code})")
        context_lines.append(f"Project background: {project.background or project.description or '-'}")
    if payload.context:
        if payload.context.field:
            context_lines.append(f"Field: {payload.context.field}")
        if payload.context.start or payload.context.end:
            context_lines.append(f"Range: {payload.context.start} - {payload.context.end}")
        if payload.context.algorithm_result:
            context_lines.append(f"Algorithm metrics: {payload.context.algorithm_result.metrics}")
        if payload.context.notes:
            context_lines.append(f"Notes: {payload.context.notes}")
        if payload.context.field:
            try:
                series_query = SeriesQuery(
                    field=payload.context.field,
                    start=payload.context.start,
                    end=payload.context.end,
                    limit=1200,
                    warehouse_id=payload.context.warehouse_id,
                )
                points = load_series(db, tenant_id=tenant.id, query=series_query)
                stats = summarize(points)
                context_lines.append(f"Stats: {stats}")
            except Exception:
                pass

    context_block = "\n".join(context_lines) if context_lines else "(no structured context)"
    conversation_block = "\n".join([f"{m.role.capitalize()}: {m.content}" for m in history if m.content]) or "(none)"
    base_system_prompt = (
        "You are WellVision AI assistant for drilling data analysis. "
        "Reply in Chinese by default. Keep responses concise, structured, and actionable. "
        "Always use the conversation history to resolve follow-up questions and references."
    )
    system_prompt = (
        f"{base_system_prompt}\n\nContext:\n{context_block}\n\nConversation so far:\n{conversation_block}"
    )

    def event_stream():
        reply_chunks: list[str] = []
        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=ai_config["api_key"],
                base_url=ai_config.get("base_url") or None,
                timeout=ai_config.get("timeout_seconds") or None,
            )
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend({"role": m.role, "content": m.content} for m in history if m.content)
            if not history or history[-1].role != "user" or history[-1].content != payload.message.strip():
                messages.append({"role": "user", "content": payload.message.strip()})
            logger.info(
                "AI chat stream request: model=%s provider=%s messages=%s",
                ai_config["model"],
                ai_config["provider"],
                [
                    {
                        "role": m["role"],
                        "content": (m["content"][:200] + "...") if len(m["content"]) > 200 else m["content"],
                    }
                    for m in messages
                ],
            )
            request_kwargs: dict[str, Any] = {
                "model": ai_config["model"],
                "messages": messages,
                "max_tokens": int(ai_config.get("max_output_tokens") or 600),
                "stream": True,
            }
            if ai_config.get("temperature") is not None:
                request_kwargs["temperature"] = ai_config.get("temperature")
            stream = client.chat.completions.create(**request_kwargs)
            for chunk in stream:
                delta = None
                if chunk.choices and chunk.choices[0].delta:
                    delta = chunk.choices[0].delta.content
                if delta:
                    reply_chunks.append(delta)
                    payload_json = json.dumps({"type": "delta", "delta": delta}, ensure_ascii=False)
                    yield f"data: {payload_json}\n\n"
        except Exception as exc:
            logger.exception("AI chat stream failed")
            payload_json = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"data: {payload_json}\n\n"
            return

        reply = "".join(reply_chunks).strip() or "(no output)"
        try:
            with SessionLocal() as write_db:
                persisted_session = write_db.get(AIChatSession, session.id)
                if persisted_session is None:
                    logger.error("AI chat session missing during stream save: %s", session.id)
                    assistant_msg_id = None
                else:
                    assistant_msg = AIChatMessage(
                        session_id=session.id,
                        role="assistant",
                        content=reply,
                        model=ai_config["model"],
                    )
                    write_db.add(assistant_msg)
                    write_db.flush()
                    actor = write_db.get(User, user_id)
                    write_audit_log(
                        write_db,
                        actor=actor,
                        action="analysis.ai_chat",
                        tenant_id=tenant.id,
                        details={"session_id": str(session.id), "message_id": str(assistant_msg.id)},
                    )
                    write_db.commit()
                    write_db.refresh(assistant_msg)
                    assistant_msg_id = str(assistant_msg.id)

            payload_json = json.dumps(
                {
                    "type": "final",
                    "session_id": str(session.id),
                    "model": ai_config["model"],
                    "reply": reply,
                    "message_id": assistant_msg_id,
                },
                ensure_ascii=False,
            )
            yield f"data: {payload_json}\n\n"
        except Exception as exc:
            logger.exception("AI chat stream save failed")
            payload_json = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
            yield f"data: {payload_json}\n\n"
        yield 'data: {"type":"done"}\n\n'
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
