from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DatasetResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    uploaded_by_user_id: uuid.UUID | None
    filename: str
    content_type: str | None
    file_format: str
    storage_bucket: str
    storage_key: str
    size_bytes: int | None
    created_at: datetime


class DatasetPreviewResponse(BaseModel):
    dataset_id: uuid.UUID
    file_format: str
    columns: list[str]
    rows: list[dict[str, Any]]
    truncated: bool
    message: str | None = None


class MultipartUploadInitiateRequest(BaseModel):
    filename: str
    warehouse_id: uuid.UUID | None = None
    content_type: str | None = None
    size_bytes: int | None = Field(default=None, ge=1)


class MultipartUploadInitiateResponse(BaseModel):
    upload_id: str
    bucket: str
    key: str
    file_format: str
    part_size_bytes: int
    max_parts: int = 10000


class MultipartUploadPresignPartRequest(BaseModel):
    upload_id: str
    key: str
    part_number: int = Field(ge=1, le=10000)


class MultipartUploadPresignPartResponse(BaseModel):
    upload_id: str
    key: str
    part_number: int
    url: str


class MultipartUploadPart(BaseModel):
    part_number: int = Field(ge=1, le=10000)
    etag: str


class MultipartUploadCompleteRequest(BaseModel):
    upload_id: str
    key: str
    filename: str
    warehouse_id: uuid.UUID | None = None
    content_type: str | None = None
    parts: list[MultipartUploadPart] = Field(min_length=1)


class MultipartUploadAbortRequest(BaseModel):
    upload_id: str
    key: str
