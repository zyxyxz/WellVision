from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine


def _existing_columns(engine: Engine, table: str) -> set[str]:
    query = text(
        """
        SELECT column_name
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = :table
        """
    )
    with engine.begin() as conn:
        rows = conn.execute(query, {"table": table}).fetchall()
    return {row[0] for row in rows}


def _ensure_columns(engine: Engine, table: str, columns: dict[str, str]) -> None:
    existing = _existing_columns(engine, table)
    if not existing:
        return
    with engine.begin() as conn:
        for name, ddl in columns.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _ensure_event_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_tenant_created_idx "
                "ON events (tenant_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_tenant_warehouse_created_idx "
                "ON events (tenant_id, warehouse_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_warehouse_created_idx "
                "ON events (warehouse_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_tenant_source_created_idx "
                "ON events (tenant_id, source, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_tenant_well_run_created_idx "
                "ON events (tenant_id, well_run_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_created_brin_idx "
                "ON events USING BRIN (created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS events_payload_gin_idx "
                "ON events USING GIN (payload)"
            )
        )


def _ensure_event_metric_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_tenant_field_created_idx "
                "ON event_metrics (tenant_id, field, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_tenant_warehouse_field_created_idx "
                "ON event_metrics (tenant_id, warehouse_id, field, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_tenant_well_channel_created_idx "
                "ON event_metrics (tenant_id, well_run_id, channel, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_tenant_well_source_channel_created_idx "
                "ON event_metrics (tenant_id, well_run_id, source, channel, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_event_id_idx "
                "ON event_metrics (event_id)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_tenant_well_md_idx "
                "ON event_metrics (tenant_id, well_run_id, md)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_created_brin_idx "
                "ON event_metrics USING BRIN (created_at)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS event_metrics_md_brin_idx "
                "ON event_metrics USING BRIN (md)"
            )
        )


def _ensure_event_metric_rollup_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        old_exists = conn.execute(text("SELECT to_regclass('public.event_metrics_rollup_1m')")).scalar()
        if old_exists:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_tenant_field_bucket_idx "
                    "ON event_metrics_rollup_1m (tenant_id, field, bucket DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_tenant_warehouse_field_bucket_idx "
                    "ON event_metrics_rollup_1m (tenant_id, warehouse_id, field, bucket DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_bucket_brin_idx "
                    "ON event_metrics_rollup_1m USING BRIN (bucket)"
                )
            )

        new_exists = conn.execute(text("SELECT to_regclass('public.event_metrics_rollup_1m_v2')")).scalar()
        if new_exists:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_v2_tenant_field_bucket_idx "
                    "ON event_metrics_rollup_1m_v2 (tenant_id, field, bucket DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_v2_tenant_warehouse_well_field_bucket_idx "
                    "ON event_metrics_rollup_1m_v2 (tenant_id, warehouse_id, well_run_id, field, bucket DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_v2_tenant_well_source_field_bucket_idx "
                    "ON event_metrics_rollup_1m_v2 (tenant_id, well_run_id, source, field, bucket DESC)"
                )
            )
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS event_metrics_rollup_1m_v2_bucket_brin_idx "
                    "ON event_metrics_rollup_1m_v2 USING BRIN (bucket)"
                )
            )


def _ensure_well_run_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS well_runs_tenant_created_idx "
                "ON well_runs (tenant_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS well_runs_tenant_warehouse_created_idx "
                "ON well_runs (tenant_id, warehouse_id, created_at DESC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS well_runs_tenant_status_created_idx "
                "ON well_runs (tenant_id, status, created_at DESC)"
            )
        )


def _ensure_op_segment_indexes(engine: Engine) -> None:
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.op_segments')")).scalar()
        if not exists:
            return
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS op_segments_tenant_well_start_idx "
                "ON op_segments (tenant_id, well_run_id, start_ts ASC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS op_segments_tenant_well_type_start_idx "
                "ON op_segments (tenant_id, well_run_id, segment_type, start_ts ASC)"
            )
        )
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS op_segments_tenant_well_source_start_idx "
                "ON op_segments (tenant_id, well_run_id, source, start_ts ASC)"
            )
        )


def _backfill_event_metric_derived_columns(engine: Engine) -> None:
    with engine.begin() as conn:
        exists = conn.execute(text("SELECT to_regclass('public.event_metrics')")).scalar()
        if not exists:
            return
        conn.execute(
            text(
                "UPDATE event_metrics "
                "SET channel = field "
                "WHERE channel IS NULL"
            )
        )
        conn.execute(
            text(
                """
                UPDATE event_metrics m
                SET source = e.source,
                    well_run_id = COALESCE(m.well_run_id, e.well_run_id)
                FROM events e
                WHERE m.event_id = e.id
                  AND (m.source IS NULL OR m.well_run_id IS NULL)
                """
            )
        )
        conn.execute(
            text(
                "UPDATE event_metrics "
                "SET source = 'unknown' "
                "WHERE source IS NULL"
            )
        )


def ensure_schema(engine: Engine) -> None:
    # Add warehouse_id to existing tables if missing.
    _ensure_columns(
        engine,
        "data_warehouses",
        {"project_id": "project_id UUID NULL REFERENCES projects(id) ON DELETE SET NULL"},
    )
    _ensure_columns(
        engine,
        "datasets",
        {"warehouse_id": "warehouse_id UUID NULL REFERENCES data_warehouses(id) ON DELETE SET NULL"},
    )
    _ensure_columns(
        engine,
        "events",
        {
            "warehouse_id": "warehouse_id UUID NULL REFERENCES data_warehouses(id) ON DELETE SET NULL",
            "well_run_id": "well_run_id UUID NULL REFERENCES well_runs(id) ON DELETE SET NULL",
        },
    )
    _ensure_columns(
        engine,
        "event_metrics",
        {
            "well_run_id": "well_run_id UUID NULL",
            "channel": "channel VARCHAR(128) NULL",
            "source": "source VARCHAR(64) NULL",
            "md": "md DOUBLE PRECISION NULL",
            "quality_code": "quality_code SMALLINT NOT NULL DEFAULT 0",
        },
    )
    _ensure_columns(
        engine,
        "analysis_runs",
        {"warehouse_id": "warehouse_id UUID NULL REFERENCES data_warehouses(id) ON DELETE SET NULL"},
    )
    _ensure_columns(
        engine,
        "import_jobs",
        {
            "well_run_id": "well_run_id UUID NULL REFERENCES well_runs(id) ON DELETE SET NULL",
            "source_label": "source_label VARCHAR(64) NOT NULL DEFAULT 'file_upload'",
            "import_mode": "import_mode VARCHAR(32) NOT NULL DEFAULT 'events'",
        },
    )
    _ensure_columns(
        engine,
        "event_metrics_rollup_1m_v2",
        {
            "well_run_id": "well_run_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'",
            "source": "source VARCHAR(64) NOT NULL DEFAULT 'unknown'",
        },
    )
    _ensure_event_indexes(engine)
    _ensure_event_metric_indexes(engine)
    _ensure_event_metric_rollup_indexes(engine)
    _ensure_well_run_indexes(engine)
    _ensure_op_segment_indexes(engine)
    _backfill_event_metric_derived_columns(engine)


def _ensure_time_pk(engine: Engine, table: str) -> None:
    with engine.begin() as conn:
        exists = conn.execute(text(f"SELECT to_regclass('public.{table}')")).scalar()
        if not exists:
            return
        pk_columns = conn.execute(
            text(
                f"""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = to_regclass('public.{table}') AND i.indisprimary
                """
            )
        ).fetchall()
        pk_names = {row[0] for row in pk_columns}
        if pk_names and "created_at" not in pk_names:
            conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_pkey"))
            conn.execute(text(f"ALTER TABLE {table} ADD PRIMARY KEY (id, created_at)"))


def _create_hypertable(
    engine: Engine,
    *,
    table: str,
    time_column: str = "created_at",
    interval_literal: str,
) -> bool:
    with engine.begin() as conn:
        exists = conn.execute(text(f"SELECT to_regclass('public.{table}')")).scalar()
        if not exists:
            return False
        try:
            conn.execute(
                text(
                    f"SELECT create_hypertable('{table}', '{time_column}', "
                    "if_not_exists => TRUE, migrate_data => TRUE, "
                    f"chunk_time_interval => INTERVAL '{interval_literal}')"
                )
            )
            return True
        except Exception as exc:  # noqa: BLE001
            print(f"[timescaledb] create_hypertable({table}) failed: {exc}")
            return False


def _ensure_compression_policy(engine: Engine, *, table: str, compress_after_hours: int) -> None:
    if compress_after_hours <= 0:
        return
    with engine.begin() as conn:
        try:
            conn.execute(text(f"ALTER TABLE {table} SET (timescaledb.compress = TRUE)"))
            conn.execute(
                text(
                    f"SELECT add_compression_policy('{table}', "
                    f"INTERVAL '{compress_after_hours} hours')"
                )
            )
        except Exception as exc:  # noqa: BLE001
            if "already exists" not in str(exc).lower():
                print(f"[timescaledb] add_compression_policy({table}) failed: {exc}")


def _ensure_retention_policy(engine: Engine, *, table: str, retention_days: int) -> None:
    if retention_days <= 0:
        return
    with engine.begin() as conn:
        try:
            conn.execute(
                text(
                    f"SELECT add_retention_policy('{table}', "
                    f"INTERVAL '{retention_days} days')"
                )
            )
        except Exception as exc:  # noqa: BLE001
            if "already exists" not in str(exc).lower():
                print(f"[timescaledb] add_retention_policy({table}) failed: {exc}")


def ensure_timescaledb(
    engine: Engine,
    *,
    enabled: bool,
    chunk_interval_hours: int = 24,
    compress_after_hours: int = 0,
    retention_days: int = 0,
) -> None:
    if not enabled:
        return

    chunk_interval_hours = max(1, min(chunk_interval_hours, 24 * 30))
    compress_after_hours = max(0, compress_after_hours)
    retention_days = max(0, retention_days)

    with engine.begin() as conn:
        try:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS timescaledb"))
        except Exception as exc:  # noqa: BLE001 - log and continue if extension is unavailable
            print(f"[timescaledb] extension not available: {exc}")
            return

    _ensure_event_indexes(engine)
    _ensure_event_metric_indexes(engine)
    _ensure_event_metric_rollup_indexes(engine)
    _ensure_well_run_indexes(engine)
    _ensure_op_segment_indexes(engine)

    _ensure_time_pk(engine, "events")
    _ensure_time_pk(engine, "event_metrics")

    interval_literal = f"{chunk_interval_hours} hours"
    events_hypertable_ok = _create_hypertable(
        engine, table="events", time_column="created_at", interval_literal=interval_literal
    )
    metrics_hypertable_ok = _create_hypertable(
        engine, table="event_metrics", time_column="created_at", interval_literal=interval_literal
    )
    metrics_rollup_hypertable_ok = _create_hypertable(
        engine,
        table="event_metrics_rollup_1m_v2",
        time_column="bucket",
        interval_literal=interval_literal,
    )

    if events_hypertable_ok:
        _ensure_compression_policy(
            engine, table="events", compress_after_hours=compress_after_hours
        )
        _ensure_retention_policy(engine, table="events", retention_days=retention_days)

    if metrics_hypertable_ok:
        _ensure_compression_policy(
            engine, table="event_metrics", compress_after_hours=compress_after_hours
        )
        _ensure_retention_policy(
            engine, table="event_metrics", retention_days=retention_days
        )
    if metrics_rollup_hypertable_ok:
        _ensure_compression_policy(
            engine,
            table="event_metrics_rollup_1m_v2",
            compress_after_hours=compress_after_hours,
        )
        _ensure_retention_policy(
            engine, table="event_metrics_rollup_1m_v2", retention_days=retention_days
        )
