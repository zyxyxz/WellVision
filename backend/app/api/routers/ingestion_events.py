from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.db.session import get_db
from app.models import DataWarehouse, Event, WellRun
from app.schemas.event import EventIngestRequest, EventResponse
from app.services.audit import write_audit_log
from app.services.event_metrics import (
    build_metric_rows,
    persist_metric_rows,
)

router = APIRouter(prefix="/ingestion/events", tags=["ingestion-events"])


@router.post("", response_model=EventResponse, summary="Ingest an HTTP event")
def ingest_event(
    payload: EventIngestRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> EventResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    warehouse: DataWarehouse | None = None
    if payload.warehouse_id is not None:
        warehouse = db.get(DataWarehouse, payload.warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

    well_run: WellRun | None = None
    if payload.well_run_id is not None:
        well_run = db.get(WellRun, payload.well_run_id)
        if well_run is None or well_run.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Well run not found.")
        if warehouse is not None and well_run.warehouse_id and well_run.warehouse_id != warehouse.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="well_run_id does not belong to warehouse_id.",
            )

    event = Event(
        tenant_id=ctx.tenant.id,
        warehouse_id=warehouse.id if warehouse else None,
        well_run_id=well_run.id if well_run else None,
        received_by_user_id=ctx.user.id,
        source=payload.source or "http",
        topic=payload.topic,
        payload=payload.payload,
    )
    db.add(event)
    db.flush()
    metric_rows = build_metric_rows(
        [
            {
                "id": event.id,
                "tenant_id": event.tenant_id,
                "warehouse_id": event.warehouse_id,
                "well_run_id": event.well_run_id,
                "source": event.source,
                "created_at": event.created_at,
                "payload": event.payload,
            }
        ]
    )
    if metric_rows:
        persist_metric_rows(db, metric_rows)

    write_audit_log(
        db,
        actor=ctx.user,
        action="event.ingest",
        tenant_id=ctx.tenant.id,
        details={
            "event_id": str(event.id),
            "source": event.source,
            "topic": event.topic,
            "warehouse_id": str(warehouse.id) if warehouse else None,
            "well_run_id": str(well_run.id) if well_run else None,
        },
    )
    db.commit()
    db.refresh(event)

    return EventResponse(
        id=event.id,
        tenant_id=event.tenant_id,
        warehouse_id=event.warehouse_id,
        well_run_id=event.well_run_id,
        received_by_user_id=event.received_by_user_id,
        source=event.source,
        topic=event.topic,
        payload=event.payload,
        created_at=event.created_at,
    )


@router.get("", response_model=list[EventResponse], summary="List recent events for tenant")
def list_events(
    source: str | None = None,
    topic: str | None = None,
    limit: int = Query(default=500, ge=10, le=5000),
    warehouse_id: uuid.UUID | None = None,
    well_run_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[EventResponse]:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    stmt = select(Event).where(Event.tenant_id == ctx.tenant.id)
    if warehouse_id is not None:
        stmt = stmt.where(Event.warehouse_id == warehouse_id)
    if well_run_id is not None:
        stmt = stmt.where(Event.well_run_id == well_run_id)
    if source:
        stmt = stmt.where(Event.source == source)
    if topic:
        stmt = stmt.where(Event.topic.is_not(None)).where(Event.topic.ilike(f"%{topic}%"))

    stmt = stmt.order_by(Event.created_at.desc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [
        EventResponse(
            id=row.id,
            tenant_id=row.tenant_id,
            warehouse_id=row.warehouse_id,
            well_run_id=row.well_run_id,
            received_by_user_id=row.received_by_user_id,
            source=row.source,
            topic=row.topic,
            payload=row.payload,
            created_at=row.created_at,
        )
        for row in rows
    ]
