from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


AlgorithmId = str


class SeriesQuery(BaseModel):
    field: str = Field(description="Numeric field name inside event payload")
    start: datetime | None = None
    end: datetime | None = None
    limit: int = Field(default=2000, ge=10, le=20000)
    bucket_minutes: int | None = Field(default=None, ge=1, le=43200)
    warehouse_id: uuid.UUID | None = None
    well_run_id: uuid.UUID | None = None


class SeriesPoint(BaseModel):
    ts: datetime
    value: float


class SeriesResponse(BaseModel):
    field: str
    points: list[SeriesPoint]
    stats: dict[str, float | int]


class CompareResponse(BaseModel):
    field: str
    left: SeriesResponse
    right: SeriesResponse


class FieldSummary(BaseModel):
    name: str
    count: int


class AlgorithmParam(BaseModel):
    key: str
    label: str
    type: Literal["number", "field", "text", "boolean"] = "number"
    default: float | int | str | bool
    min: float | int | None = None
    max: float | int | None = None
    step: float | int | None = None
    description: str | None = None


class XYPoint(BaseModel):
    x: float
    y: float


class AlgorithmInfo(BaseModel):
    id: AlgorithmId
    name: str
    description: str
    params: list[AlgorithmParam] = []
    kind: str = "builtin"


class AlgorithmRunRequest(BaseModel):
    algorithm_id: AlgorithmId
    series: SeriesQuery
    params: dict[str, Any] = {}


class AlgorithmRunResponse(BaseModel):
    algorithm_id: AlgorithmId
    run_id: uuid.UUID | None = None
    result_series: list[SeriesPoint]
    result_points: list[XYPoint] = []
    x_axis: str | None = None
    metrics: dict[str, float | int | str]


class AnalysisRunResponse(BaseModel):
    id: uuid.UUID
    algorithm_id: AlgorithmId
    field: str
    warehouse_id: uuid.UUID | None = None
    params: dict[str, Any]
    base_stats: dict[str, Any]
    metrics: dict[str, Any]
    created_at: datetime


class AIReportRequest(BaseModel):
    title: str = "WellVision Analysis Report"
    series: SeriesQuery
    algorithm_result: AlgorithmRunResponse | None = None
    notes: str | None = None
    save_as_report: bool = False
    report_title: str | None = None
    template_id: uuid.UUID | None = None


class AIReportResponse(BaseModel):
    model: str
    report_markdown: str
    report_id: uuid.UUID | None = None
