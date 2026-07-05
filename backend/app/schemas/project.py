from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str
    code: str | None = None
    description: str | None = None
    background: str | None = None
    status: str | None = None


class ProjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    description: str | None = None
    background: str | None = None
    status: str | None = None


class ProjectResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    code: str
    description: str | None = None
    background: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
