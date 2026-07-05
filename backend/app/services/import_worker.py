from __future__ import annotations

import csv
import io
import itertools
import tempfile
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import insert, text

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models import Dataset, Event, ImportJob
from app.services.event_metrics import (
    build_metric_rows,
    persist_metric_rows,
)
from app.services.storage import build_s3_client, stream_object


def _parse_timestamp(value: str | None) -> datetime | None:
    if value is None:
        return None
    text_value = value.strip()
    if not text_value:
        return None
    try:
        return datetime.fromisoformat(text_value)
    except Exception:
        pass
    try:
        numeric = float(text_value)
        if numeric > 1e12:
            return datetime.fromtimestamp(numeric / 1000, tz=timezone.utc)
        if numeric > 1e9:
            return datetime.fromtimestamp(numeric, tz=timezone.utc)
    except Exception:
        return None
    return None


def _iter_csv_rows(
    fileobj: io.BufferedReader,
    *,
    has_header: bool,
    delimiter: str | None,
) -> Iterable[dict[str, str]]:
    text_stream = io.TextIOWrapper(fileobj, encoding="utf-8", errors="replace")
    if has_header:
        reader = csv.DictReader(text_stream, delimiter=delimiter or ",")
        for row in reader:
            yield row
        return

    reader = csv.reader(text_stream, delimiter=delimiter or ",")
    headers: list[str] | None = None
    for row in reader:
        if headers is None:
            headers = [f"col_{idx+1}" for idx in range(len(row))]
        yield {headers[i]: row[i] if i < len(row) else "" for i in range(len(headers))}


def _iter_parquet_rows(
    path: str,
    *,
    offset: int = 0,
    batch_size: int = 5000,
) -> tuple[list[str], Iterable[dict[str, object]]]:
    import pyarrow.parquet as pq  # type: ignore

    parquet = pq.ParquetFile(path)
    columns = list(parquet.schema.names)

    def _rows() -> Iterable[dict[str, object]]:
        skipped = 0
        for batch in parquet.iter_batches(batch_size=max(500, batch_size)):
            for row in batch.to_pylist():
                if skipped < offset:
                    skipped += 1
                    continue
                yield row

    return columns, _rows()


def _claim_pending_job() -> str | None:
    with SessionLocal() as db:
        row = db.execute(
            text(
                """
                WITH picked AS (
                    SELECT id
                    FROM import_jobs
                    WHERE status = 'pending'
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE import_jobs j
                SET status = 'running',
                    started_at = COALESCE(j.started_at, NOW()),
                    updated_at = NOW()
                FROM picked
                WHERE j.id = picked.id
                RETURNING j.id
                """
            )
        ).fetchone()
        if row is None:
            return None
        db.commit()
        return str(row[0])


def _mark_failed(job_id: str, message: str) -> None:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_message = message
        job.finished_at = datetime.utcnow()
        db.commit()


def _process_job(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None:
            return
        if job.status in {"paused", "cancelled", "completed", "failed", "needs_config"}:
            return
        if job.status != "running":
            job.status = "running"
            job.started_at = job.started_at or datetime.utcnow()
            db.commit()
        dataset = db.get(Dataset, job.dataset_id)
        if dataset is None:
            job.status = "failed"
            job.error_message = "Dataset not found."
            job.finished_at = datetime.utcnow()
            db.commit()
            return
        processed = int(job.processed_rows or 0)

    try:
        if dataset.file_format == "parquet":
            s3 = build_s3_client()
            with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
                s3.download_file(dataset.storage_bucket, dataset.storage_key, tmp.name)
                columns, rows = _iter_parquet_rows(tmp.name, offset=processed)
                outcome = _write_rows(job_id, rows, columns, processed)
        else:
            body = stream_object(bucket=dataset.storage_bucket, key=dataset.storage_key)
            buffered = io.BufferedReader(body)
            outcome = _process_csv_stream(job_id, buffered, processed)
    except Exception as exc:
        _mark_failed(job_id, str(exc))
        return

    if outcome == "completed":
        with SessionLocal() as db:
            job = db.get(ImportJob, job_id)
            if job:
                job.status = "completed"
                job.finished_at = datetime.utcnow()
                db.commit()


def _build_import_row(
    *,
    row: dict[str, object],
    columns: list[str],
    tenant_id,
    warehouse_id,
    well_run_id,
    source_label: str,
    time_column: str | None,
    start_time: datetime | None,
    sample_rate: float | None,
    global_idx: int,
) -> dict:
    payload = {key: row.get(key) for key in columns}
    created_at = None
    if time_column:
        created_at = _parse_timestamp(str(row.get(time_column)))
    if created_at is None and start_time and sample_rate:
        created_at = start_time + timedelta(seconds=sample_rate * global_idx)
    if created_at is None:
        created_at = datetime.utcnow()
    return {
        "tenant_id": tenant_id,
        "warehouse_id": warehouse_id,
        "well_run_id": well_run_id,
        "received_by_user_id": None,
        "source": source_label,
        "topic": None,
        "payload": payload,
        "created_at": created_at,
    }


def _write_rows(job_id: str, rows: Iterable[dict[str, object]], columns: list[str], processed: int) -> str:
    settings = get_settings()
    batch_size = max(100, settings.import_batch_size)
    buffer: list[dict] = []

    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None:
            return "cancelled"
        tenant_id = job.tenant_id
        warehouse_id = job.warehouse_id
        well_run_id = job.well_run_id
        source_label = (job.source_label or "file_upload").strip() or "file_upload"
        import_mode = (job.import_mode or "events").strip() or "events"
        time_column = job.time_column
        start_time = job.start_time
        sample_rate = job.sample_rate_seconds

    if import_mode not in {"events", "metrics_only"}:
        import_mode = "events"

    for idx, row in enumerate(rows):
        global_idx = processed + idx
        buffer.append(
            _build_import_row(
                row=row,
                columns=columns,
                tenant_id=tenant_id,
                warehouse_id=warehouse_id,
                well_run_id=well_run_id,
                source_label=source_label,
                time_column=time_column,
                start_time=start_time,
                sample_rate=sample_rate,
                global_idx=global_idx,
            )
        )
        if len(buffer) < batch_size:
            continue

        status = _current_status(job_id)
        if status == "paused":
            return "paused"
        if status == "cancelled":
            _mark_finished(job_id)
            return "cancelled"
        _flush_rows(buffer, import_mode=import_mode)
        processed += len(buffer)
        buffer.clear()
        _update_progress(job_id, processed)

    if buffer:
        status = _current_status(job_id)
        if status == "paused":
            return "paused"
        if status == "cancelled":
            _mark_finished(job_id)
            return "cancelled"
        _flush_rows(buffer, import_mode=import_mode)
        processed += len(buffer)
        _update_progress(job_id, processed)

    return "completed"


def _process_csv_stream(job_id: str, buffered: io.BufferedReader, processed: int) -> str:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None:
            return "cancelled"
        has_header = job.has_header
        delimiter = job.delimiter

    rows_iter = _iter_csv_rows(buffered, has_header=has_header, delimiter=delimiter)
    if processed:
        skipped = 0
        while skipped < processed:
            try:
                next(rows_iter)
                skipped += 1
            except StopIteration:
                break

    try:
        first_row = next(rows_iter)
    except StopIteration as exc:
        raise RuntimeError("Empty CSV.") from exc

    columns = list(first_row.keys())
    remaining = itertools.chain([first_row], rows_iter)
    return _write_rows(job_id, remaining, columns, processed)


def _flush_rows(rows: list[dict], *, import_mode: str) -> None:
    with SessionLocal() as db:
        if import_mode == "events":
            db.execute(insert(Event), rows)
        metric_rows = build_metric_rows(rows)
        if metric_rows:
            persist_metric_rows(db, metric_rows)
        db.commit()


def _update_progress(job_id: str, processed: int) -> None:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job is None:
            return
        job.processed_rows = processed
        db.commit()


def _current_status(job_id: str) -> str | None:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        return job.status if job else None


def _mark_finished(job_id: str) -> None:
    with SessionLocal() as db:
        job = db.get(ImportJob, job_id)
        if job:
            job.status = "cancelled"
            job.finished_at = datetime.utcnow()
            db.commit()


def _worker_loop() -> None:
    settings = get_settings()
    poll_seconds = max(1, settings.import_worker_poll_seconds)
    while True:
        job_id = _claim_pending_job()
        if job_id:
            _process_job(job_id)
            continue
        time.sleep(poll_seconds)


def start_import_worker() -> None:
    settings = get_settings()
    if not settings.import_worker_enabled:
        return
    worker_count = max(1, min(settings.import_worker_concurrency, 16))
    for idx in range(worker_count):
        name = f"import-worker-{idx + 1}"
        thread = threading.Thread(target=_worker_loop, name=name, daemon=True)
        thread.start()
