from __future__ import annotations

import csv
import io
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_auth_context
from app.core.config import get_settings
from app.db.session import get_db
from app.models import DataWarehouse, Dataset, ImportJob, WellRun
from app.schemas.dataset import (
    DatasetPreviewResponse,
    DatasetResponse,
    MultipartUploadAbortRequest,
    MultipartUploadCompleteRequest,
    MultipartUploadInitiateRequest,
    MultipartUploadInitiateResponse,
    MultipartUploadPresignPartRequest,
    MultipartUploadPresignPartResponse,
)
from app.schemas.import_job import ImportJobCreate, ImportJobResponse, ImportJobUpdate
from app.services.audit import write_audit_log
from app.services.storage import (
    abort_multipart_upload,
    build_s3_client,
    complete_multipart_upload,
    create_multipart_upload,
    download_object_bytes,
    generate_multipart_upload_url,
    head_object,
    upload_bytesio,
)

router = APIRouter(prefix="/ingestion", tags=["ingestion"])
settings = get_settings()

ALLOWED_EXTENSIONS = {".csv": "csv", ".parquet": "parquet"}
ALLOWED_IMPORT_MODES = {"events", "metrics_only"}


def _detect_format(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    fmt = ALLOWED_EXTENSIONS.get(ext)
    if not fmt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only .csv and .parquet files are supported.",
        )
    return fmt


def _safe_filename(filename: str) -> str:
    base = os.path.basename(filename)
    return base.replace(" ", "_")


def _tenant_raw_prefix(tenant_id: uuid.UUID) -> str:
    raw_prefix = settings.raw_prefix.strip("/")
    return f"{tenant_id}/{raw_prefix}/"


def _assert_tenant_raw_key(tenant_id: uuid.UUID, key: str) -> None:
    expected_prefix = _tenant_raw_prefix(tenant_id)
    if not key.startswith(expected_prefix):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid object key for current tenant.",
        )


def _build_dataset_response(dataset: Dataset) -> DatasetResponse:
    return DatasetResponse(
        id=dataset.id,
        tenant_id=dataset.tenant_id,
        warehouse_id=dataset.warehouse_id,
        uploaded_by_user_id=dataset.uploaded_by_user_id,
        filename=dataset.filename,
        content_type=dataset.content_type,
        file_format=dataset.file_format,
        storage_bucket=dataset.storage_bucket,
        storage_key=dataset.storage_key,
        size_bytes=dataset.size_bytes,
        created_at=dataset.created_at,
    )


@router.post("/datasets", response_model=DatasetResponse, summary="Upload CSV/Parquet dataset")
async def upload_dataset(
    file: UploadFile = File(...),
    warehouse_id: uuid.UUID | None = Form(default=None),
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DatasetResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    warehouse: DataWarehouse | None = None
    if warehouse_id is not None:
        warehouse = db.get(DataWarehouse, warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

    file_format = _detect_format(file.filename)
    safe_name = _safe_filename(file.filename)
    key_filename = f"{uuid.uuid4()}__{safe_name}"

    file.file.seek(0, os.SEEK_END)
    size_bytes = file.file.tell()
    file.file.seek(0)

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes and size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max size of {settings.max_upload_mb} MB.",
        )

    bucket, key = upload_bytesio(
        tenant_id=ctx.tenant.id,
        prefix=settings.raw_prefix,
        filename=key_filename,
        fileobj=file.file,
        content_type=file.content_type,
    )

    dataset = Dataset(
        tenant_id=ctx.tenant.id,
        warehouse_id=warehouse.id if warehouse else None,
        uploaded_by_user_id=ctx.user.id,
        filename=safe_name,
        content_type=file.content_type,
        file_format=file_format,
        storage_bucket=bucket,
        storage_key=key,
        size_bytes=size_bytes,
    )
    db.add(dataset)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="dataset.upload",
        tenant_id=ctx.tenant.id,
        details={
            "dataset_id": str(dataset.id),
            "filename": dataset.filename,
            "format": dataset.file_format,
            "size_bytes": dataset.size_bytes,
            "storage_key": dataset.storage_key,
            "warehouse_id": str(warehouse.id) if warehouse else None,
        },
    )
    db.commit()
    db.refresh(dataset)

    return _build_dataset_response(dataset)


def _object_store_bucket_name() -> str:
    if settings.object_store_provider == "tos":
        return settings.tos_bucket or settings.object_store_bucket
    return settings.object_store_bucket


@router.post(
    "/datasets/multipart/initiate",
    response_model=MultipartUploadInitiateResponse,
    summary="Initiate multipart upload for CSV/Parquet dataset",
)
def initiate_multipart_upload(
    payload: MultipartUploadInitiateRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> MultipartUploadInitiateResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    warehouse: DataWarehouse | None = None
    if payload.warehouse_id is not None:
        warehouse = db.get(DataWarehouse, payload.warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

    file_format = _detect_format(payload.filename)
    safe_name = _safe_filename(payload.filename)
    key_filename = f"{uuid.uuid4()}__{safe_name}"

    max_bytes = settings.max_upload_mb * 1024 * 1024
    if payload.size_bytes and payload.size_bytes > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds max size of {settings.max_upload_mb} MB.",
        )

    part_size_bytes = settings.multipart_part_size_mb * 1024 * 1024
    max_parts = 10000
    if payload.size_bytes and payload.size_bytes > part_size_bytes * max_parts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"File is too large for current multipart settings. "
                f"Increase MULTIPART_PART_SIZE_MB (current: {settings.multipart_part_size_mb})."
            ),
        )

    try:
        bucket, key, upload_id = create_multipart_upload(
            tenant_id=ctx.tenant.id,
            prefix=settings.raw_prefix,
            filename=key_filename,
            content_type=payload.content_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to initiate multipart upload: {exc}",
        ) from exc

    write_audit_log(
        db,
        actor=ctx.user,
        action="dataset.multipart.initiate",
        tenant_id=ctx.tenant.id,
        details={
            "filename": safe_name,
            "format": file_format,
            "bucket": bucket,
            "key": key,
            "upload_id": upload_id,
            "warehouse_id": str(warehouse.id) if warehouse else None,
            "size_bytes": payload.size_bytes,
        },
    )
    db.commit()

    return MultipartUploadInitiateResponse(
        upload_id=upload_id,
        bucket=bucket,
        key=key,
        file_format=file_format,
        part_size_bytes=part_size_bytes,
    )


@router.post(
    "/datasets/multipart/presign-part",
    response_model=MultipartUploadPresignPartResponse,
    summary="Get presigned URL for multipart upload part",
)
def presign_multipart_part(
    payload: MultipartUploadPresignPartRequest,
    ctx: AuthContext = Depends(get_auth_context),
) -> MultipartUploadPresignPartResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    _assert_tenant_raw_key(ctx.tenant.id, payload.key)
    bucket = _object_store_bucket_name()

    try:
        url = generate_multipart_upload_url(
            bucket=bucket,
            key=payload.key,
            upload_id=payload.upload_id,
            part_number=payload.part_number,
            expires_seconds=settings.multipart_presign_expires_seconds,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to generate upload URL: {exc}",
        ) from exc

    return MultipartUploadPresignPartResponse(
        upload_id=payload.upload_id,
        key=payload.key,
        part_number=payload.part_number,
        url=url,
    )


@router.post(
    "/datasets/multipart/complete",
    response_model=DatasetResponse,
    summary="Complete multipart upload and register dataset",
)
def complete_multipart_dataset_upload(
    payload: MultipartUploadCompleteRequest,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DatasetResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    warehouse: DataWarehouse | None = None
    if payload.warehouse_id is not None:
        warehouse = db.get(DataWarehouse, payload.warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

    _assert_tenant_raw_key(ctx.tenant.id, payload.key)

    safe_name = _safe_filename(payload.filename)
    file_format = _detect_format(safe_name)
    bucket = _object_store_bucket_name()
    parts = [
        {
            "PartNumber": part.part_number,
            "ETag": part.etag.strip().strip('"'),
        }
        for part in payload.parts
    ]

    try:
        complete_multipart_upload(
            bucket=bucket,
            key=payload.key,
            upload_id=payload.upload_id,
            parts=parts,
        )
        object_meta = head_object(bucket=bucket, key=payload.key)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to complete multipart upload: {exc}",
        ) from exc

    dataset = Dataset(
        tenant_id=ctx.tenant.id,
        warehouse_id=warehouse.id if warehouse else None,
        uploaded_by_user_id=ctx.user.id,
        filename=safe_name,
        content_type=payload.content_type or (object_meta.get("content_type") or None),
        file_format=file_format,
        storage_bucket=bucket,
        storage_key=payload.key,
        size_bytes=int(object_meta.get("size_bytes") or 0),
    )
    db.add(dataset)
    db.flush()

    write_audit_log(
        db,
        actor=ctx.user,
        action="dataset.upload",
        tenant_id=ctx.tenant.id,
        details={
            "dataset_id": str(dataset.id),
            "filename": dataset.filename,
            "format": dataset.file_format,
            "size_bytes": dataset.size_bytes,
            "storage_key": dataset.storage_key,
            "warehouse_id": str(warehouse.id) if warehouse else None,
            "upload_mode": "multipart",
        },
    )
    db.commit()
    db.refresh(dataset)

    return _build_dataset_response(dataset)


@router.post(
    "/datasets/multipart/abort",
    summary="Abort multipart upload",
)
def abort_multipart_dataset_upload(
    payload: MultipartUploadAbortRequest,
    ctx: AuthContext = Depends(get_auth_context),
):
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    _assert_tenant_raw_key(ctx.tenant.id, payload.key)
    bucket = _object_store_bucket_name()

    try:
        abort_multipart_upload(bucket=bucket, key=payload.key, upload_id=payload.upload_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to abort multipart upload: {exc}",
        ) from exc

    return {"success": True}


@router.get("/datasets", response_model=list[DatasetResponse], summary="List datasets for current tenant")
def list_datasets(
    warehouse_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[DatasetResponse]:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    stmt = select(Dataset).where(Dataset.tenant_id == ctx.tenant.id)
    if warehouse_id is not None:
        stmt = stmt.where(Dataset.warehouse_id == warehouse_id)
    stmt = stmt.order_by(Dataset.created_at.desc()).limit(200)
    rows = db.execute(stmt).scalars().all()
    return [_build_dataset_response(row) for row in rows]


@router.get(
    "/datasets/{dataset_id}/preview",
    response_model=DatasetPreviewResponse,
    summary="Preview dataset rows (CSV/Parquet)",
)
def preview_dataset(
    dataset_id: uuid.UUID,
    limit: int = 20,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> DatasetPreviewResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    dataset = db.get(Dataset, dataset_id)
    if dataset is None or dataset.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    if dataset.file_format == "parquet":
        try:
            import pyarrow.parquet as pq  # type: ignore
        except Exception:
            return DatasetPreviewResponse(
                dataset_id=dataset.id,
                file_format=dataset.file_format,
                columns=[],
                rows=[],
                truncated=False,
                message="Parquet preview requires pyarrow.",
            )
        preview_limit = max(1, min(limit, 200))
        preview_max_bytes = settings.parquet_preview_max_mb * 1024 * 1024
        try:
            metadata = head_object(bucket=dataset.storage_bucket, key=dataset.storage_key)
            size_bytes = int(metadata.get("size_bytes") or 0)
            if size_bytes > preview_max_bytes:
                return DatasetPreviewResponse(
                    dataset_id=dataset.id,
                    file_format=dataset.file_format,
                    columns=[],
                    rows=[],
                    truncated=True,
                    message=(
                        f"Parquet file is too large for preview "
                        f"({size_bytes / (1024 * 1024):.1f} MB > {settings.parquet_preview_max_mb} MB)."
                    ),
                )

            client = build_s3_client()
            with tempfile.NamedTemporaryFile(suffix=".parquet") as tmp:
                with open(tmp.name, "wb") as fp:
                    client.download_fileobj(dataset.storage_bucket, dataset.storage_key, fp)

                parquet = pq.ParquetFile(tmp.name)
                columns = list(parquet.schema.names)
                rows: list[dict[str, object]] = []
                for batch in parquet.iter_batches(batch_size=max(500, preview_limit)):
                    for row in batch.to_pylist():
                        rows.append(row)
                        if len(rows) >= preview_limit:
                            break
                    if len(rows) >= preview_limit:
                        break

                total_rows = parquet.metadata.num_rows if parquet.metadata else None
                truncated = (total_rows is not None and total_rows > len(rows)) or (
                    total_rows is None and len(rows) >= preview_limit
                )
                return DatasetPreviewResponse(
                    dataset_id=dataset.id,
                    file_format=dataset.file_format,
                    columns=columns,
                    rows=rows,
                    truncated=truncated,
                )
        except Exception as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Preview failed: {exc}") from exc

    if dataset.file_format != "csv":
        return DatasetPreviewResponse(
            dataset_id=dataset.id,
            file_format=dataset.file_format,
            columns=[],
            rows=[],
            truncated=False,
            message="Preview is only available for CSV/Parquet files.",
        )

    max_bytes = settings.max_upload_mb * 1024 * 1024
    sample_bytes = min(max_bytes, settings.import_preview_bytes)
    try:
        raw = download_object_bytes(
            bucket=dataset.storage_bucket,
            key=dataset.storage_key,
            max_bytes=sample_bytes,
        )
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=f"Failed to read object: {exc}") from exc
    text = raw.decode("utf-8", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, str]] = []
    truncated = False
    for row in reader:
        rows.append(row)
        if len(rows) >= limit:
            truncated = True
            break
    columns = reader.fieldnames or []
    return DatasetPreviewResponse(
        dataset_id=dataset.id,
        file_format=dataset.file_format,
        columns=columns,
        rows=rows,
        truncated=truncated,
    )


@router.post("/import-jobs", response_model=ImportJobResponse, summary="Create an import job")
def create_import_job(
    payload: ImportJobCreate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")

    dataset = db.get(Dataset, payload.dataset_id)
    if dataset is None or dataset.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dataset not found.")

    warehouse_id = payload.warehouse_id or dataset.warehouse_id
    if warehouse_id is not None:
        warehouse = db.get(DataWarehouse, warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")
    else:
        warehouse = None

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
    source_label = (payload.source_label or "file_upload").strip() or "file_upload"
    import_mode = (payload.import_mode or "events").strip() or "events"
    if import_mode not in ALLOWED_IMPORT_MODES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"import_mode must be one of: {', '.join(sorted(ALLOWED_IMPORT_MODES))}.",
        )

    needs_config = not payload.time_column and not (
        payload.start_time and payload.sample_rate_seconds
    )
    status_value = "needs_config" if needs_config else "pending"

    job = ImportJob(
        tenant_id=ctx.tenant.id,
        dataset_id=dataset.id,
        warehouse_id=warehouse.id if warehouse else None,
        well_run_id=well_run.id if well_run else None,
        created_by_user_id=ctx.user.id,
        status=status_value,
        has_header=payload.has_header,
        delimiter=payload.delimiter,
        source_label=source_label,
        import_mode=import_mode,
        time_column=payload.time_column,
        start_time=payload.start_time,
        sample_rate_seconds=payload.sample_rate_seconds,
    )
    db.add(job)
    db.flush()
    write_audit_log(
        db,
        actor=ctx.user,
        action="import_job.create",
        tenant_id=ctx.tenant.id,
        details={"job_id": str(job.id), "dataset_id": str(dataset.id)},
    )
    db.commit()
    db.refresh(job)
    return ImportJobResponse.from_orm(job)


@router.get("/import-jobs", response_model=list[ImportJobResponse], summary="List import jobs")
def list_import_jobs(
    dataset_id: uuid.UUID | None = None,
    warehouse_id: uuid.UUID | None = None,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> list[ImportJobResponse]:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    stmt = select(ImportJob).where(ImportJob.tenant_id == ctx.tenant.id)
    if dataset_id is not None:
        stmt = stmt.where(ImportJob.dataset_id == dataset_id)
    if warehouse_id is not None:
        stmt = stmt.where(ImportJob.warehouse_id == warehouse_id)
    stmt = stmt.order_by(ImportJob.created_at.desc()).limit(200)
    rows = db.execute(stmt).scalars().all()
    return [ImportJobResponse.from_orm(row) for row in rows]


@router.patch("/import-jobs/{job_id}", response_model=ImportJobResponse, summary="Update import job config")
def update_import_job(
    job_id: uuid.UUID,
    payload: ImportJobUpdate,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    job = db.get(ImportJob, job_id)
    if job is None or job.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")

    patch = payload.dict(exclude_unset=True)
    next_warehouse_id = patch.get("warehouse_id", job.warehouse_id)
    next_well_run_id = patch.get("well_run_id", job.well_run_id)

    if next_warehouse_id is not None:
        warehouse = db.get(DataWarehouse, next_warehouse_id)
        if warehouse is None or warehouse.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Warehouse not found.")

    if next_well_run_id is not None:
        well_run = db.get(WellRun, next_well_run_id)
        if well_run is None or well_run.tenant_id != ctx.tenant.id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Well run not found.")
        if next_warehouse_id is not None and well_run.warehouse_id and well_run.warehouse_id != next_warehouse_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="well_run_id does not belong to warehouse_id.",
            )

    for field, value in patch.items():
        if field == "source_label" and value is not None:
            value = value.strip() or "file_upload"
        if field == "import_mode" and value is not None:
            value = value.strip() or "events"
            if value not in ALLOWED_IMPORT_MODES:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"import_mode must be one of: {', '.join(sorted(ALLOWED_IMPORT_MODES))}.",
                )
        setattr(job, field, value)

    needs_config = not job.time_column and not (job.start_time and job.sample_rate_seconds)
    if needs_config:
        job.status = "needs_config"
    elif job.status == "needs_config":
        job.status = "pending"

    db.flush()
    db.commit()
    db.refresh(job)
    return ImportJobResponse.from_orm(job)


@router.post("/import-jobs/{job_id}/start", response_model=ImportJobResponse, summary="Start or resume import job")
def start_import_job(
    job_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    job = db.get(ImportJob, job_id)
    if job is None or job.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")
    if job.status == "needs_config":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Import job needs configuration.")
    if job.status in {"completed", "running"}:
        return ImportJobResponse.from_orm(job)
    job.status = "pending"
    job.error_message = None
    db.flush()
    db.commit()
    db.refresh(job)
    return ImportJobResponse.from_orm(job)


@router.post("/import-jobs/{job_id}/pause", response_model=ImportJobResponse, summary="Pause import job")
def pause_import_job(
    job_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    job = db.get(ImportJob, job_id)
    if job is None or job.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")
    if job.status == "running":
        job.status = "paused"
    db.flush()
    db.commit()
    db.refresh(job)
    return ImportJobResponse.from_orm(job)


@router.post("/import-jobs/{job_id}/cancel", response_model=ImportJobResponse, summary="Cancel import job")
def cancel_import_job(
    job_id: uuid.UUID,
    ctx: AuthContext = Depends(get_auth_context),
    db: Session = Depends(get_db),
) -> ImportJobResponse:
    if ctx.tenant is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Tenant context required.")
    job = db.get(ImportJob, job_id)
    if job is None or job.tenant_id != ctx.tenant.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found.")
    if job.status not in {"completed", "cancelled"}:
        job.status = "cancelled"
    db.flush()
    db.commit()
    db.refresh(job)
    return ImportJobResponse.from_orm(job)
