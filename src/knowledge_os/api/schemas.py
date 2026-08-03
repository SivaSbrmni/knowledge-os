from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9-]+$")


class OrganizationResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=128, pattern=r"^[a-z0-9-]+$")


class WorkspaceResponse(BaseModel):
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=255)


class UserResponse(BaseModel):
    id: UUID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


class WorkspaceMemberCreate(BaseModel):
    user_id: UUID
    role: str


class WorkspaceMemberResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    created_at: datetime


class AgentRegisterRequest(BaseModel):
    config: dict[str, Any]
    activate: bool = True


class AgentVersionResponse(BaseModel):
    id: UUID
    agent_id: str
    workspace_id: UUID
    version: int
    schema_version: str
    config: dict[str, Any]
    is_active: bool
    created_by: UUID | None
    created_at: datetime


class AuditRecordResponse(BaseModel):
    id: UUID
    trace_id: str
    actor_id: UUID | None
    tenant_id: UUID | None
    workspace_id: UUID | None
    action: str
    resource_type: str
    resource_id: str | None
    payload_hash: str
    details: dict[str, Any]
    created_at: datetime


class DevTokenRequest(BaseModel):
    user_id: UUID
    email: EmailStr
    roles: list[str] = Field(default_factory=lambda: ["workspace_admin"])


class DevTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class HealthResponse(BaseModel):
    status: str
    version: str
    environment: str


class ReadyResponse(BaseModel):
    status: str
    database: str
    redis: str
