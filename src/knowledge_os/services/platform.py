from datetime import UTC, datetime
from uuid import UUID, uuid4

from knowledge_os.domain.enums import EventTopic, Role
from knowledge_os.domain.models import AuditRecord, PlatformEvent, User
from knowledge_os.domain.utils import hash_payload, new_trace_id
from knowledge_os.ports.repositories import (
    AgentRepository,
    AuditStore,
    EventBus,
    TenantRepository,
)
from knowledge_os.schemas.agent_validator import AgentSchemaValidator


class TenantService:
    def __init__(
        self,
        tenant_repo: TenantRepository,
        audit_store: AuditStore,
        event_bus: EventBus,
    ):
        self._tenant_repo = tenant_repo
        self._audit_store = audit_store
        self._event_bus = event_bus

    async def _audit(
        self,
        *,
        trace_id: str,
        actor_id: UUID | None,
        tenant_id: UUID | None,
        workspace_id: UUID | None,
        action: str,
        resource_type: str,
        resource_id: str | None,
        details: dict,
    ) -> None:
        record = AuditRecord(
            id=uuid4(),
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            payload_hash=hash_payload(details),
            details=details,
            created_at=datetime.now(UTC),
        )
        await self._audit_store.append(record)

    async def _emit(
        self,
        *,
        trace_id: str,
        event_type: str,
        tenant_id: UUID | None,
        workspace_id: UUID | None,
        actor_id: UUID | None,
        payload: dict,
    ) -> PlatformEvent:
        from knowledge_os.adapters.messaging.event_bus import build_platform_event

        event = build_platform_event(
            topic=EventTopic.TENANT,
            event_type=event_type,
            trace_id=trace_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            payload=payload,
        )
        await self._event_bus.publish(event)
        return event

    async def create_organization(
        self, name: str, slug: str, *, actor_id: UUID | None = None, trace_id: str | None = None
    ):
        trace_id = trace_id or new_trace_id()
        org = await self._tenant_repo.create_organization(name, slug)
        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=org.id,
            workspace_id=None,
            action="organization.created",
            resource_type="organization",
            resource_id=str(org.id),
            details={"name": name, "slug": slug},
        )
        await self._emit(
            trace_id=trace_id,
            event_type="organization.created",
            tenant_id=org.id,
            workspace_id=None,
            actor_id=actor_id,
            payload={"organization_id": str(org.id), "slug": slug},
        )
        return org

    async def create_workspace(
        self,
        organization_id: UUID,
        name: str,
        slug: str,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
    ):
        trace_id = trace_id or new_trace_id()
        workspace = await self._tenant_repo.create_workspace(organization_id, name, slug)
        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=organization_id,
            workspace_id=workspace.id,
            action="workspace.created",
            resource_type="workspace",
            resource_id=str(workspace.id),
            details={"name": name, "slug": slug},
        )
        await self._emit(
            trace_id=trace_id,
            event_type="workspace.created",
            tenant_id=organization_id,
            workspace_id=workspace.id,
            actor_id=actor_id,
            payload={"workspace_id": str(workspace.id), "slug": slug},
        )
        return workspace

    async def ensure_user(
        self,
        user_id: UUID,
        email: str,
        display_name: str | None = None,
    ) -> User:
        return await self._tenant_repo.ensure_user(user_id, email, display_name)

    async def register_user(
        self,
        email: str,
        display_name: str,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
    ):
        trace_id = trace_id or new_trace_id()
        user = await self._tenant_repo.create_user(email, display_name)
        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id or user.id,
            tenant_id=None,
            workspace_id=None,
            action="user.registered",
            resource_type="user",
            resource_id=str(user.id),
            details={"email": email},
        )
        return user

    async def add_workspace_member(
        self,
        workspace_id: UUID,
        user_id: UUID,
        role: str,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
    ):
        if role not in {r.value for r in Role}:
            raise ValueError(f"Invalid role: {role}")

        trace_id = trace_id or new_trace_id()
        workspace = await self._tenant_repo.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")

        membership = await self._tenant_repo.add_workspace_member(workspace_id, user_id, role)
        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=workspace.organization_id,
            workspace_id=workspace_id,
            action="workspace.member.added",
            resource_type="workspace_membership",
            resource_id=str(membership.id),
            details={"user_id": str(user_id), "role": role},
        )
        return membership


class AgentRegistryService:
    def __init__(
        self,
        agent_repo: AgentRepository,
        tenant_repo: TenantRepository,
        audit_store: AuditStore,
        event_bus: EventBus,
        validator: AgentSchemaValidator | None = None,
    ):
        self._agent_repo = agent_repo
        self._tenant_repo = tenant_repo
        self._audit_store = audit_store
        self._event_bus = event_bus
        self._validator = validator or AgentSchemaValidator()

    async def _audit(
        self,
        *,
        trace_id: str,
        actor_id: UUID | None,
        tenant_id: UUID | None,
        workspace_id: UUID | None,
        action: str,
        resource_id: str | None,
        details: dict,
    ) -> None:
        record = AuditRecord(
            id=uuid4(),
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            action=action,
            resource_type="agent",
            resource_id=resource_id,
            payload_hash=hash_payload(details),
            details=details,
            created_at=datetime.now(UTC),
        )
        await self._audit_store.append(record)

    async def register_agent(
        self,
        config: dict,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
        activate: bool = True,
    ):
        trace_id = trace_id or new_trace_id()
        validated = self._validator.validate(config)

        workspace_id = UUID(validated["workspace_id"])
        workspace = await self._tenant_repo.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")

        if str(workspace.organization_id) != validated["tenant_id"]:
            raise ValueError("tenant_id must match workspace organization")

        agent_id = validated["agent_id"]
        version = await self._agent_repo.create_version(
            agent_id=agent_id,
            workspace_id=workspace_id,
            schema_version=validated["schema_version"],
            config=validated,
            created_by=actor_id,
        )

        if activate:
            version = await self._agent_repo.activate_version(
                agent_id, workspace_id, version.version
            )

        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=workspace.organization_id,
            workspace_id=workspace_id,
            action="agent.version.created",
            resource_id=f"{agent_id}:v{version.version}",
            details={"agent_id": agent_id, "version": version.version, "active": activate},
        )

        from knowledge_os.adapters.messaging.event_bus import build_platform_event

        event = build_platform_event(
            topic=EventTopic.AGENT,
            event_type="agent.version.created",
            trace_id=trace_id,
            tenant_id=workspace.organization_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            payload={
                "agent_id": agent_id,
                "version": version.version,
                "schema_version": version.schema_version,
                "is_active": version.is_active,
            },
        )
        await self._event_bus.publish(event)
        return version

    async def get_active_agent(self, agent_id: str, workspace_id: UUID):
        return await self._agent_repo.get_active_version(agent_id, workspace_id)

    async def list_versions(self, agent_id: str, workspace_id: UUID):
        return await self._agent_repo.list_versions(agent_id, workspace_id)

    async def activate_version(
        self,
        agent_id: str,
        workspace_id: UUID,
        version: int,
        *,
        actor_id: UUID | None = None,
        trace_id: str | None = None,
    ):
        trace_id = trace_id or new_trace_id()
        workspace = await self._tenant_repo.get_workspace(workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")

        activated = await self._agent_repo.activate_version(agent_id, workspace_id, version)
        await self._audit(
            trace_id=trace_id,
            actor_id=actor_id,
            tenant_id=workspace.organization_id,
            workspace_id=workspace_id,
            action="agent.version.activated",
            resource_id=f"{agent_id}:v{version}",
            details={"agent_id": agent_id, "version": version},
        )
        return activated
