from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class WellRunCreate(BaseModel):
    name: str
    warehouse_id: uuid.UUID | None = None
    well_name: str | None = None
    section: str | None = None
    status: str = "active"
    started_at: datetime | None = None
    ended_at: datetime | None = None
    details: dict[str, Any] | None = None


class WellRunUpdate(BaseModel):
    name: str | None = None
    warehouse_id: uuid.UUID | None = None
    well_name: str | None = None
    section: str | None = None
    status: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    details: dict[str, Any] | None = None


class WellRunResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID | None
    name: str
    well_name: str | None
    section: str | None
    status: str
    started_at: datetime | None
    ended_at: datetime | None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WellRunChannelSummary(BaseModel):
    source: str
    channel: str
    count: int
    ts_start: datetime | None = None
    ts_end: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None


class AlignChannelRequest(BaseModel):
    channel: str
    source: str | None = None
    alias: str | None = None
    native_axis: Literal["auto", "time", "depth"] = "auto"
    method: Literal["nearest", "linear"] = "nearest"
    max_gap_seconds: float | None = Field(default=None, gt=0)
    max_gap_meters: float | None = Field(default=None, gt=0)


class WellRunAxisMapConfig(BaseModel):
    enabled: bool = True
    source: str | None = None
    channel: str | None = None
    max_gap_seconds: float = Field(default=120.0, gt=0)
    max_gap_meters: float = Field(default=10.0, gt=0)
    map_limit: int = Field(default=200000, ge=1000, le=1000000)


class WellRunAlignRequest(BaseModel):
    axis: Literal["time", "depth"] = "time"
    channels: list[AlignChannelRequest]
    grid_mode: Literal["fixed", "anchor"] = "fixed"
    anchor_alias: str | None = None
    segment_ids: list[uuid.UUID] = Field(default_factory=list)
    segment_types: list[str] = Field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None
    step_seconds: int = Field(default=5, ge=1, le=3600)
    step_meters: float = Field(default=0.5, gt=0, le=100)
    max_rows: int = Field(default=2000, ge=10, le=20000)
    axis_map: WellRunAxisMapConfig = Field(default_factory=WellRunAxisMapConfig)


class AlignedChannelValue(BaseModel):
    value: float | None = None
    quality_code: int = 9
    source: str | None = None


class WellRunAlignedRow(BaseModel):
    ts: datetime | None = None
    md: float | None = None
    values: dict[str, AlignedChannelValue]


class WellRunAlignResponse(BaseModel):
    well_run_id: uuid.UUID
    axis: Literal["time", "depth"]
    step_seconds: int | None = None
    step_meters: float | None = None
    rows: list[WellRunAlignedRow]
    stats: dict[str, Any] = Field(default_factory=dict)


class WellRunAxisMapPoint(BaseModel):
    ts: datetime
    md: float


class WellRunAxisMapResponse(BaseModel):
    well_run_id: uuid.UUID
    source: str | None = None
    channel: str | None = None
    count: int
    ts_start: datetime | None = None
    ts_end: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None
    rows: list[WellRunAxisMapPoint]


class WellRunSegmentCreate(BaseModel):
    segment_type: str
    source: str = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None
    details: dict[str, Any] | None = None


class WellRunSegmentUpdate(BaseModel):
    segment_type: str | None = None
    source: str | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None
    details: dict[str, Any] | None = None


class WellRunSegmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    warehouse_id: uuid.UUID | None
    well_run_id: uuid.UUID
    segment_type: str
    source: str
    confidence: float | None = None
    start_ts: datetime | None = None
    end_ts: datetime | None = None
    md_start: float | None = None
    md_end: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class WellRunSegmentDetectRequest(BaseModel):
    source: str = "surface"
    auto_source: str = "auto_v1"
    replace_existing_auto: bool = True
    start: datetime | None = None
    end: datetime | None = None
    step_seconds: int = Field(default=10, ge=1, le=300)
    max_rows: int = Field(default=20000, ge=100, le=100000)
    min_segment_points: int = Field(default=3, ge=1, le=1000)
    rpm_channel: str = "rpm"
    wob_channel: str = "wob"
    flow_channel: str = "flow_in"
    bit_depth_channel: str = "bit_depth"
    rpm_on: float = 20.0
    wob_on: float = 5.0
    flow_on: float = 50.0
    rpm_idle: float = 5.0
    wob_idle: float = 2.0
    flow_idle: float = 10.0
    rop_on_m_per_h: float = 3.0
    trip_rate_m_per_h: float = 20.0


class WellRunSegmentDetectResponse(BaseModel):
    well_run_id: uuid.UUID
    source: str
    auto_source: str
    step_seconds: int
    scanned_points: int
    created_segments: int
    distribution: dict[str, int] = Field(default_factory=dict)
    rows: list[WellRunSegmentResponse] = Field(default_factory=list)


class WellRunLagCorrectionRequest(BaseModel):
    source: str = "mudlog"
    channels: list[str] = Field(default_factory=list)
    start: datetime | None = None
    end: datetime | None = None
    lag_seconds: float = Field(default=120.0, gt=0, le=86400)
    direction: Literal["backward", "forward"] = "backward"
    remap_md: bool = True
    map_source: str | None = None
    map_channel: str | None = None
    max_gap_seconds: float = Field(default=120.0, gt=0)
    max_rows: int = Field(default=200000, ge=100, le=1000000)
    dry_run: bool = False


class WellRunLagCorrectionPreviewPoint(BaseModel):
    channel: str
    old_ts: datetime
    new_ts: datetime
    old_md: float | None = None
    new_md: float | None = None
    value: float


class WellRunLagCorrectionResponse(BaseModel):
    well_run_id: uuid.UUID
    source: str
    channels: list[str] = Field(default_factory=list)
    lag_seconds: float
    direction: Literal["backward", "forward"]
    scanned_rows: int
    affected_rows: int
    map_source: str | None = None
    map_channel: str | None = None
    dry_run: bool = False
    preview: list[WellRunLagCorrectionPreviewPoint] = Field(default_factory=list)
