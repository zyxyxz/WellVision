from __future__ import annotations

from collections.abc import Callable
from decimal import Decimal
from statistics import mean
from typing import Iterable, Sequence

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.algorithms import load_algorithms
from app.algorithms.base import AlgorithmResult
from app.core.config import get_settings
from app.models import AlgorithmDefinition, AnalysisRun
from app.schemas.analysis import (
    AlgorithmInfo,
    AlgorithmParam,
    AnalysisRunResponse,
    FieldSummary,
    SeriesPoint,
    SeriesQuery,
)


NUMERIC_VALUE_REGEX = r"^[-+]?((\d+(\.\d*)?)|(\.\d+))([eE][-+]?\d+)?$"
DATE_BIN_ORIGIN = "TIMESTAMPTZ '2000-01-01 00:00:00+00'"
METRIC_ROLLUP_1M = "event_metrics_rollup_1m_v2"

SQL_PUSH_DOWN_ALGORITHMS = {
    "moving_average",
    "rolling_std",
    "rolling_range",
    "rate_of_change",
    "zscore_anomaly",
    "linear_trend",
}


def _as_float(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _event_where_sql(*, tenant_id, query: SeriesQuery) -> tuple[str, dict]:
    clauses = ["tenant_id = :tenant_id", "payload ? :field"]
    params: dict[str, object] = {"tenant_id": tenant_id, "field": query.field}
    if query.warehouse_id is not None:
        clauses.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = query.warehouse_id
    if query.well_run_id is not None:
        clauses.append("well_run_id = :well_run_id")
        params["well_run_id"] = query.well_run_id
    if query.start is not None:
        clauses.append("created_at >= :start")
        params["start"] = query.start
    if query.end is not None:
        clauses.append("created_at <= :end")
        params["end"] = query.end
    return " AND ".join(clauses), params


def _bucket_expr(*, use_timescale: bool) -> str:
    if use_timescale:
        return "time_bucket(make_interval(mins => :bucket_minutes), created_at)"
    return (
        "date_bin(make_interval(mins => :bucket_minutes), created_at, "
        "TIMESTAMPTZ '2000-01-01 00:00:00+00')"
    )


def _build_event_series_sql(
    *,
    tenant_id,
    query: SeriesQuery,
    apply_limit: bool,
    use_timescale: bool,
) -> tuple[str, dict]:
    where_sql, params = _event_where_sql(tenant_id=tenant_id, query=query)
    params["numeric_regex"] = NUMERIC_VALUE_REGEX

    value_expr = """
    CASE
      WHEN jsonb_typeof(payload -> :field) = 'number' THEN (payload ->> :field)::double precision
      WHEN jsonb_typeof(payload -> :field) = 'string'
        AND (payload ->> :field) ~ :numeric_regex THEN (payload ->> :field)::double precision
      ELSE NULL
    END
    """

    if query.bucket_minutes is not None:
        params["bucket_minutes"] = max(1, min(int(query.bucket_minutes), 43200))
        sql = f"""
        SELECT bucket AS ts, AVG(value)::double precision AS value
        FROM (
            SELECT {_bucket_expr(use_timescale=use_timescale)} AS bucket,
                   {value_expr} AS value
            FROM events
            WHERE {where_sql}
        ) src
        WHERE value IS NOT NULL
        GROUP BY bucket
        """
        if apply_limit:
            sql += "\nORDER BY bucket ASC"
    else:
        sql = f"""
        SELECT ts, value
        FROM (
            SELECT created_at AS ts,
                   {value_expr} AS value
            FROM events
            WHERE {where_sql}
        ) src
        WHERE value IS NOT NULL
        """
        if apply_limit:
            sql += "\nORDER BY ts ASC"

    if apply_limit:
        params["limit"] = max(10, min(int(query.limit), 20000))
        sql += "\nLIMIT :limit"

    return sql, params


def _metric_where_sql(*, tenant_id, query: SeriesQuery, time_column: str) -> tuple[str, dict]:
    clauses = ["tenant_id = :tenant_id", "field = :field"]
    params: dict[str, object] = {"tenant_id": tenant_id, "field": query.field}
    if query.warehouse_id is not None:
        clauses.append("warehouse_id = :warehouse_id")
        params["warehouse_id"] = query.warehouse_id
    if query.well_run_id is not None:
        clauses.append("well_run_id = :well_run_id")
        params["well_run_id"] = query.well_run_id
    if query.start is not None:
        clauses.append(f"{time_column} >= :start")
        params["start"] = query.start
    if query.end is not None:
        clauses.append(f"{time_column} <= :end")
        params["end"] = query.end
    return " AND ".join(clauses), params


def _build_metric_series_sql(
    *,
    tenant_id,
    query: SeriesQuery,
    apply_limit: bool,
    use_cagg: bool,
) -> tuple[str, dict]:
    if query.bucket_minutes is not None and use_cagg:
        bucket_minutes = max(1, min(int(query.bucket_minutes), 43200))
        where_sql, params = _metric_where_sql(
            tenant_id=tenant_id,
            query=query,
            time_column="bucket",
        )
        params["bucket_minutes"] = bucket_minutes
        sql = f"""
        SELECT bkt AS ts,
               (SUM(sum_value) / NULLIF(SUM(point_count), 0))::double precision AS value
        FROM (
            SELECT
                date_bin(
                    make_interval(mins => :bucket_minutes),
                    bucket,
                    {DATE_BIN_ORIGIN}
                ) AS bkt,
                point_count,
                sum_value
            FROM {METRIC_ROLLUP_1M}
            WHERE {where_sql}
        ) agg
        GROUP BY bkt
        """
        if apply_limit:
            params["limit"] = max(10, min(int(query.limit), 20000))
            sql += "\nORDER BY bkt ASC\nLIMIT :limit"
        return sql, params

    where_sql, params = _metric_where_sql(
        tenant_id=tenant_id,
        query=query,
        time_column="created_at",
    )
    if query.bucket_minutes is None:
        sql = f"""
        SELECT created_at AS ts, value
        FROM event_metrics
        WHERE {where_sql}
        """
        if apply_limit:
            params["limit"] = max(10, min(int(query.limit), 20000))
            sql += "\nORDER BY created_at ASC\nLIMIT :limit"
        return sql, params

    params["bucket_minutes"] = max(1, min(int(query.bucket_minutes), 43200))
    sql = f"""
    SELECT bkt AS ts, AVG(value)::double precision AS value
    FROM (
        SELECT
            date_bin(
                make_interval(mins => :bucket_minutes),
                created_at,
                {DATE_BIN_ORIGIN}
            ) AS bkt,
            value
        FROM event_metrics
        WHERE {where_sql}
    ) src
    GROUP BY bkt
    """
    if apply_limit:
        params["limit"] = max(10, min(int(query.limit), 20000))
        sql += "\nORDER BY bkt ASC\nLIMIT :limit"
    return sql, params


def _metric_source_complete(db: Session, *, tenant_id, query: SeriesQuery) -> bool:
    metric_where_sql, metric_params = _metric_where_sql(
        tenant_id=tenant_id,
        query=query,
        time_column="created_at",
    )
    metric_sql = f"""
    SELECT COUNT(*)::bigint
    FROM event_metrics
    WHERE {metric_where_sql}
    """
    try:
        metric_count = int(_execute_stmt(db, metric_sql, metric_params).scalar() or 0)
    except Exception as exc:  # noqa: BLE001 - metric storage might not exist during migration.
        if _is_metric_storage_missing(exc):
            return False
        raise

    where_sql, event_params = _event_where_sql(tenant_id=tenant_id, query=query)
    event_params["numeric_regex"] = NUMERIC_VALUE_REGEX
    value_expr = """
    CASE
      WHEN jsonb_typeof(payload -> :field) = 'number' THEN (payload ->> :field)::double precision
      WHEN jsonb_typeof(payload -> :field) = 'string'
        AND (payload ->> :field) ~ :numeric_regex THEN (payload ->> :field)::double precision
      ELSE NULL
    END
    """
    event_sql = f"""
    SELECT COUNT(*)::bigint
    FROM (
        SELECT {value_expr} AS value
        FROM events
        WHERE {where_sql}
    ) src
    WHERE value IS NOT NULL
    """
    event_count = int(_execute_stmt(db, event_sql, event_params).scalar() or 0)
    if event_count <= 0:
        return True
    return metric_count >= event_count


def _is_time_bucket_missing(exc: Exception) -> bool:
    message = str(exc).lower()
    return "time_bucket" in message and ("does not exist" in message or "undefined function" in message)


def _is_missing_relation(exc: Exception, relation_name: str) -> bool:
    message = str(exc).lower()
    relation = relation_name.lower()
    return relation in message and ("does not exist" in message or "undefined table" in message)


def _is_metric_storage_missing(exc: Exception) -> bool:
    return _is_missing_relation(exc, "event_metrics") or _is_missing_relation(exc, METRIC_ROLLUP_1M)


def _execute_stmt(db: Session, sql: str, params: dict):
    # Use a SAVEPOINT so fallback retries are not blocked by aborted transactions.
    with db.begin_nested():
        return db.execute(text(sql), params)


def _execute_with_bucket_fallback(
    db: Session,
    *,
    query: SeriesQuery,
    builder: Callable[[bool], tuple[str, dict]],
):
    settings = get_settings()
    use_timescale = bool(query.bucket_minutes and settings.timescaledb_enabled)
    sql, params = builder(use_timescale)
    try:
        return _execute_stmt(db, sql, params)
    except Exception as exc:  # noqa: BLE001 - retry with date_bin if time_bucket is unavailable.
        if use_timescale and _is_time_bucket_missing(exc):
            sql, params = builder(False)
            return _execute_stmt(db, sql, params)
        raise


def _execute_metric_query(
    db: Session,
    *,
    query: SeriesQuery,
    builder: Callable[[bool], tuple[str, dict]],
):
    use_cagg = bool(query.bucket_minutes)
    sql, params = builder(use_cagg)
    try:
        return _execute_stmt(db, sql, params)
    except Exception as exc:  # noqa: BLE001 - retry without cagg if relation is missing.
        if use_cagg and _is_missing_relation(exc, METRIC_ROLLUP_1M):
            sql, params = builder(False)
            return _execute_stmt(db, sql, params)
        raise


def _execute_metric_then_event_rows(
    db: Session,
    *,
    query: SeriesQuery,
    metric_builder: Callable[[bool], tuple[str, dict]],
    event_builder: Callable[[bool], tuple[str, dict]],
) -> tuple[list, str]:
    metric_rows: list = []
    try:
        metric_rows = _execute_metric_query(
            db,
            query=query,
            builder=metric_builder,
        ).fetchall()
    except Exception as exc:  # noqa: BLE001 - fall back only when metric storage is not ready.
        if not _is_metric_storage_missing(exc):
            raise
    if metric_rows:
        return metric_rows, "timeseries_sql_metric"
    event_rows = _execute_with_bucket_fallback(
        db,
        query=query,
        builder=event_builder,
    ).fetchall()
    return event_rows, "timeseries_sql_event_fallback"


def _execute_metric_then_event_one(
    db: Session,
    *,
    query: SeriesQuery,
    metric_builder: Callable[[bool], tuple[str, dict]],
    event_builder: Callable[[bool], tuple[str, dict]],
    metric_has_data: Callable[[object], bool] | None = None,
) -> tuple[object | None, str]:
    metric_row = None
    try:
        metric_row = _execute_metric_query(
            db,
            query=query,
            builder=metric_builder,
        ).fetchone()
    except Exception as exc:  # noqa: BLE001 - fall back only when metric storage is not ready.
        if not _is_metric_storage_missing(exc):
            raise
    if metric_row is not None and (metric_has_data(metric_row) if metric_has_data else True):
        return metric_row, "timeseries_sql_metric"
    event_row = _execute_with_bucket_fallback(
        db,
        query=query,
        builder=event_builder,
    ).fetchone()
    return event_row, "timeseries_sql_event_fallback"


def _rows_to_points(rows) -> list[SeriesPoint]:
    points: list[SeriesPoint] = []
    for row in rows:
        ts = row[0]
        value = _as_float(row[1])
        if ts is None or value is None:
            continue
        points.append(SeriesPoint(ts=ts, value=value))
    return points


def load_series(db: Session, *, tenant_id, query: SeriesQuery) -> list[SeriesPoint]:
    metric_complete = _metric_source_complete(db, tenant_id=tenant_id, query=query)
    if not metric_complete:
        rows = _execute_with_bucket_fallback(
            db,
            query=query,
            builder=lambda use_timescale: _build_event_series_sql(
                tenant_id=tenant_id,
                query=query,
                apply_limit=True,
                use_timescale=use_timescale,
            ),
        ).fetchall()
        return _rows_to_points(rows)

    rows, _ = _execute_metric_then_event_rows(
        db,
        query=query,
        metric_builder=lambda use_cagg: _build_metric_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=True,
            use_cagg=use_cagg,
        ),
        event_builder=lambda use_timescale: _build_event_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=True,
            use_timescale=use_timescale,
        ),
    )
    return _rows_to_points(rows)


def summarize_query(db: Session, *, tenant_id, query: SeriesQuery) -> dict[str, float | int]:
    def _metric_build(use_cagg: bool) -> tuple[str, dict]:
        series_sql, params = _build_metric_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=False,
            use_cagg=use_cagg,
        )
        sql = f"""
        WITH series AS (
            {series_sql}
        )
        SELECT
            COUNT(*)::bigint AS count,
            MIN(value)::double precision AS min,
            MAX(value)::double precision AS max,
            AVG(value)::double precision AS avg,
            COALESCE(STDDEV_POP(value), 0)::double precision AS stddev,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY value)::double precision AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY value)::double precision AS p95
        FROM series
        """
        return sql, params

    def _event_build(use_timescale: bool) -> tuple[str, dict]:
        series_sql, params = _build_event_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=False,
            use_timescale=use_timescale,
        )
        sql = f"""
        WITH series AS (
            {series_sql}
        )
        SELECT
            COUNT(*)::bigint AS count,
            MIN(value)::double precision AS min,
            MAX(value)::double precision AS max,
            AVG(value)::double precision AS avg,
            COALESCE(STDDEV_POP(value), 0)::double precision AS stddev,
            percentile_cont(0.50) WITHIN GROUP (ORDER BY value)::double precision AS p50,
            percentile_cont(0.95) WITHIN GROUP (ORDER BY value)::double precision AS p95
        FROM series
        """
        return sql, params

    metric_complete = _metric_source_complete(db, tenant_id=tenant_id, query=query)
    if metric_complete:
        row, _ = _execute_metric_then_event_one(
            db,
            query=query,
            metric_builder=_metric_build,
            event_builder=_event_build,
            metric_has_data=lambda r: int(r[0] or 0) > 0,
        )
    else:
        row = _execute_with_bucket_fallback(
            db,
            query=query,
            builder=_event_build,
        ).fetchone()
    count = int(row[0] or 0) if row else 0

    if not row:
        return {"count": 0}
    if count <= 0:
        return {"count": 0}
    return {
        "count": count,
        "min": _as_float(row[1]) or 0.0,
        "max": _as_float(row[2]) or 0.0,
        "avg": _as_float(row[3]) or 0.0,
        "stddev": _as_float(row[4]) or 0.0,
        "p50": _as_float(row[5]) or 0.0,
        "p95": _as_float(row[6]) or 0.0,
    }


def summarize(points: Iterable[SeriesPoint]) -> dict[str, float | int]:
    pts = list(points)
    if not pts:
        return {"count": 0}
    values = [p.value for p in pts]
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": mean(values),
    }


def discover_numeric_fields(
    db: Session, *, tenant_id, limit: int = 1000, warehouse_id=None, well_run_id=None
) -> list[FieldSummary]:
    sample_limit = max(50, min(limit, 5000))
    where = "tenant_id = :tenant_id"
    params: dict[str, object] = {
        "tenant_id": tenant_id,
        "sample_limit": sample_limit,
    }
    if warehouse_id is not None:
        where += " AND warehouse_id = :warehouse_id"
        params["warehouse_id"] = warehouse_id
    if well_run_id is not None:
        where += " AND well_run_id = :well_run_id"
        params["well_run_id"] = well_run_id

    metric_stmt = text(
        f"""
        WITH sampled AS (
            SELECT field
            FROM event_metrics
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :sample_limit
        )
        SELECT field, COUNT(*)::bigint AS cnt
        FROM sampled
        GROUP BY field
        ORDER BY cnt DESC, field ASC
        """
    )
    try:
        metric_rows = db.execute(metric_stmt, params).fetchall()
    except Exception as exc:  # noqa: BLE001 - use event payload path when metric table is unavailable.
        if not _is_metric_storage_missing(exc):
            raise
        metric_rows = []
    if metric_rows:
        return [FieldSummary(name=row[0], count=int(row[1])) for row in metric_rows]

    params["numeric_regex"] = NUMERIC_VALUE_REGEX

    stmt = text(
        f"""
        WITH sampled AS (
            SELECT payload
            FROM events
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT :sample_limit
        ),
        expanded AS (
            SELECT
                kv.key AS key,
                kv.value #>> '{{}}' AS raw_value,
                jsonb_typeof(kv.value) AS value_type
            FROM sampled s
            CROSS JOIN LATERAL jsonb_each(s.payload) AS kv(key, value)
        )
        SELECT key, COUNT(*)::bigint AS cnt
        FROM expanded
        WHERE value_type = 'number'
           OR (value_type = 'string' AND raw_value ~ :numeric_regex)
        GROUP BY key
        ORDER BY cnt DESC, key ASC
        """
    )
    rows = db.execute(stmt, params).fetchall()
    return [FieldSummary(name=row[0], count=int(row[1])) for row in rows]


def _downsample(points: Sequence[SeriesPoint], max_points: int = 600) -> list[SeriesPoint]:
    if len(points) <= max_points:
        return list(points)
    step = max(1, len(points) // max_points)
    sampled = [points[i] for i in range(0, len(points), step)]
    if sampled[-1].ts != points[-1].ts:
        sampled.append(points[-1])
    return sampled[: max_points + 1]


def _series_to_json(points: Sequence[SeriesPoint]) -> list[dict]:
    return [{"ts": p.ts.isoformat(), "value": p.value} for p in points]

ALGORITHMS = load_algorithms()

def _params_from_config(config: dict) -> list[AlgorithmParam]:
    raw_params = config.get("params") or []
    params: list[AlgorithmParam] = []
    for raw in raw_params:
        try:
            params.append(AlgorithmParam(**raw))
        except Exception:
            continue
    return params


def list_algorithms(db: Session | None = None, tenant_id=None) -> list[AlgorithmInfo]:
    infos = []
    for spec in ALGORITHMS.values():
        info = AlgorithmInfo(**spec.info.model_dump())
        infos.append(info)
    if db is None or tenant_id is None:
        return infos
    stmt = select(AlgorithmDefinition).where(
        AlgorithmDefinition.tenant_id == tenant_id, AlgorithmDefinition.enabled.is_(True)
    )
    rows = db.execute(stmt).scalars().all()
    for row in rows:
        params = _params_from_config(row.config or {})
        infos.append(
            AlgorithmInfo(
                id=row.key,
                name=row.name,
                description=row.description or "",
                params=params,
                kind=row.kind,
            )
        )
    return infos


def run_algorithm(algorithm_id: str, series: Sequence[SeriesPoint], params: dict) -> AlgorithmResult:
    if algorithm_id not in ALGORITHMS:
        raise KeyError(f"Unknown algorithm: {algorithm_id}")
    fn = ALGORITHMS[algorithm_id].fn
    return fn(series, params)


def run_algorithm_pushdown(
    db: Session,
    *,
    tenant_id,
    algorithm_id: str,
    query: SeriesQuery,
    params: dict,
) -> AlgorithmResult | None:
    if algorithm_id not in SQL_PUSH_DOWN_ALGORITHMS:
        return None

    metric_complete = _metric_source_complete(db, tenant_id=tenant_id, query=query)

    def _base_metric_series_sql(use_rollup: bool) -> tuple[str, dict]:
        return _build_metric_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=True,
            use_cagg=use_rollup,
        )

    def _base_event_series_sql(use_timescale: bool) -> tuple[str, dict]:
        return _build_event_series_sql(
            tenant_id=tenant_id,
            query=query,
            apply_limit=True,
            use_timescale=use_timescale,
        )

    def _execute_rows(
        transform: Callable[[str, dict], tuple[str, dict]],
    ) -> tuple[list, str]:
        if not metric_complete:
            rows = _execute_with_bucket_fallback(
                db,
                query=query,
                builder=lambda use_timescale: transform(*_base_event_series_sql(use_timescale)),
            ).fetchall()
            return rows, "timeseries_sql_event_fallback"
        return _execute_metric_then_event_rows(
            db,
            query=query,
            metric_builder=lambda use_rollup: transform(*_base_metric_series_sql(use_rollup)),
            event_builder=lambda use_timescale: transform(*_base_event_series_sql(use_timescale)),
        )

    def _execute_one(
        transform: Callable[[str, dict], tuple[str, dict]],
        metric_has_data: Callable[[object], bool] | None = None,
    ) -> tuple[object | None, str]:
        if not metric_complete:
            row = _execute_with_bucket_fallback(
                db,
                query=query,
                builder=lambda use_timescale: transform(*_base_event_series_sql(use_timescale)),
            ).fetchone()
            return row, "timeseries_sql_event_fallback"
        return _execute_metric_then_event_one(
            db,
            query=query,
            metric_builder=lambda use_rollup: transform(*_base_metric_series_sql(use_rollup)),
            event_builder=lambda use_timescale: transform(*_base_event_series_sql(use_timescale)),
            metric_has_data=metric_has_data,
        )

    if algorithm_id == "moving_average":
        window = max(2, min(int(params.get("window", 20)), 500))

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            run_params["window_preceding"] = window - 1
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                ts,
                AVG(value) OVER (
                    ORDER BY ts
                    ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                )::double precision AS value
            FROM base
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        return AlgorithmResult(
            result_series=points,
            metrics={"window": window, "count": len(points), "execution_mode": execution_mode},
        )

    if algorithm_id == "rolling_std":
        window = max(2, min(int(params.get("window", 20)), 500))

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            run_params["window_preceding"] = window - 1
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                ts,
                COALESCE(
                    STDDEV_POP(value) OVER (
                        ORDER BY ts
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    ),
                    0
                )::double precision AS value
            FROM base
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        avg_std = mean([p.value for p in points]) if points else 0.0
        return AlgorithmResult(
            result_series=points,
            metrics={"window": window, "avg_std": avg_std, "execution_mode": execution_mode},
        )

    if algorithm_id == "rolling_range":
        window = max(2, min(int(params.get("window", 20)), 500))

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            run_params["window_preceding"] = window - 1
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                ts,
                (
                    MAX(value) OVER (
                        ORDER BY ts
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    ) -
                    MIN(value) OVER (
                        ORDER BY ts
                        ROWS BETWEEN :window_preceding PRECEDING AND CURRENT ROW
                    )
                )::double precision AS value
            FROM base
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        avg_range = mean([p.value for p in points]) if points else 0.0
        return AlgorithmResult(
            result_series=points,
            metrics={"window": window, "avg_range": avg_range, "execution_mode": execution_mode},
        )

    if algorithm_id == "rate_of_change":

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            sql = f"""
            WITH base AS (
                {base_sql}
            ),
            ordered AS (
                SELECT
                    ts,
                    value,
                    LAG(ts) OVER (ORDER BY ts) AS prev_ts,
                    LAG(value) OVER (ORDER BY ts) AS prev_value
                FROM base
            )
            SELECT
                ts,
                CASE
                    WHEN prev_ts IS NULL THEN NULL
                    WHEN EXTRACT(EPOCH FROM (ts - prev_ts)) <= 0 THEN NULL
                    ELSE (value - prev_value) / EXTRACT(EPOCH FROM (ts - prev_ts))
                END::double precision AS value
            FROM ordered
            WHERE prev_ts IS NOT NULL
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        values = [p.value for p in points]
        return AlgorithmResult(
            result_series=points,
            metrics={
                "avg_rate": mean(values) if values else 0.0,
                "max_rate": max(values, default=0.0),
                "count": len(points),
                "execution_mode": execution_mode,
            },
        )

    if algorithm_id == "zscore_anomaly":
        threshold = max(1.0, min(float(params.get("threshold", 3.0)), 10.0))

        def _stats_transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                COUNT(*)::bigint AS count,
                AVG(value)::double precision AS mean_value,
                COALESCE(STDDEV_POP(value), 0)::double precision AS std_value
            FROM base
            """
            return sql, run_params

        stats_row, stats_mode = _execute_one(
            _stats_transform,
            metric_has_data=lambda row: int(row[0] or 0) > 0,
        )
        count = int(stats_row[0] or 0) if stats_row else 0
        mean_value = _as_float(stats_row[1]) if stats_row else 0.0
        std_value = _as_float(stats_row[2]) if stats_row else 0.0

        if count <= 0 or not std_value:
            return AlgorithmResult(
                result_series=[],
                metrics={
                    "anomalies": 0,
                    "threshold": threshold,
                    "mean": mean_value or 0.0,
                    "std": 0.0,
                    "execution_mode": stats_mode,
                },
            )

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            run_params.update(
                {
                    "threshold": threshold,
                    "mean_value": mean_value,
                    "std_value": std_value,
                }
            )
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                ts,
                value
            FROM base
            WHERE ABS((value - :mean_value) / :std_value) >= :threshold
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        return AlgorithmResult(
            result_series=points,
            metrics={
                "anomalies": len(points),
                "threshold": threshold,
                "mean": mean_value or 0.0,
                "std": std_value,
                "execution_mode": execution_mode,
            },
        )

    if algorithm_id == "linear_trend":

        def _stats_transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                COUNT(*)::bigint AS count,
                COALESCE(REGR_SLOPE(value, EXTRACT(EPOCH FROM ts)), 0)::double precision AS slope,
                COALESCE(REGR_INTERCEPT(value, EXTRACT(EPOCH FROM ts)), 0)::double precision AS intercept,
                COALESCE(REGR_R2(value, EXTRACT(EPOCH FROM ts)), 0)::double precision AS r2
            FROM base
            """
            return sql, run_params

        stats_row, stats_mode = _execute_one(
            _stats_transform,
            metric_has_data=lambda row: int(row[0] or 0) > 0,
        )
        count = int(stats_row[0] or 0) if stats_row else 0
        slope = _as_float(stats_row[1]) if stats_row else 0.0
        intercept = _as_float(stats_row[2]) if stats_row else 0.0
        r2 = _as_float(stats_row[3]) if stats_row else 0.0

        if count <= 0:
            return AlgorithmResult(
                result_series=[],
                metrics={
                    "slope": 0.0,
                    "intercept": 0.0,
                    "r2": 0.0,
                    "execution_mode": stats_mode,
                },
            )

        def _transform(base_sql: str, query_params: dict) -> tuple[str, dict]:
            run_params = dict(query_params)
            run_params.update({"slope": slope, "intercept": intercept})
            sql = f"""
            WITH base AS (
                {base_sql}
            )
            SELECT
                ts,
                (:slope * EXTRACT(EPOCH FROM ts) + :intercept)::double precision AS value
            FROM base
            ORDER BY ts ASC
            """
            return sql, run_params

        rows, execution_mode = _execute_rows(_transform)
        points = _rows_to_points(rows)
        return AlgorithmResult(
            result_series=points,
            metrics={
                "slope": slope or 0.0,
                "intercept": intercept or 0.0,
                "r2": r2 or 0.0,
                "execution_mode": execution_mode,
            },
        )

    return None


def run_custom_algorithm(
    db: Session,
    *,
    tenant_id,
    algorithm_id: str,
    series: Sequence[SeriesPoint],
    params: dict,
) -> AlgorithmResult:
    stmt = select(AlgorithmDefinition).where(
        AlgorithmDefinition.tenant_id == tenant_id,
        AlgorithmDefinition.key == algorithm_id,
        AlgorithmDefinition.enabled.is_(True),
    )
    row = db.execute(stmt).scalar_one_or_none()
    if row is None:
        raise KeyError(f"Unknown algorithm: {algorithm_id}")

    config = row.config or {}
    points_payload = [{"ts": p.ts.isoformat(), "value": p.value} for p in series]

    if row.kind == "http":
        import json
        import urllib.request

        url = config.get("url")
        if not url:
            raise ValueError("HTTP algorithm requires config.url")
        method = (config.get("method") or "POST").upper()
        headers = config.get("headers") or {}
        timeout = float(config.get("timeout_seconds") or 15)
        payload = json.dumps({"series": points_payload, "params": params}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, method=method)
        req.add_header("Content-Type", "application/json")
        for key, value in headers.items():
            req.add_header(str(key), str(value))
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return _parse_custom_result(data)

    if row.kind == "workflow":
        steps = config.get("steps") or []
        result_series = list(series)
        combined_metrics: dict[str, float | int | str] = {"steps": len(steps)}
        for idx, step in enumerate(steps):
            step_id = step.get("algorithm_id")
            step_params = step.get("params") or {}
            if not step_id:
                continue
            if step_id in ALGORITHMS:
                step_result = run_algorithm(step_id, result_series, step_params)
            else:
                step_result = run_custom_algorithm(
                    db,
                    tenant_id=tenant_id,
                    algorithm_id=step_id,
                    series=result_series,
                    params=step_params,
                )
            result_series = step_result.result_series
            combined_metrics[f"step_{idx+1}_{step_id}"] = step_result.metrics
        return AlgorithmResult(result_series=result_series, metrics=combined_metrics)

    # python
    code = config.get("code")
    if not code:
        raise ValueError("Python algorithm requires config.code")
    local_env: dict[str, object] = {}
    import math
    import statistics

    safe_builtins = {
        "min": min,
        "max": max,
        "sum": sum,
        "len": len,
        "abs": abs,
        "float": float,
        "int": int,
        "range": range,
        "enumerate": enumerate,
        "list": list,
        "dict": dict,
        "sorted": sorted,
    }
    global_env = {"__builtins__": safe_builtins, "math": math, "statistics": statistics}
    exec(code, global_env, local_env)
    run_fn = local_env.get("run")
    if not callable(run_fn):
        raise ValueError("Python algorithm must define a run(points, params) function.")
    result = run_fn(points_payload, params)
    return _parse_custom_result(result)


def _parse_custom_result(result) -> AlgorithmResult:
    if not isinstance(result, dict):
        raise ValueError("Algorithm result must be a dict with result_series and metrics.")
    series_data = result.get("result_series") or []
    metrics = result.get("metrics") or {}
    raw_points = result.get("result_points") or []
    x_axis = result.get("x_axis")
    points: list[SeriesPoint] = []
    for item in series_data:
        if isinstance(item, dict):
            ts = item.get("ts")
            value = item.get("value")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            ts, value = item[0], item[1]
        else:
            continue
        if ts is None or value is None:
            continue
        points.append(SeriesPoint(ts=ts, value=float(value)))
    parsed_points: list[dict[str, float]] = []
    for item in raw_points:
        if isinstance(item, dict):
            x = item.get("x")
            y = item.get("y")
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            x, y = item[0], item[1]
        else:
            continue
        if x is None or y is None:
            continue
        parsed_points.append({"x": float(x), "y": float(y)})
    return AlgorithmResult(result_series=points, metrics=metrics, result_points=parsed_points, x_axis=x_axis)


def persist_analysis_run(
    db: Session,
    *,
    tenant_id,
    user_id,
    warehouse_id,
    algorithm_id: str,
    field: str,
    params: dict,
    base_stats: dict,
    metrics: dict,
    result_series: Sequence[SeriesPoint],
) -> AnalysisRun:
    sampled = _downsample(result_series, max_points=600)
    run = AnalysisRun(
        tenant_id=tenant_id,
        warehouse_id=warehouse_id,
        user_id=user_id,
        algorithm_id=algorithm_id,
        field=field,
        params_json=params or {},
        base_stats_json=base_stats or {},
        metrics_json=metrics or {},
        result_series_json=_series_to_json(sampled),
    )
    db.add(run)
    db.flush()
    return run


def list_analysis_runs(
    db: Session,
    *,
    tenant_id,
    warehouse_id=None,
    algorithm_id: str | None = None,
    field: str | None = None,
    limit: int = 100,
) -> list[AnalysisRunResponse]:
    stmt = select(AnalysisRun).where(AnalysisRun.tenant_id == tenant_id)
    if warehouse_id is not None:
        stmt = stmt.where(AnalysisRun.warehouse_id == warehouse_id)
    if algorithm_id:
        stmt = stmt.where(AnalysisRun.algorithm_id == algorithm_id)
    if field:
        stmt = stmt.where(AnalysisRun.field == field)
    stmt = stmt.order_by(AnalysisRun.created_at.desc()).limit(max(10, min(limit, 500)))
    rows = db.execute(stmt).scalars().all()
    return [
        AnalysisRunResponse(
            id=row.id,
            algorithm_id=row.algorithm_id,  # type: ignore[arg-type]
            field=row.field,
            warehouse_id=row.warehouse_id,
            params=row.params_json or {},
            base_stats=row.base_stats_json or {},
            metrics=row.metrics_json or {},
            created_at=row.created_at,
        )
        for row in rows
    ]


def get_analysis_run(db: Session, *, tenant_id, run_id) -> AnalysisRun:
    stmt = select(AnalysisRun).where(AnalysisRun.tenant_id == tenant_id, AnalysisRun.id == run_id)
    run = db.execute(stmt).scalar_one_or_none()
    if run is None:
        raise KeyError("Analysis run not found")
    return run
