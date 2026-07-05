from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


ReportStatusValue = Literal["draft", "in_review", "published", "rejected"]


class ReportCreateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    content_markdown: str = Field(min_length=1)


class ReportUpdateRequest(BaseModel):
    title: str = Field(min_length=3, max_length=255)
    content_markdown: str = Field(min_length=1)


class ReportReviewRequest(BaseModel):
    comment: str | None = Field(default=None, max_length=5000)


class ReportFromRunRequest(BaseModel):
    run_id: uuid.UUID
    title: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=5000)


class ReportResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    created_by_user_id: uuid.UUID
    reviewed_by_user_id: uuid.UUID | None
    title: str
    content_markdown: str
    summary_json: dict = Field(default_factory=dict)
    status: ReportStatusValue
    review_comment: str | None
    created_at: datetime
    updated_at: datetime
    published_at: datetime | None
