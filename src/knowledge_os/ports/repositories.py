from abc import ABC, abstractmethod
from typing import Any
from uuid import UUID

from knowledge_os.domain.models import (
    AgentVersion,
    AuditRecord,
    Organization,
    PlatformEvent,
    User,
    Workspace,
    WorkspaceMembership,
)


class TenantRepository(ABC):
    @abstractmethod
    async def create_organization(self, name: str, slug: str) -> Organization:
        pass

    @abstractmethod
    async def get_organization(self, org_id: UUID) -> Organization | None:
        pass

    @abstractmethod
    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        pass

    @abstractmethod
    async def create_workspace(
        self, organization_id: UUID, name: str, slug: str
    ) -> Workspace:
        pass

    @abstractmethod
    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        pass

    @abstractmethod
    async def list_workspaces(self, organization_id: UUID) -> list[Workspace]:
        pass

    @abstractmethod
    async def create_user(self, email: str, display_name: str) -> User:
        pass

    @abstractmethod
    async def get_user(self, user_id: UUID) -> User | None:
        pass

    @abstractmethod
    async def get_user_by_email(self, email: str) -> User | None:
        pass

    @abstractmethod
    async def add_workspace_member(
        self, workspace_id: UUID, user_id: UUID, role: str
    ) -> WorkspaceMembership:
        pass

    @abstractmethod
    async def get_workspace_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMembership | None:
        pass


class AgentRepository(ABC):
    @abstractmethod
    async def create_version(
        self,
        agent_id: str,
        workspace_id: UUID,
        schema_version: str,
        config: dict[str, Any],
        created_by: UUID | None,
    ) -> AgentVersion:
        pass

    @abstractmethod
    async def get_active_version(
        self, agent_id: str, workspace_id: UUID
    ) -> AgentVersion | None:
        pass

    @abstractmethod
    async def get_version(
        self, agent_id: str, workspace_id: UUID, version: int
    ) -> AgentVersion | None:
        pass

    @abstractmethod
    async def list_versions(self, agent_id: str, workspace_id: UUID) -> list[AgentVersion]:
        pass

    @abstractmethod
    async def activate_version(
        self, agent_id: str, workspace_id: UUID, version: int
    ) -> AgentVersion:
        pass


class EventBus(ABC):
    @abstractmethod
    async def publish(self, event: PlatformEvent) -> None:
        pass

    @abstractmethod
    async def subscribe(self, topic: str, handler: Any) -> None:
        pass


class AuditStore(ABC):
    @abstractmethod
    async def append(self, record: AuditRecord) -> AuditRecord:
        pass

    @abstractmethod
    async def query_by_trace(self, trace_id: str) -> list[AuditRecord]:
        pass

    @abstractmethod
    async def query_by_tenant(
        self, tenant_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[AuditRecord]:
        pass


class AuthProvider(ABC):
    """Authentication port — OIDC-compatible."""

    @abstractmethod
    async def verify_token(self, token: str) -> dict[str, Any]:
        pass

    @abstractmethod
    async def issue_dev_token(
        self, user_id: UUID, email: str, roles: list[str]
    ) -> str:
        pass
