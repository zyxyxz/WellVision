from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field


class TenantCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255)


class TenantResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str | None = Field(default=None, max_length=255)
    is_platform_admin: bool = False


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None
    is_active: bool
    is_platform_admin: bool


class MembershipAssignRequest(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


class MembershipResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str
