from __future__ import annotations

import math
from bisect import bisect_left
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.schemas.well_run import (
    AlignedChannelValue,
    AlignChannelRequest,
    WellRunAlignRequest,
    WellRunAlignResponse,
    WellRunAlignedRow,
    WellRunAxisMapConfig,
    WellRunAxisMapPoint,
    WellRunAxisMapResponse,
    WellRunChannelSummary,
)


@dataclass
class _AlignedPoint:
    x: float
    value: float
    quality_code: int
    source: str | None


@dataclass
class _AxisMap:
    source: str | None
    channel: str | None
    ts_to_md: list[_AlignedPoint]
    md_to_ts: list[_AlignedPoint]


def _to_epoch(value: datetime) -> float:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.timestamp()


def _from_epoch(value: float) -> datetime:
    return datetime.fromtimestamp(value, tz=timezone.utc)


def discover_well_run_channels(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    limit: int = 200,
) -> list[WellRunChannelSummary]:
    limit = max(10, min(limit, 2000))
    stmt = text(
        """
        SELECT
            COALESCE(source, 'unknown') AS source,
            COALESCE(channel, field) AS channel,
            COUNT(*)::bigint AS cnt,
            MIN(created_at) AS ts_start,
            MAX(created_at) AS ts_end,
            MIN(md) AS md_start,
            MAX(md) AS md_end
        FROM event_metrics
        WHERE tenant_id = :tenant_id
          AND well_run_id = :well_run_id
        GROUP BY COALESCE(source, 'unknown'), COALESCE(channel, field)
        ORDER BY cnt DESC, source ASC, channel ASC
        LIMIT :limit
        """
    )
    rows = db.execute(
        stmt,
        {"tenant_id": tenant_id, "well_run_id": well_run_id, "limit": limit},
    ).fetchall()
    return [
        WellRunChannelSummary(
            source=row[0],
            channel=row[1],
            count=int(row[2]),
            ts_start=row[3],
            ts_end=row[4],
            md_start=float(row[5]) if row[5] is not None else None,
            md_end=float(row[6]) if row[6] is not None else None,
        )
        for row in rows
    ]


def _resolve_aliases(channels: list[AlignChannelRequest]) -> list[tuple[str, AlignChannelRequest]]:
    resolved: list[tuple[str, AlignChannelRequest]] = []
    seen: dict[str, int] = {}
    for item in channels:
        base = (item.alias or "").strip()
        if not base:
            if item.source:
                base = f"{item.source}:{item.channel}"
            else:
                base = item.channel
        count = seen.get(base, 0)
        seen[base] = count + 1
        alias = base if count == 0 else f"{base}_{count + 1}"
        resolved.append((alias, item))
    return resolved


def _dedupe_sorted_points(points: list[_AlignedPoint], *, keep: str = "last") -> list[_AlignedPoint]:
    if not points:
        return []
    deduped: list[_AlignedPoint] = [points[0]]
    for point in points[1:]:
        if math.isclose(point.x, deduped[-1].x, rel_tol=0, abs_tol=1e-9):
            if keep == "last":
                deduped[-1] = point
            continue
        deduped.append(point)
    return deduped


def _base_selector_where(
    *,
    tenant_id,
    well_run_id,
    selector: AlignChannelRequest,
) -> tuple[list[str], dict[str, Any]]:
    where = [
        "tenant_id = :tenant_id",
        "well_run_id = :well_run_id",
        "COALESCE(channel, field) = :channel",
    ]
    params: dict[str, Any] = {
        "tenant_id": tenant_id,
        "well_run_id": well_run_id,
        "channel": selector.channel,
    }
    if selector.source:
        where.append("COALESCE(source, 'unknown') = :source")
        params["source"] = selector.source
    return where, params


def _load_time_points(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    selector: AlignChannelRequest,
    payload: WellRunAlignRequest,
    time_ranges: list[tuple[float, float]] | None,
) -> list[_AlignedPoint]:
    point_limit = max(5000, min(payload.max_rows * 300, 300000))
    where, params = _base_selector_where(
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        selector=selector,
    )
    params["limit"] = point_limit
    if payload.start is not None:
        where.append("created_at >= :start")
        params["start"] = payload.start
    if payload.end is not None:
        where.append("created_at <= :end")
        params["end"] = payload.end
    stmt = text(
        f"""
        SELECT
            created_at,
            value,
            COALESCE(quality_code, 0) AS quality_code,
            COALESCE(source, 'unknown') AS source
        FROM event_metrics
        WHERE {" AND ".join(where)}
        ORDER BY created_at ASC
        LIMIT :limit
        """
    )
    rows = db.execute(stmt, params).fetchall()
    points: list[_AlignedPoint] = []
    for row in rows:
        ts = row[0]
        value = row[1]
        if ts is None or value is None:
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric):
            continue
        points.append(
            _AlignedPoint(
                x=_to_epoch(ts),
                value=numeric,
                quality_code=int(row[2] or 0),
                source=row[3],
            )
        )
    points = _dedupe_sorted_points(points, keep="last")
    return _filter_points_by_ranges(points, time_ranges)


def _load_depth_points(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    selector: AlignChannelRequest,
    payload: WellRunAlignRequest,
    depth_ranges: list[tuple[float, float]] | None,
) -> list[_AlignedPoint]:
    point_limit = max(5000, min(payload.max_rows * 300, 300000))
    where, params = _base_selector_where(
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        selector=selector,
    )
    where.append("md IS NOT NULL")
    params["limit"] = point_limit
    if payload.md_start is not None:
        where.append("md >= :md_start")
        params["md_start"] = payload.md_start
    if payload.md_end is not None:
        where.append("md <= :md_end")
        params["md_end"] = payload.md_end

    stmt = text(
        f"""
        SELECT
            md,
            value,
            COALESCE(quality_code, 0) AS quality_code,
            COALESCE(source, 'unknown') AS source
        FROM event_metrics
        WHERE {" AND ".join(where)}
        ORDER BY md ASC
        LIMIT :limit
        """
    )
    rows = db.execute(stmt, params).fetchall()
    points: list[_AlignedPoint] = []
    for row in rows:
        md = row[0]
        value = row[1]
        if md is None or value is None:
            continue
        try:
            depth = float(md)
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(depth) or not math.isfinite(numeric):
            continue
        points.append(
            _AlignedPoint(
                x=depth,
                value=numeric,
                quality_code=int(row[2] or 0),
                source=row[3],
            )
        )
    points = _dedupe_sorted_points(points, keep="last")
    return _filter_points_by_ranges(points, depth_ranges)


def _point_in_ranges(x: float, ranges: list[tuple[float, float]] | None) -> bool:
    if not ranges:
        return True
    for start, end in ranges:
        lo = start if start <= end else end
        hi = end if end >= start else start
        if lo <= x <= hi:
            return True
    return False


def _filter_points_by_ranges(
    points: list[_AlignedPoint],
    ranges: list[tuple[float, float]] | None,
) -> list[_AlignedPoint]:
    if not ranges:
        return points
    return [point for point in points if _point_in_ranges(point.x, ranges)]


def _nearest_point(
    *,
    points: list[_AlignedPoint],
    xs: list[float],
    x: float,
    max_gap: float,
) -> tuple[_AlignedPoint | None, float]:
    if not points:
        return None, math.inf
    idx = bisect_left(xs, x)
    candidates: list[_AlignedPoint] = []
    if idx > 0:
        candidates.append(points[idx - 1])
    if idx < len(points):
        candidates.append(points[idx])
    if not candidates:
        return None, math.inf
    best = min(candidates, key=lambda point: abs(point.x - x))
    gap = abs(best.x - x)
    if gap > max_gap:
        return None, gap
    return best, gap


def _project_axis_value(
    *,
    map_points: list[_AlignedPoint],
    map_xs: list[float],
    x: float,
    max_gap: float,
) -> tuple[float | None, int]:
    if not map_points:
        return None, 9
    idx = bisect_left(map_xs, x)
    prev_p = map_points[idx - 1] if idx > 0 else None
    next_p = map_points[idx] if idx < len(map_points) else None
    if prev_p is not None and next_p is not None and next_p.x > prev_p.x:
        left_gap = abs(x - prev_p.x)
        right_gap = abs(next_p.x - x)
        if left_gap <= max_gap and right_gap <= max_gap:
            ratio = (x - prev_p.x) / (next_p.x - prev_p.x)
            value = prev_p.value + ratio * (next_p.value - prev_p.value)
            return value, 2
    nearest, _ = _nearest_point(points=map_points, xs=map_xs, x=x, max_gap=max_gap)
    if nearest is None:
        return None, 9
    return nearest.value, 1


def _project_points(
    *,
    points: list[_AlignedPoint],
    map_points: list[_AlignedPoint],
    max_gap: float,
) -> list[_AlignedPoint]:
    if not points or not map_points:
        return []
    map_xs = [point.x for point in map_points]
    projected: list[_AlignedPoint] = []
    for point in points:
        target_x, projection_quality = _project_axis_value(
            map_points=map_points,
            map_xs=map_xs,
            x=point.x,
            max_gap=max_gap,
        )
        if target_x is None:
            continue
        projected.append(
            _AlignedPoint(
                x=target_x,
                value=point.value,
                quality_code=max(int(point.quality_code or 0), projection_quality),
                source=point.source,
            )
        )
    projected.sort(key=lambda point: point.x)
    return _dedupe_sorted_points(projected, keep="last")


def _build_axis_map(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    config: WellRunAxisMapConfig,
) -> _AxisMap | None:
    if not config.enabled:
        return None

    selector_where = [
        "tenant_id = :tenant_id",
        "well_run_id = :well_run_id",
        "md IS NOT NULL",
    ]
    selector_params: dict[str, Any] = {"tenant_id": tenant_id, "well_run_id": well_run_id}
    if config.source:
        selector_where.append("COALESCE(source, 'unknown') = :source")
        selector_params["source"] = config.source
    if config.channel:
        selector_where.append("COALESCE(channel, field) = :channel")
        selector_params["channel"] = config.channel

    selector_stmt = text(
        f"""
        SELECT
            COALESCE(source, 'unknown') AS source,
            COALESCE(channel, field) AS channel,
            COUNT(*)::bigint AS cnt
        FROM event_metrics
        WHERE {" AND ".join(selector_where)}
        GROUP BY COALESCE(source, 'unknown'), COALESCE(channel, field)
        ORDER BY cnt DESC, source ASC, channel ASC
        LIMIT 1
        """
    )
    selector_row = db.execute(selector_stmt, selector_params).fetchone()
    if selector_row is None:
        return None

    selected_source = selector_row[0]
    selected_channel = selector_row[1]
    map_limit = max(1000, min(int(config.map_limit), 1000000))
    map_stmt = text(
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
    )
    map_rows = db.execute(
        map_stmt,
        {
            "tenant_id": tenant_id,
            "well_run_id": well_run_id,
            "source": selected_source,
            "channel": selected_channel,
            "limit": map_limit,
        },
    ).fetchall()
    if not map_rows:
        return None

    pairs: list[tuple[float, float]] = []
    for row in map_rows:
        ts = row[0]
        md = row[1]
        if ts is None or md is None:
            continue
        try:
            epoch = _to_epoch(ts)
            depth = float(md)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(depth):
            continue
        pairs.append((epoch, depth))
    if not pairs:
        return None

    ts_to_md_points = _dedupe_sorted_points(
        [
            _AlignedPoint(x=epoch, value=depth, quality_code=0, source=selected_source)
            for epoch, depth in sorted(pairs, key=lambda item: item[0])
        ],
        keep="last",
    )
    md_to_ts_points = _dedupe_sorted_points(
        [
            _AlignedPoint(x=depth, value=epoch, quality_code=0, source=selected_source)
            for epoch, depth in sorted(pairs, key=lambda item: (item[1], item[0]))
        ],
        keep="first",
    )
    if not ts_to_md_points or not md_to_ts_points:
        return None
    return _AxisMap(
        source=selected_source,
        channel=selected_channel,
        ts_to_md=ts_to_md_points,
        md_to_ts=md_to_ts_points,
    )


def preview_well_run_axis_map(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    source: str | None = None,
    channel: str | None = None,
    limit: int = 200,
) -> WellRunAxisMapResponse:
    row_limit = max(10, min(limit, 5000))
    axis_map = _build_axis_map(
        db,
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        config=WellRunAxisMapConfig(
            enabled=True,
            source=source,
            channel=channel,
            map_limit=max(row_limit * 50, 1000),
        ),
    )
    if axis_map is None:
        return WellRunAxisMapResponse(
            well_run_id=well_run_id,
            source=source,
            channel=channel,
            count=0,
            rows=[],
        )

    ts_to_md = axis_map.ts_to_md
    stride = max(1, int(math.ceil(len(ts_to_md) / row_limit)))
    sampled = ts_to_md[::stride][:row_limit]
    rows = [
        WellRunAxisMapPoint(ts=_from_epoch(point.x), md=round(float(point.value), 6))
        for point in sampled
    ]
    return WellRunAxisMapResponse(
        well_run_id=well_run_id,
        source=axis_map.source,
        channel=axis_map.channel,
        count=len(ts_to_md),
        ts_start=_from_epoch(ts_to_md[0].x),
        ts_end=_from_epoch(ts_to_md[-1].x),
        md_start=float(axis_map.md_to_ts[0].x),
        md_end=float(axis_map.md_to_ts[-1].x),
        rows=rows,
    )


def _load_channel_points(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    axis: str,
    selector: AlignChannelRequest,
    payload: WellRunAlignRequest,
    axis_map: _AxisMap | None,
    time_ranges: list[tuple[float, float]] | None,
    depth_ranges: list[tuple[float, float]] | None,
) -> list[_AlignedPoint]:
    native_axis = selector.native_axis
    if axis == "time":
        if native_axis == "depth":
            depth_points = _load_depth_points(
                db,
                tenant_id=tenant_id,
                well_run_id=well_run_id,
                selector=selector,
                payload=payload,
                depth_ranges=depth_ranges,
            )
            if axis_map is None:
                return []
            return _project_points(
                points=depth_points,
                map_points=axis_map.md_to_ts,
                max_gap=float(payload.axis_map.max_gap_meters),
            )

        time_points = _load_time_points(
            db,
            tenant_id=tenant_id,
            well_run_id=well_run_id,
            selector=selector,
            payload=payload,
            time_ranges=time_ranges,
        )
        if time_points or native_axis == "time" or axis_map is None:
            return time_points

        depth_points = _load_depth_points(
            db,
            tenant_id=tenant_id,
            well_run_id=well_run_id,
            selector=selector,
            payload=payload,
            depth_ranges=depth_ranges,
        )
        return _project_points(
            points=depth_points,
            map_points=axis_map.md_to_ts,
            max_gap=float(payload.axis_map.max_gap_meters),
        )

    if native_axis == "time":
        time_points = _load_time_points(
            db,
            tenant_id=tenant_id,
            well_run_id=well_run_id,
            selector=selector,
            payload=payload,
            time_ranges=time_ranges,
        )
        if axis_map is None:
            return []
        return _project_points(
            points=time_points,
            map_points=axis_map.ts_to_md,
            max_gap=float(payload.axis_map.max_gap_seconds),
        )

    depth_points = _load_depth_points(
        db,
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        selector=selector,
        payload=payload,
        depth_ranges=depth_ranges,
    )
    if depth_points or native_axis == "depth" or axis_map is None:
        return depth_points

    time_points = _load_time_points(
        db,
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        selector=selector,
        payload=payload,
        time_ranges=time_ranges,
    )
    return _project_points(
        points=time_points,
        map_points=axis_map.ts_to_md,
        max_gap=float(payload.axis_map.max_gap_seconds),
    )


def _find_bounds(
    *,
    axis: str,
    payload: WellRunAlignRequest,
    points_map: dict[str, list[_AlignedPoint]],
) -> tuple[float, float] | None:
    mins: list[float] = []
    maxs: list[float] = []
    for points in points_map.values():
        if not points:
            continue
        mins.append(points[0].x)
        maxs.append(points[-1].x)
    if not mins:
        return None

    if axis == "time":
        start = _to_epoch(payload.start) if payload.start else min(mins)
        end = _to_epoch(payload.end) if payload.end else max(maxs)
    else:
        start = payload.md_start if payload.md_start is not None else min(mins)
        end = payload.md_end if payload.md_end is not None else max(maxs)

    if end < start:
        return None
    return start, end


def _build_fixed_grid(
    *,
    start: float,
    end: float,
    step: float,
    max_rows: int,
) -> list[float]:
    if step <= 0:
        return []
    span = end - start
    if span < 0:
        return []
    estimated = int(math.floor(span / step)) + 1
    if estimated > max_rows:
        stride = int(math.ceil(estimated / max_rows))
        step *= stride
    grid: list[float] = []
    cursor = start
    while cursor <= end + 1e-9 and len(grid) < max_rows:
        grid.append(cursor)
        cursor += step
    return grid


def _build_anchor_grid(
    *,
    start: float,
    end: float,
    anchor_points: list[_AlignedPoint],
    max_rows: int,
) -> list[float]:
    if not anchor_points:
        return []
    scoped = [point.x for point in anchor_points if start <= point.x <= end]
    if not scoped:
        return []
    deduped: list[float] = []
    for value in scoped:
        if deduped and math.isclose(value, deduped[-1], rel_tol=0, abs_tol=1e-9):
            continue
        deduped.append(value)
    if len(deduped) <= max_rows:
        return deduped

    stride = int(math.ceil(len(deduped) / max_rows))
    sampled = deduped[::stride]
    if sampled and not math.isclose(sampled[-1], deduped[-1], rel_tol=0, abs_tol=1e-9):
        sampled.append(deduped[-1])
    return sampled[:max_rows]


def _align_point(
    *,
    points: list[_AlignedPoint],
    xs: list[float],
    x: float,
    method: str,
    max_gap: float,
) -> AlignedChannelValue:
    if not points:
        return AlignedChannelValue(value=None, quality_code=9, source=None)
    idx = bisect_left(xs, x)
    prev_p = points[idx - 1] if idx > 0 else None
    next_p = points[idx] if idx < len(points) else None

    if method == "linear" and prev_p is not None and next_p is not None and next_p.x > prev_p.x:
        left_gap = abs(x - prev_p.x)
        right_gap = abs(next_p.x - x)
        if left_gap <= max_gap and right_gap <= max_gap:
            ratio = (x - prev_p.x) / (next_p.x - prev_p.x)
            value = prev_p.value + ratio * (next_p.value - prev_p.value)
            source = prev_p.source if prev_p.source == next_p.source else "mixed"
            return AlignedChannelValue(value=value, quality_code=2, source=source)

    nearest, gap = _nearest_point(points=points, xs=xs, x=x, max_gap=max_gap)
    if nearest is None:
        return AlignedChannelValue(value=None, quality_code=9, source=None)

    quality = nearest.quality_code if gap < 1e-9 else 1
    return AlignedChannelValue(value=nearest.value, quality_code=quality, source=nearest.source)


def align_well_run_series(
    db: Session,
    *,
    tenant_id,
    well_run_id,
    payload: WellRunAlignRequest,
    time_ranges: list[tuple[float, float]] | None = None,
    depth_ranges: list[tuple[float, float]] | None = None,
    segment_meta: dict[str, Any] | None = None,
) -> WellRunAlignResponse:
    axis = payload.axis
    channels = _resolve_aliases(payload.channels)
    axis_map = _build_axis_map(
        db,
        tenant_id=tenant_id,
        well_run_id=well_run_id,
        config=payload.axis_map,
    )

    points_map: dict[str, list[_AlignedPoint]] = {}
    for alias, selector in channels:
        points = _load_channel_points(
            db,
            tenant_id=tenant_id,
            well_run_id=well_run_id,
            axis=axis,
            selector=selector,
            payload=payload,
            axis_map=axis_map,
            time_ranges=time_ranges,
            depth_ranges=depth_ranges,
        )
        points_map[alias] = points

    bounds = _find_bounds(axis=axis, payload=payload, points_map=points_map)
    if bounds is None:
        return WellRunAlignResponse(
            well_run_id=well_run_id,
            axis=axis,
            step_seconds=payload.step_seconds if axis == "time" else None,
            step_meters=payload.step_meters if axis == "depth" else None,
            rows=[],
            stats={
                "channels": len(channels),
                "channels_with_data": sum(1 for rows in points_map.values() if rows),
                "grid_points": 0,
                "grid_mode": payload.grid_mode,
                "axis_map": {
                    "enabled": payload.axis_map.enabled,
                    "source": axis_map.source if axis_map else None,
                    "channel": axis_map.channel if axis_map else None,
                    "count": len(axis_map.ts_to_md) if axis_map else 0,
                },
                "segment_filter": segment_meta or {"selected_segments": 0},
            },
        )

    start, end = bounds
    chosen_anchor_alias: str | None = None
    if payload.grid_mode == "anchor":
        candidate_alias = (payload.anchor_alias or "").strip() or None
        if candidate_alias and points_map.get(candidate_alias):
            chosen_anchor_alias = candidate_alias
        elif candidate_alias:
            chosen_anchor_alias = None
        else:
            for alias, _ in channels:
                if points_map.get(alias):
                    chosen_anchor_alias = alias
                    break
        grid = _build_anchor_grid(
            start=start,
            end=end,
            anchor_points=points_map.get(chosen_anchor_alias, []) if chosen_anchor_alias else [],
            max_rows=payload.max_rows,
        )
    else:
        grid = []

    if not grid:
        step = float(payload.step_seconds if axis == "time" else payload.step_meters)
        grid = _build_fixed_grid(start=start, end=end, step=step, max_rows=payload.max_rows)

    rows: list[WellRunAlignedRow] = []
    prepared_map: dict[str, tuple[list[_AlignedPoint], list[float]]] = {
        alias: (points_map.get(alias, []), [point.x for point in points_map.get(alias, [])])
        for alias, _ in channels
    }
    ts_to_md_xs: list[float] = []
    if axis == "time" and axis_map is not None:
        ts_to_md_xs = [point.x for point in axis_map.ts_to_md]

    filled_counts: dict[str, int] = {alias: 0 for alias, _ in channels}
    for x in grid:
        values: dict[str, AlignedChannelValue] = {}
        for alias, selector in channels:
            channel_points, xs = prepared_map.get(alias, ([], []))
            if axis == "time":
                max_gap = selector.max_gap_seconds or max(float(payload.step_seconds * 3), 5.0)
            else:
                max_gap = selector.max_gap_meters or max(payload.step_meters * 3, 0.1)
            aligned = _align_point(
                points=channel_points,
                xs=xs,
                x=x,
                method=selector.method,
                max_gap=max_gap,
            )
            if aligned.value is not None:
                filled_counts[alias] += 1
            values[alias] = aligned

        if axis == "time":
            md_value = None
            if axis_map is not None and ts_to_md_xs:
                projected_md, _ = _project_axis_value(
                    map_points=axis_map.ts_to_md,
                    map_xs=ts_to_md_xs,
                    x=x,
                    max_gap=float(payload.axis_map.max_gap_seconds),
                )
                md_value = round(projected_md, 6) if projected_md is not None else None
            rows.append(WellRunAlignedRow(ts=_from_epoch(x), md=md_value, values=values))
        else:
            rows.append(WellRunAlignedRow(md=round(x, 6), values=values))

    total_rows = len(rows)
    coverage = {
        alias: round((filled_counts[alias] / total_rows), 6) if total_rows > 0 else 0.0
        for alias, _ in channels
    }
    return WellRunAlignResponse(
        well_run_id=well_run_id,
        axis=axis,
        step_seconds=payload.step_seconds if axis == "time" else None,
        step_meters=payload.step_meters if axis == "depth" else None,
        rows=rows,
        stats={
            "channels": len(channels),
            "channels_with_data": sum(1 for rows_ in points_map.values() if rows_),
            "grid_points": len(rows),
            "grid_mode": payload.grid_mode,
            "anchor_alias": chosen_anchor_alias,
            "source_points": {alias: len(points_map.get(alias, [])) for alias, _ in channels},
            "coverage": coverage,
            "axis_start": _from_epoch(start).isoformat() if axis == "time" else start,
            "axis_end": _from_epoch(end).isoformat() if axis == "time" else end,
            "axis_map": {
                "enabled": payload.axis_map.enabled,
                "source": axis_map.source if axis_map else None,
                "channel": axis_map.channel if axis_map else None,
                "count": len(axis_map.ts_to_md) if axis_map else 0,
            },
            "segment_filter": segment_meta or {"selected_segments": 0},
        },
    )
