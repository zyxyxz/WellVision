from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.analysis import AlgorithmParam


AlgorithmKind = Literal["python", "http", "workflow"]


class AlgorithmDefinitionCreate(BaseModel):
    name: str
    key: str | None = None
    kind: AlgorithmKind = "python"
    description: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True


class AlgorithmDefinitionUpdate(BaseModel):
    name: str | None = None
    key: str | None = None
    kind: AlgorithmKind | None = None
    description: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class AlgorithmDefinitionResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by_user_id: uuid.UUID | None
    key: str
    name: str
    kind: AlgorithmKind
    description: str | None
    config: dict[str, Any]
    enabled: bool
    params: list[AlgorithmParam] = []
    created_at: datetime
    updated_at: datetime


class AlgorithmAIGenerateRequest(BaseModel):
    requirement: str = Field(min_length=4)
    field: str | None = None
    language: str = "python"


class AlgorithmAIGenerateResponse(BaseModel):
    code: str
    params: list[AlgorithmParam] = []
