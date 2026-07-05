from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, SmallInteger, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class EventMetric(Base):
    __tablename__ = "event_metrics"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, default=datetime.utcnow
    )

    event_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("data_warehouses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    well_run_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, index=True, nullable=True)

    field: Mapped[str] = mapped_column(String(128), index=True)
    channel: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    md: Mapped[float | None] = mapped_column(Float(asdecimal=False), nullable=True)
    quality_code: Mapped[int] = mapped_column(SmallInteger, default=0)
    value: Mapped[float] = mapped_column(Float(asdecimal=False))
