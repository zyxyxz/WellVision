from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.well_run import (
    WellRunLagCorrectionPreviewPoint,
    WellRunLagCorrectionRequest,
    WellRunLagCorrectionResponse,
)


@dataclass
class _AxisMapPoint:
    ts_epoch: float
    md: float


def _to_epoch(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def _dedupe_map(points: list[_AxisMapPoint]) -> list[_AxisMapPoint]:
    if not points:
        return []
    deduped: list[_AxisMapPoint] = [points[0]]
    for point in points[1:]:
        if math.isclose(point.ts_epoch, deduped[-1].ts_epoch, rel_tol=0, abs_tol=1e-9):
            deduped[-1] = point
            continue
        deduped.append(point)
    return deduped


def _load_axis_map(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    raw_source: str,
    preferred_source: str | None,
    preferred_channel: str | None,
    map_limit: int,
) -> tuple[str | None, str | None, list[_AxisMapPoint]]:
    selector_where = [
        "tenant_id = :tenant_id",
        "well_run_id = :well_run_id",
        "md IS NOT NULL",
    ]
    selector_params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "well_run_id": well_run_id,
        "raw_source": raw_source,
    }
    if preferred_source:
        selector_where.append("COALESCE(source, 'unknown') = :source")
        selector_params["source"] = preferred_source
    if preferred_channel:
        selector_where.append("COALESCE(channel, field) = :channel")
        selector_params["channel"] = preferred_channel

    if preferred_source and preferred_channel:
        selector_stmt = text(
            f"""
            SELECT COALESCE(source, 'unknown') AS src, COALESCE(channel, field) AS ch
            FROM event_metrics
            WHERE {" AND ".join(selector_where)}
            LIMIT 1
            """
        )
        selected = db.execute(selector_stmt, selector_params).fetchone()
    else:
        selector_stmt = text(
            f"""
            SELECT src, ch
            FROM (
                SELECT
                    COALESCE(source, 'unknown') AS src,
                    COALESCE(channel, field) AS ch,
                    COUNT(*)::bigint AS cnt
                FROM event_metrics
                WHERE {" AND ".join(selector_where)}
                GROUP BY COALESCE(source, 'unknown'), COALESCE(channel, field)
            ) candidates
            ORDER BY
                CASE WHEN src = 'surface' THEN 0 ELSE 1 END,
                CASE WHEN ch IN ('bit_depth', 'hole_depth', 'md', 'measured_depth') THEN 0 ELSE 1 END,
                CASE WHEN src = :raw_source THEN 1 ELSE 0 END,
                cnt DESC
            LIMIT 1
            """
        )
        selected = db.execute(selector_stmt, selector_params).fetchone()

    if selected is None:
        return None, None, []
    map_source = selected[0]
    map_channel = selected[1]

    rows = db.execute(
        text(
            """
            SELECT created_at, md
            FROM event_metrics
            WHERE tenant_id = :tenant_id
              AND well_run_id = :well_run_id
              AND md IS NOT NULL
              AND COALESCE(source, 'unknown') = :source
              AND COALESCE(channel, field) = :channel
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        {
            "tenant_id": tenant_id,
            "well_run_id": well_run_id,
            "source": map_source,
            "channel": map_channel,
            "limit": max(1000, min(map_limit, 1000000)),
        },
    ).fetchall()

    points: list[_AxisMapPoint] = []
    for row in rows:
        ts = row[0]
        md = row[1]
        if ts is None or md is None:
            continue
        try:
            ts_epoch = _to_epoch(ts)
            md_value = float(md)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(md_value):
            continue
        points.append(_AxisMapPoint(ts_epoch=ts_epoch, md=md_value))
    points.sort(key=lambda item: item.ts_epoch)
    return map_source, map_channel, _dedupe_map(points)


def _project_md(
    *,
    points: list[_AxisMapPoint],
    xs: list[float],
    ts_epoch: float,
    max_gap_seconds: float,
) -> float | None:
    if not points:
        return None
    idx = bisect_left(xs, ts_epoch)
    prev_point = points[idx - 1] if idx > 0 else None
    next_point = points[idx] if idx < len(points) else None
    if prev_point is not None and next_point is not None and next_point.ts_epoch > prev_point.ts_epoch:
        left_gap = abs(ts_epoch - prev_point.ts_epoch)
        right_gap = abs(next_point.ts_epoch - ts_epoch)
        if left_gap <= max_gap_seconds and right_gap <= max_gap_seconds:
            ratio = (ts_epoch - prev_point.ts_epoch) / (next_point.ts_epoch - prev_point.ts_epoch)
            return prev_point.md + ratio * (next_point.md - prev_point.md)

    candidates = []
    if prev_point is not None:
        candidates.append(prev_point)
    if next_point is not None:
        candidates.append(next_point)
    if not candidates:
        return None
    nearest = min(candidates, key=lambda item: abs(item.ts_epoch - ts_epoch))
    if abs(nearest.ts_epoch - ts_epoch) > max_gap_seconds:
        return None
    return nearest.md


def apply_well_run_lag_correction(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    payload: WellRunLagCorrectionRequest,
) -> WellRunLagCorrectionResponse:
    where = [
        "tenant_id = :tenant_id",
        "well_run_id = :well_run_id",
        "COALESCE(source, 'unknown') = :source",
    ]
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "well_run_id": well_run_id,
        "source": payload.source,
        "limit": payload.max_rows,
    }
    if payload.start is not None:
        where.append("created_at >= :start")
        params["start"] = payload.start
    if payload.end is not None:
        where.append("created_at <= :end")
        params["end"] = payload.end

    rows = db.execute(
        text(
            f"""
            SELECT
                id,
                created_at,
                md,
                COALESCE(channel, field) AS channel,
                value
            FROM event_metrics
            WHERE {" AND ".join(where)}
            ORDER BY created_at ASC
            LIMIT :limit
            """
        ),
        params,
    ).fetchall()

    channel_set = {item.strip() for item in payload.channels if item and item.strip()}
    candidates = []
    for row in rows:
        channel = str(row[3] or "").strip()
        if channel_set and channel not in channel_set:
            continue
        candidates.append(row)

    map_source: str | None = None
    map_channel: str | None = None
    map_points: list[_AxisMapPoint] = []
    map_xs: list[float] = []
    if payload.remap_md:
        map_source, map_channel, map_points = _load_axis_map(
            db,
            tenant_id=tenant_id,
            well_run_id=well_run_id,
            raw_source=payload.source,
            preferred_source=payload.map_source,
            preferred_channel=payload.map_channel,
            map_limit=max(payload.max_rows, 1000),
        )
        map_xs = [point.ts_epoch for point in map_points]

    shift_seconds = -payload.lag_seconds if payload.direction == "backward" else payload.lag_seconds
    updates: list[dict[str, Any]] = []
    preview: list[WellRunLagCorrectionPreviewPoint] = []
    for row in candidates:
        row_id = row[0]
        old_ts = row[1]
        old_md = row[2]
        channel = row[3]
        value = row[4]
        if old_ts is None:
            continue

        new_ts = old_ts + timedelta(seconds=shift_seconds)
        new_md = float(old_md) if old_md is not None else None
        if payload.remap_md and map_points:
            projected = _project_md(
                points=map_points,
                xs=map_xs,
                ts_epoch=_to_epoch(new_ts),
                max_gap_seconds=float(payload.max_gap_seconds),
            )
            if projected is not None:
                new_md = projected

        updates.append(
            {
                "id": row_id,
                "old_created_at": old_ts,
                "new_created_at": new_ts,
                "new_md": new_md,
            }
        )
        if len(preview) < 20:
            preview.append(
                WellRunLagCorrectionPreviewPoint(
                    channel=channel,
                    old_ts=old_ts,
                    new_ts=new_ts,
                    old_md=float(old_md) if old_md is not None else None,
                    new_md=float(new_md) if new_md is not None else None,
                    value=float(value),
                )
            )

    if not payload.dry_run and updates:
        db.execute(
            text(
                """
                UPDATE event_metrics
                SET created_at = :new_created_at,
                    md = :new_md,
                    quality_code = 5
                WHERE id = :id
                  AND created_at = :old_created_at
                """
            ),
            updates,
        )

    return WellRunLagCorrectionResponse(
        well_run_id=well_run_id,
        source=payload.source,
        channels=sorted(channel_set),
        lag_seconds=float(payload.lag_seconds),
        direction=payload.direction,
        scanned_rows=len(candidates),
        affected_rows=len(updates),
        map_source=map_source,
        map_channel=map_channel,
        dry_run=payload.dry_run,
        preview=preview,
    )
