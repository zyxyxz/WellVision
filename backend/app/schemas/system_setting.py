from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SystemSettingResponse(BaseModel):
    key: str
    value: dict[str, Any] = Field(default_factory=dict)
    updated_at: datetime | None = None
    updated_by_user_id: uuid.UUID | None = None


class SystemSettingUpsert(BaseModel):
    value: dict[str, Any] = Field(default_factory=dict)
