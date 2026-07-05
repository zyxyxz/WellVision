from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    tenant_id: uuid.UUID | None = None


class SwitchTenantRequest(BaseModel):
    tenant_id: uuid.UUID


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenant_id: uuid.UUID | None = None
    roles: list[str] = []


class UserInfo(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    is_platform_admin: bool


class MeResponse(BaseModel):
    user: UserInfo
    tenant_id: uuid.UUID | None = None
    roles: list[str] = []
    context: dict[str, Any] = {}
