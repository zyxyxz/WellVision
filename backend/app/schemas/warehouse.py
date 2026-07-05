from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DataSourceCreate(BaseModel):
    name: str | None = None
    source_type: str
    config: dict[str, Any] | None = None
    enabled: bool = True


class DataSourceUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class DataWarehouseCreate(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID | None = None
    sources: list[DataSourceCreate] | None = None


class DataWarehouseUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    project_id: uuid.UUID | None = None


class DataSourceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID
    name: str
    source_type: str
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool
    created_at: datetime
    updated_at: datetime


class DataWarehouseResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    project_id: uuid.UUID | None = None
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
