from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventMetricRollup1mV2(Base):
    __tablename__ = "event_metrics_rollup_1m_v2"

    bucket: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    well_run_id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    source: Mapped[str] = mapped_column(String(64), primary_key=True)
    field: Mapped[str] = mapped_column(String(128), primary_key=True)

    point_count: Mapped[int] = mapped_column(BigInteger, default=0)
    sum_value: Mapped[float] = mapped_column(Float(asdecimal=False), default=0.0)
    min_value: Mapped[float] = mapped_column(Float(asdecimal=False), default=0.0)
    max_value: Mapped[float] = mapped_column(Float(asdecimal=False), default=0.0)
