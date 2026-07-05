from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ImportJobBase(BaseModel):
    dataset_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    well_run_id: uuid.UUID | None = None
    source_label: str = "file_upload"
    import_mode: str = Field(default="events")
    has_header: bool = True
    delimiter: str | None = None
    time_column: str | None = None
    start_time: datetime | None = None
    sample_rate_seconds: float | None = None


class ImportJobCreate(ImportJobBase):
    pass


class ImportJobUpdate(BaseModel):
    warehouse_id: uuid.UUID | None = None
    well_run_id: uuid.UUID | None = None
    source_label: str | None = None
    import_mode: str | None = None
    has_header: bool | None = None
    delimiter: str | None = None
    time_column: str | None = None
    start_time: datetime | None = None
    sample_rate_seconds: float | None = None


class ImportJobResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    dataset_id: uuid.UUID
    warehouse_id: uuid.UUID | None
    well_run_id: uuid.UUID | None
    created_by_user_id: uuid.UUID | None
    status: str
    error_message: str | None
    total_rows: int | None
    processed_rows: int
    has_header: bool
    delimiter: str | None
    source_label: str
    import_mode: str
    time_column: str | None
    start_time: datetime | None
    sample_rate_seconds: float | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    class Config:
        from_attributes = True
