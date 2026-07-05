from __future__ import annotations

import math
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import OpSegment
from app.schemas.well_run import (
    AlignChannelRequest,
    WellRunAlignRequest,
    WellRunAxisMapConfig,
    WellRunSegmentCreate,
    WellRunSegmentDetectRequest,
    WellRunSegmentDetectResponse,
    WellRunSegmentResponse,
    WellRunSegmentUpdate,
)
from app.services.well_run_alignment import align_well_run_series


def _to_epoch(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _to_segment_response(row: OpSegment) -> WellRunSegmentResponse:
    return WellRunSegmentResponse(
        id=row.id,
        tenant_id=row.tenant_id,
        warehouse_id=row.warehouse_id,
        well_run_id=row.well_run_id,
        segment_type=row.segment_type,
        source=row.source,
        confidence=row.confidence,
        start_ts=row.start_ts,
        end_ts=row.end_ts,
        md_start=row.md_start,
        md_end=row.md_end,
        details=row.details or {},
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def list_well_run_segments(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    segment_type: str | None = None,
    source: str | None = None,
    limit: int = 500,
) -> list[WellRunSegmentResponse]:
    limit = max(10, min(limit, 5000))
    stmt = select(OpSegment).where(
        OpSegment.tenant_id == tenant_id,
        OpSegment.well_run_id == well_run_id,
    )
    if segment_type:
        stmt = stmt.where(OpSegment.segment_type == segment_type)
    if source:
        stmt = stmt.where(OpSegment.source == source)
    stmt = stmt.order_by(OpSegment.start_ts.asc(), OpSegment.created_at.asc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return [_to_segment_response(row) for row in rows]


def create_well_run_segment(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    warehouse_id,
    payload: WellRunSegmentCreate,
) -> WellRunSegmentResponse:
    row = OpSegment(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        well_run_id=well_run_id,
        segment_type=payload.segment_type.strip(),
        source=(payload.source or "manual").strip() or "manual",
        confidence=payload.confidence,
        start_ts=payload.start_ts,
        end_ts=payload.end_ts,
        md_start=payload.md_start,
        md_end=payload.md_end,
        details=payload.details or {},
    )
    db.add(row)
    db.flush()
    return _to_segment_response(row)


def update_well_run_segment(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    segment_id: uuid.UUID,
    payload: WellRunSegmentUpdate,
) -> WellRunSegmentResponse | None:
    row = db.get(OpSegment, segment_id)
    if row is None or row.tenant_id != tenant_id or row.well_run_id != well_run_id:
        return None

    if "segment_type" in payload.model_fields_set and payload.segment_type is not None:
        row.segment_type = payload.segment_type.strip() or row.segment_type
    if "source" in payload.model_fields_set and payload.source is not None:
        row.source = payload.source.strip() or row.source
    if "confidence" in payload.model_fields_set:
        row.confidence = payload.confidence
    if "start_ts" in payload.model_fields_set:
        row.start_ts = payload.start_ts
    if "end_ts" in payload.model_fields_set:
        row.end_ts = payload.end_ts
    if "md_start" in payload.model_fields_set:
        row.md_start = payload.md_start
    if "md_end" in payload.model_fields_set:
        row.md_end = payload.md_end
    if "details" in payload.model_fields_set:
        row.details = payload.details

    db.flush()
    return _to_segment_response(row)


def load_segment_ranges(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    segment_ids: list[uuid.UUID],
    segment_types: list[str],
) -> tuple[list[tuple[float, float]], list[tuple[float, float]], dict[str, Any]]:
    ids = [item for item in segment_ids if item]
    types = [item.strip() for item in segment_types if item and item.strip()]
    if not ids and not types:
        return [], [], {"selected_segments": 0}

    stmt = select(OpSegment).where(
        OpSegment.tenant_id == tenant_id,
        OpSegment.well_run_id == well_run_id,
    )
    if ids:
        stmt = stmt.where(OpSegment.id.in_(ids))
    if types:
        stmt = stmt.where(OpSegment.segment_type.in_(types))
    stmt = stmt.order_by(OpSegment.start_ts.asc(), OpSegment.created_at.asc())
    rows = db.execute(stmt).scalars().all()

    time_ranges: list[tuple[float, float]] = []
    depth_ranges: list[tuple[float, float]] = []
    distribution: Counter[str] = Counter()
    for row in rows:
        distribution[row.segment_type] += 1
        if row.start_ts is not None and row.end_ts is not None:
            start = _to_epoch(row.start_ts)
            end = _to_epoch(row.end_ts)
            if end >= start:
                time_ranges.append((start, end))
        if row.md_start is not None and row.md_end is not None:
            start_md = float(row.md_start)
            end_md = float(row.md_end)
            if math.isfinite(start_md) and math.isfinite(end_md):
                if end_md >= start_md:
                    depth_ranges.append((start_md, end_md))
                else:
                    depth_ranges.append((end_md, start_md))

    return time_ranges, depth_ranges, {
        "selected_segments": len(rows),
        "segment_types": dict(distribution),
        "filters": {
            "segment_ids": [str(item) for item in ids],
            "segment_types": types,
        },
    }


def _classify_state(
    *,
    rpm: float,
    wob: float,
    flow: float,
    rop_m_per_h: float,
    req: WellRunSegmentDetectRequest,
) -> str:
    if rpm >= req.rpm_on and wob >= req.wob_on and flow >= req.flow_on and rop_m_per_h >= req.rop_on_m_per_h:
        return "drilling"
    if wob <= req.wob_idle and flow <= req.flow_idle and rpm <= req.rpm_idle and abs(rop_m_per_h) <= (
        req.trip_rate_m_per_h * 0.2
    ):
        return "connection"
    if wob <= req.wob_idle and flow >= req.flow_on and rpm <= req.rpm_idle:
        return "circulation"
    if wob <= req.wob_idle and flow <= req.flow_idle and rop_m_per_h >= req.trip_rate_m_per_h:
        return "trip_in"
    if wob <= req.wob_idle and flow <= req.flow_idle and rop_m_per_h <= -req.trip_rate_m_per_h:
        return "trip_out"
    return "other"


def detect_well_run_segments(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    warehouse_id,
    payload: WellRunSegmentDetectRequest,
) -> WellRunSegmentDetectResponse:
    aligned = align_well_run_series(
        db,
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        payload=WellRunAlignRequest(
            axis="time",
            channels=[
                AlignChannelRequest(channel=payload.rpm_channel, source=payload.source, alias="rpm"),
                AlignChannelRequest(channel=payload.wob_channel, source=payload.source, alias="wob"),
                AlignChannelRequest(channel=payload.flow_channel, source=payload.source, alias="flow"),
                AlignChannelRequest(
                    channel=payload.bit_depth_channel,
                    source=payload.source,
                    alias="bit_depth",
                ),
            ],
            start=payload.start,
            end=payload.end,
            step_seconds=payload.step_seconds,
            max_rows=payload.max_rows,
            axis_map=WellRunAxisMapConfig(enabled=False),
        ),
    )

    records: list[tuple[datetime, str, float | None]] = []
    prev_ts: datetime | None = None
    prev_md: float | None = None
    for row in aligned.rows:
        ts = row.ts
        if ts is None:
            continue
        rpm = float(row.values.get("rpm").value or 0.0) if row.values.get("rpm") else 0.0
        wob = float(row.values.get("wob").value or 0.0) if row.values.get("wob") else 0.0
        flow = float(row.values.get("flow").value or 0.0) if row.values.get("flow") else 0.0
        md_value = row.values.get("bit_depth").value if row.values.get("bit_depth") else None
        md = float(md_value) if md_value is not None else None

        rop = 0.0
        if prev_ts is not None and prev_md is not None and md is not None:
            dt = max(1e-6, (ts - prev_ts).total_seconds())
            rop = ((md - prev_md) / dt) * 3600.0
        label = _classify_state(rpm=rpm, wob=wob, flow=flow, rop_m_per_h=rop, req=payload)
        records.append((ts, label, md))
        prev_ts = ts
        prev_md = md if md is not None else prev_md

    if payload.replace_existing_auto:
        db.execute(
            delete(OpSegment).where(
                OpSegment.tenant_id == tenant_id,
                OpSegment.well_run_id == well_run_id,
                OpSegment.source == payload.auto_source,
            )
        )

    created: list[OpSegment] = []
    if records:
        start_idx = 0
        for idx in range(1, len(records) + 1):
            is_boundary = idx == len(records) or records[idx][1] != records[start_idx][1]
            if not is_boundary:
                continue
            group = records[start_idx:idx]
            label = group[0][1]
            if len(group) >= payload.min_segment_points:
                start_ts = group[0][0]
                end_ts = group[-1][0]
                md_start = next((item[2] for item in group if item[2] is not None), None)
                md_end = next((item[2] for item in reversed(group) if item[2] is not None), None)
                confidence = min(1.0, len(group) / max(payload.min_segment_points * 4.0, 1.0))
                row = OpSegment(
                    tenant_id=tenant_id,
                    warehouse_id=warehouse_id,
                    well_run_id=well_run_id,
                    segment_type=label,
                    source=payload.auto_source,
                    confidence=round(confidence, 3),
                    start_ts=start_ts,
                    end_ts=end_ts,
                    md_start=md_start,
                    md_end=md_end,
                    details={
                        "point_count": len(group),
                        "step_seconds": payload.step_seconds,
                        "detector": "rule_v1",
                        "source": payload.source,
                    },
                )
                db.add(row)
                created.append(row)
            start_idx = idx

    db.flush()
    for row in created:
        db.refresh(row)

    distribution = Counter(row.segment_type for row in created)
    return WellRunSegmentDetectResponse(
        well_run_id=well_run_id,
        source=payload.source,
        auto_source=payload.auto_source,
        step_seconds=payload.step_seconds,
        scanned_points=len(records),
        created_segments=len(created),
        distribution=dict(distribution),
        rows=[_to_segment_response(row) for row in created],
    )
