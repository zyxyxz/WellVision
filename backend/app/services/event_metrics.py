from __future__ import annotations

import math
import uuid
from collections.abc import Iterable
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import insert
from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import EventMetric, EventMetricRollup1mV2

NULL_WAREHOUSE_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
NULL_WELL_RUN_ID = uuid.UUID("00000000-0000-0000-0000-000000000000")
UNKNOWN_SOURCE = "unknown"
MD_KEYS = (
    "md",
    "measured_depth",
    "measuredDepth",
    "depth",
    "bit_depth",
    "hole_depth",
)


def _is_missing_relation(exc: Exception, relation_name: str) -> bool:
    message = str(exc).lower()
    relation = relation_name.lower()
    return relation in message and ("does not exist" in message or "undefined table" in message)


def _coerce_numeric(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        val = float(value)
        return val if math.isfinite(val) else None
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            val = float(text)
            return val if math.isfinite(val) else None
        except ValueError:
            return None
    return None


def extract_numeric_payload(payload: dict[str, Any] | None) -> list[tuple[str, float]]:
    if not payload:
        return []
    rows: list[tuple[str, float]] = []
    for key, raw in payload.items():
        if not isinstance(key, str) or not key:
            continue
        value = _coerce_numeric(raw)
        if value is None:
            continue
        rows.append((key[:128], value))
    return rows


def extract_measured_depth(payload: dict[str, Any] | None) -> float | None:
    if not payload:
        return None
    for key in MD_KEYS:
        if key not in payload:
            continue
        depth = _coerce_numeric(payload.get(key))
        if depth is None:
            continue
        return depth
    return None


def _minute_bucket(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.replace(second=0, microsecond=0)


def build_rollup_rows_1m(metric_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple, dict[str, Any]] = {}
    for row in metric_rows:
        created_at = row.get("created_at")
        tenant_id = row.get("tenant_id")
        field = row.get("field")
        value = row.get("value")
        if created_at is None or tenant_id is None or field is None or value is None:
            continue
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            continue
        if not math.isfinite(numeric_value):
            continue

        bucket = _minute_bucket(created_at)
        warehouse_id = row.get("warehouse_id") or NULL_WAREHOUSE_ID
        well_run_id = row.get("well_run_id") or NULL_WELL_RUN_ID
        source = str(row.get("source") or UNKNOWN_SOURCE)[:64]
        key = (bucket, tenant_id, warehouse_id, well_run_id, source, field)
        item = grouped.get(key)
        if item is None:
            grouped[key] = {
                "bucket": bucket,
                "tenant_id": tenant_id,
                "warehouse_id": warehouse_id,
                "well_run_id": well_run_id,
                "source": source,
                "field": field,
                "point_count": 1,
                "sum_value": numeric_value,
                "min_value": numeric_value,
                "max_value": numeric_value,
            }
            continue
        item["point_count"] += 1
        item["sum_value"] += numeric_value
        if numeric_value < item["min_value"]:
            item["min_value"] = numeric_value
        if numeric_value > item["max_value"]:
            item["max_value"] = numeric_value

    return list(grouped.values())


def upsert_rollup_rows_1m(db: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    stmt = pg_insert(EventMetricRollup1mV2).values(rows)
    upsert_stmt = stmt.on_conflict_do_update(
        index_elements=[
            EventMetricRollup1mV2.bucket,
            EventMetricRollup1mV2.tenant_id,
            EventMetricRollup1mV2.warehouse_id,
            EventMetricRollup1mV2.well_run_id,
            EventMetricRollup1mV2.source,
            EventMetricRollup1mV2.field,
        ],
        set_={
            "point_count": EventMetricRollup1mV2.point_count + stmt.excluded.point_count,
            "sum_value": EventMetricRollup1mV2.sum_value + stmt.excluded.sum_value,
            "min_value": func.least(EventMetricRollup1mV2.min_value, stmt.excluded.min_value),
            "max_value": func.greatest(EventMetricRollup1mV2.max_value, stmt.excluded.max_value),
        },
    )
    try:
        db.execute(upsert_stmt)
    except Exception as exc:  # noqa: BLE001 - keep ingestion alive before rollup table migration.
        if _is_missing_relation(exc, "event_metrics_rollup_1m_v2"):
            return
        raise


def persist_metric_rows(db: Session, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    try:
        db.execute(insert(EventMetric), rows)
    except Exception as exc:  # noqa: BLE001 - keep ingestion alive before metric table migration.
        if _is_missing_relation(exc, "event_metrics"):
            return
        raise
    upsert_rollup_rows_1m(db, build_rollup_rows_1m(rows))


def build_metric_rows(
    events: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for event in events:
        tenant_id = event.get("tenant_id")
        created_at = event.get("created_at")
        if tenant_id is None or created_at is None:
            continue
        event_id = event.get("id")
        warehouse_id = event.get("warehouse_id")
        well_run_id = event.get("well_run_id")
        raw_source = event.get("source")
        source = str(raw_source).strip()[:64] if raw_source else None
        payload = event.get("payload")
        md = extract_measured_depth(payload)
        for field, value in extract_numeric_payload(payload):
            rows.append(
                {
                    "id": uuid.uuid4(),
                    "event_id": event_id,
                    "tenant_id": tenant_id,
                    "warehouse_id": warehouse_id,
                    "well_run_id": well_run_id,
                    "created_at": created_at,
                    "field": field,
                    "channel": field,
                    "source": source,
                    "md": md,
                    "quality_code": 0,
                    "value": value,
                }
            )
    return rows
