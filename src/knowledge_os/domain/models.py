from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class Organization:
    id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class Workspace:
    id: UUID
    organization_id: UUID
    name: str
    slug: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class User:
    id: UUID
    email: str
    display_name: str
    is_active: bool
    created_at: datetime


@dataclass(frozen=True)
class WorkspaceMembership:
    id: UUID
    workspace_id: UUID
    user_id: UUID
    role: str
    created_at: datetime


@dataclass(frozen=True)
class AgentVersion:
    id: UUID
    agent_id: str
    workspace_id: UUID
    version: int
    schema_version: str
    config: dict[str, Any]
    is_active: bool
    created_by: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class PlatformEvent:
    """Immutable domain event emitted to the event bus."""

    event_id: UUID
    topic: str
    event_type: str
    tenant_id: UUID | None
    workspace_id: UUID | None
    actor_id: UUID | None
    trace_id: str
    payload: dict[str, Any]
    payload_hash: str
    occurred_at: datetime
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AuditRecord:
    """Append-only audit entry with strong consistency requirements."""

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
