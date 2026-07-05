from __future__ import annotations

import uuid

from pydantic import BaseModel


class TenantSummary(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    role: str
