from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OpSegment(Base):
    __tablename__ = "op_segments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_warehouses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    well_run_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("well_runs.id", ondelete="CASCADE"), index=True
    )

    segment_type: Mapped[str] = mapped_column(String(64), index=True)
    source: Mapped[str] = mapped_column(String(64), default="manual", index=True)
    confidence: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)

    start_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    md_start: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    md_end: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow
    )
