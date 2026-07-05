from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class ReportTemplateCreate(BaseModel):
    name: str
    description: str | None = None
    prompt_template: str
    enabled: bool = True


class ReportTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    prompt_template: str | None = None
    enabled: bool | None = None


class ReportTemplateResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    name: str
    description: str | None
    prompt_template: str
    enabled: bool
    created_at: datetime
    updated_at: datetime
