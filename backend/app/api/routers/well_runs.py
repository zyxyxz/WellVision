from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import DataWarehouse, WellRun
from app.schemas.well_run import (
    WellRunAlignRequest,
    WellRunAlignResponse,
    WellRunAxisMapResponse,
    WellRunChannelSummary,
    WellRunCreate,
    WellRunLagCorrectionRequest,
    WellRunLagCorrectionResponse,
    WellRunResponse,
    WellRunSegmentCreate,
    WellRunSegmentDetectRequest,
    WellRunSegmentDetectResponse,
    WellRunSegmentResponse,
    WellRunSegmentUpdate,
    WellRunUpdate,
)
from app.services.audit import write_audit_log
from app.services.well_run_lag import apply_well_run_lag_correction
from app.services.well_run_alignment import (
    align_well_run_series,
    discover_well_run_channels,
    preview_well_run_axis_map,
)
from app.services.well_run_segments import (
    create_well_run_segment,
    detect_well_run_segments,
    list_well_run_segments,
    load_segment_ranges,
    update_well_run_segment,
)

router = APIRouter(prefix="/well-runs", tags=["well-runs"])


def _require_tenant(ctx: AuthContext):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    return ctx.tenant


def _validate_warehouse(db: Session, tenant_id, warehouse_id: uuid.UUID | None) -> DataWarehouse | None:
    if warehouse_id is None:
        return None
    warehouse = db.get(DataWarehouse, warehouse_id)
    if warehouse is None or warehouse.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")
    return warehouse


def _get_well_run(db: Session, tenant_id, well_run_id: uuid.UUID) -> WellRun:
    run = db.get(WellRun, well_run_id)
    if run is None or run.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Well run not found.")
    return run


def _to_response(row: WellRun) -> WellRunResponse:
    return WellRunResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        warehouse_id=row.warehouse_id,
        name=row.name,
        well_name=row.well_name,
        section=row.section,
        status=row.status,
        started_at=row.started_at,
        ended_at=row.ended_at,
        details=row.details or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[WellRunResponse], summary="List well runs")
def list_well_runs(
    warehouse_id: uuid.UUID | None = None,
    status_value: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=200, ge=10, le=2000),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[WellRunResponse]:
    tenant = _require_tenant(ctx)
    if warehouse_id is not None:
        _validate_warehouse(db, tenant.id, warehouse_id)

    stmt = select(WellRun).where(WellRun.tenant_id == tenant.id)
    if warehouse_id is not None:
        stmt = stmt.where(WellRun.warehouse_id == warehouse_id)
    if status_value:
        stmt = stmt.where(WellRun.status == status_value)
    stmt = stmt.order_by(WellRun.created_at.desc()).limit(limit)

    rows = db.execute(stmt).scalars().all()
    return [_to_response(row) for row in rows]


@router.post("", response_model=WellRunResponse, summary="Create well run")
def create_well_run(
    payload: WellRunCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunResponse:
    tenant = _require_tenant(ctx)
    warehouse = _validate_warehouse(db, tenant.id, payload.warehouse_id)

    row = WellRun(
        tenant_id=tenant.id,
        warehouse_id=warehouse.id if warehouse else None,
        name=payload.name.strip(),
        well_name=(payload.well_name or "").strip() or None,
        section=(payload.section or "").strip() or None,
        status=(payload.status or "active").strip() or "active",
        started_at=payload.started_at,
        ended_at=payload.ended_at,
        details=payload.details or {},
    )
    db.add(row)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.create",
        tenant_id=tenant.id,
        details={"well_run_id": str(row.id), "name": row.name},
    )
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.get("/{well_run_id}", response_model=WellRunResponse, summary="Get a well run")
def get_well_run(
    well_run_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunResponse:
    tenant = _require_tenant(ctx)
    row = _get_well_run(db, tenant.id, well_run_id)
    return _to_response(row)


@router.patch("/{well_run_id}", response_model=WellRunResponse, summary="Update a well run")
def update_well_run(
    well_run_id: uuid.UUID,
    payload: WellRunUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunResponse:
    tenant = _require_tenant(ctx)
    row = _get_well_run(db, tenant.id, well_run_id)

    if "warehouse_id" in payload.model_fields_set:
        if payload.warehouse_id is None:
            row.warehouse_id = None
        else:
            warehouse = _validate_warehouse(db, tenant.id, payload.warehouse_id)
            row.warehouse_id = warehouse.id if warehouse else None

    if payload.name is not None:
        row.name = payload.name.strip() or row.name
    if payload.well_name is not None:
        row.well_name = payload.well_name.strip() or None
    if payload.section is not None:
        row.section = payload.section.strip() or None
    if payload.status is not None:
        row.status = payload.status.strip() or row.status
    if payload.started_at is not None:
        row.started_at = payload.started_at
    if payload.ended_at is not None:
        row.ended_at = payload.ended_at
    if payload.details is not None:
        row.details = payload.details

    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.update",
        tenant_id=tenant.id,
        details={"well_run_id": str(row.id)},
    )
    db.commit()
    db.refresh(row)
    return _to_response(row)


@router.get(
    "/{well_run_id}/channels",
    response_model=list[WellRunChannelSummary],
    summary="Discover channels for a well run",
)
def list_well_run_channels(
    well_run_id: uuid.UUID,
    limit: int = Query(default=200, ge=10, le=2000),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[WellRunChannelSummary]:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    return discover_well_run_channels(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        limit=limit,
    )


@router.get(
    "/{well_run_id}/axis-map",
    response_model=WellRunAxisMapResponse,
    summary="Preview time-depth map for a well run",
)
def get_well_run_axis_map(
    well_run_id: uuid.UUID,
    source: str | None = Query(default=None),
    channel: str | None = Query(default=None),
    limit: int = Query(default=200, ge=10, le=5000),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunAxisMapResponse:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    return preview_well_run_axis_map(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        source=source,
        channel=channel,
        limit=limit,
    )


@router.get(
    "/{well_run_id}/segments",
    response_model=list[WellRunSegmentResponse],
    summary="List operation segments for a well run",
)
def list_segments(
    well_run_id: uuid.UUID,
    segment_type: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=500, ge=10, le=5000),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[WellRunSegmentResponse]:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    return list_well_run_segments(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        segment_type=segment_type,
        source=source,
        limit=limit,
    )


@router.post(
    "/{well_run_id}/segments",
    response_model=WellRunSegmentResponse,
    summary="Create a segment manually",
)
def create_segment(
    well_run_id: uuid.UUID,
    payload: WellRunSegmentCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunSegmentResponse:
    tenant = _require_tenant(ctx)
    run = _get_well_run(db, tenant.id, well_run_id)
    row = create_well_run_segment(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        warehouse_id=run.warehouse_id,
        payload=payload,
    )
    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.segment.create",
        tenant_id=tenant.id,
        details={"well_run_id": str(well_run_id), "segment_id": str(row.id), "segment_type": row.segment_type},
    )
    db.commit()
    return row


@router.patch(
    "/{well_run_id}/segments/{segment_id}",
    response_model=WellRunSegmentResponse,
    summary="Update a segment",
)
def patch_segment(
    well_run_id: uuid.UUID,
    segment_id: uuid.UUID,
    payload: WellRunSegmentUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunSegmentResponse:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    row = update_well_run_segment(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        segment_id=segment_id,
        payload=payload,
    )
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found.")
    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.segment.update",
        tenant_id=tenant.id,
        details={"well_run_id": str(well_run_id), "segment_id": str(segment_id)},
    )
    db.commit()
    return row


@router.post(
    "/{well_run_id}/segments/detect",
    response_model=WellRunSegmentDetectResponse,
    summary="Detect operation segments automatically",
)
def detect_segments(
    well_run_id: uuid.UUID,
    payload: WellRunSegmentDetectRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunSegmentDetectResponse:
    tenant = _require_tenant(ctx)
    run = _get_well_run(db, tenant.id, well_run_id)
    result = detect_well_run_segments(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        warehouse_id=run.warehouse_id,
        payload=payload,
    )
    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.segment.detect",
        tenant_id=tenant.id,
        details={
            "well_run_id": str(well_run_id),
            "source": payload.source,
            "auto_source": payload.auto_source,
            "created_segments": result.created_segments,
        },
    )
    db.commit()
    return result


@router.post(
    "/{well_run_id}/lag-correction",
    response_model=WellRunLagCorrectionResponse,
    summary="Apply lag correction to source metrics",
)
def lag_correction(
    well_run_id: uuid.UUID,
    payload: WellRunLagCorrectionRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunLagCorrectionResponse:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    result = apply_well_run_lag_correction(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        payload=payload,
    )
    write_audit_log(
        db,
        actor=ctx.user,
        action="well_run.lag_correction",
        tenant_id=tenant.id,
        details={
            "well_run_id": str(well_run_id),
            "source": payload.source,
            "lag_seconds": payload.lag_seconds,
            "direction": payload.direction,
            "affected_rows": result.affected_rows,
            "dry_run": payload.dry_run,
        },
    )
    if not payload.dry_run:
        db.commit()
    return result


@router.post(
    "/{well_run_id}/align",
    response_model=WellRunAlignResponse,
    summary="Align multi-source channels on time/depth axis",
)
def align_well_run(
    well_run_id: uuid.UUID,
    payload: WellRunAlignRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> WellRunAlignResponse:
    tenant = _require_tenant(ctx)
    _get_well_run(db, tenant.id, well_run_id)
    if not payload.channels:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="channels is required.")
    time_ranges: list[tuple[float, float]] = []
    depth_ranges: list[tuple[float, float]] = []
    segment_meta = {"selected_segments": 0}
    if payload.segment_ids or payload.segment_types:
        time_ranges, depth_ranges, segment_meta = load_segment_ranges(
            db,
            tenant_id=tenant.id,
            well_run_id=well_run_id,
            segment_ids=payload.segment_ids,
            segment_types=payload.segment_types,
        )
        if segment_meta.get("selected_segments", 0) <= 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No segments matched segment filters.",
            )
        if payload.axis == "time" and not time_ranges:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected segments do not have time ranges.",
            )
        if payload.axis == "depth" and not depth_ranges:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected segments do not have depth ranges.",
            )

    return align_well_run_series(
        db,
        tenant_id=tenant.id,
        well_run_id=well_run_id,
        payload=payload,
        time_ranges=time_ranges,
        depth_ranges=depth_ranges,
        segment_meta=segment_meta,
    )
