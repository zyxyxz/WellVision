from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.schemas.analysis import AlgorithmRunResponse


class AIChatContext(BaseModel):
    warehouse_id: uuid.UUID | None = None
    field: str | None = None
    start: datetime | None = None
    end: datetime | None = None
    algorithm_result: AlgorithmRunResponse | None = None
    notes: str | None = None


class AIChatRequest(BaseModel):
    session_id: uuid.UUID | None = None
    title: str | None = None
    message: str
    context: AIChatContext | None = None


class AIChatMessageResponse(BaseModel):
    id: uuid.UUID
    role: str
    content: str
    created_at: datetime


class AIChatSessionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    user_id: uuid.UUID | None
    warehouse_id: uuid.UUID | None
    title: str | None
    context: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class AIChatResponse(BaseModel):
    session_id: uuid.UUID
    model: str
    reply: str
    message_id: uuid.UUID
