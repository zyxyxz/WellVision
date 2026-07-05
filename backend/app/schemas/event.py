from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EventIngestRequest(BaseModel):
    source: str = Field(default="http")
    topic: str | None = None
    payload: dict[str, Any]
    warehouse_id: uuid.UUID | None = None
    well_run_id: uuid.UUID | None = None


class EventResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID | None = None
    well_run_id: uuid.UUID | None = None
    received_by_user_id: uuid.UUID | None
    source: str
    topic: str | None
    payload: dict[str, Any]
    created_at: datetime
