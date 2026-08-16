from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import (
    AgentVersionModel,
    AuditRecordModel,
    OrganizationModel,
    UserModel,
    WorkspaceMembershipModel,
    WorkspaceModel,
)
from knowledge_os.domain.models import (
    AgentVersion,
    AuditRecord,
    Organization,
    User,
    Workspace,
    WorkspaceMembership,
)
from knowledge_os.ports.repositories import AgentRepository, AuditStore, TenantRepository


def _to_org(model: OrganizationModel) -> Organization:
    return Organization(
        id=model.id,
        name=model.name,
        slug=model.slug,
        is_active=model.is_active,
        created_at=model.created_at,
    )


def _to_workspace(model: WorkspaceModel) -> Workspace:
    return Workspace(
        id=model.id,
        organization_id=model.organization_id,
        name=model.name,
        slug=model.slug,
        is_active=model.is_active,
        created_at=model.created_at,
    )


def _to_user(model: UserModel) -> User:
    return User(
        id=model.id,
        email=model.email,
        display_name=model.display_name,
        is_active=model.is_active,
        created_at=model.created_at,
    )


def _to_membership(model: WorkspaceMembershipModel) -> WorkspaceMembership:
    return WorkspaceMembership(
        id=model.id,
        workspace_id=model.workspace_id,
        user_id=model.user_id,
        role=model.role,
        created_at=model.created_at,
    )


def _to_agent_version(model: AgentVersionModel) -> AgentVersion:
    return AgentVersion(
        id=model.id,
        agent_id=model.agent_id,
        workspace_id=model.workspace_id,
        version=model.version,
        schema_version=model.schema_version,
        config=model.config,
        is_active=model.is_active,
        created_by=model.created_by,
        created_at=model.created_at,
    )


def _to_audit(model: AuditRecordModel) -> AuditRecord:
    return AuditRecord(
        id=model.id,
        trace_id=model.trace_id,
        actor_id=model.actor_id,
        tenant_id=model.tenant_id,
        workspace_id=model.workspace_id,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        payload_hash=model.payload_hash,
        details=model.details,
        created_at=model.created_at,
    )


class PostgresTenantRepository(TenantRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create_organization(self, name: str, slug: str) -> Organization:
        model = OrganizationModel(name=name, slug=slug)
        self._session.add(model)
        await self._session.flush()
        return _to_org(model)

    async def get_organization(self, org_id: UUID) -> Organization | None:
        result = await self._session.get(OrganizationModel, org_id)
        return _to_org(result) if result else None

    async def get_organization_by_slug(self, slug: str) -> Organization | None:
        stmt = select(OrganizationModel).where(OrganizationModel.slug == slug)
        result = await self._session.scalar(stmt)
        return _to_org(result) if result else None

    async def create_workspace(
        self, organization_id: UUID, name: str, slug: str
    ) -> Workspace:
        model = WorkspaceModel(organization_id=organization_id, name=name, slug=slug)
        self._session.add(model)
        await self._session.flush()
        return _to_workspace(model)

    async def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        result = await self._session.get(WorkspaceModel, workspace_id)
        return _to_workspace(result) if result else None

    async def list_workspaces(self, organization_id: UUID) -> list[Workspace]:
        stmt = select(WorkspaceModel).where(WorkspaceModel.organization_id == organization_id)
        results = await self._session.scalars(stmt)
        return [_to_workspace(r) for r in results]

    async def create_user(self, email: str, display_name: str) -> User:
        model = UserModel(email=email, display_name=display_name)
        self._session.add(model)
        await self._session.flush()
        return _to_user(model)

    async def get_user(self, user_id: UUID) -> User | None:
        result = await self._session.get(UserModel, user_id)
        return _to_user(result) if result else None

    async def get_user_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await self._session.scalar(stmt)
        return _to_user(result) if result else None

    async def ensure_user(
        self, user_id: UUID, email: str, display_name: str | None = None
    ) -> User:
        existing = await self.get_user(user_id)
        if existing is not None:
            return existing
        by_email = await self.get_user_by_email(email)
        if by_email is not None:
            return by_email
        model = UserModel(
            id=user_id,
            email=email,
            display_name=display_name or email.split("@")[0],
        )
        self._session.add(model)
        await self._session.flush()
        return _to_user(model)

    async def add_workspace_member(
        self, workspace_id: UUID, user_id: UUID, role: str
    ) -> WorkspaceMembership:
        model = WorkspaceMembershipModel(workspace_id=workspace_id, user_id=user_id, role=role)
        self._session.add(model)
        await self._session.flush()
        return _to_membership(model)

    async def get_workspace_membership(
        self, workspace_id: UUID, user_id: UUID
    ) -> WorkspaceMembership | None:
        stmt = select(WorkspaceMembershipModel).where(
            WorkspaceMembershipModel.workspace_id == workspace_id,
            WorkspaceMembershipModel.user_id == user_id,
        )
        result = await self._session.scalar(stmt)
        return _to_membership(result) if result else None


class PostgresAgentRepository(AgentRepository):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def _next_version(self, agent_id: str, workspace_id: UUID) -> int:
        stmt = select(func.coalesce(func.max(AgentVersionModel.version), 0)).where(
            AgentVersionModel.agent_id == agent_id,
            AgentVersionModel.workspace_id == workspace_id,
        )
        current = await self._session.scalar(stmt)
        return int(current or 0) + 1

    async def create_version(
        self,
        agent_id: str,
        workspace_id: UUID,
        schema_version: str,
        config: dict,
        created_by: UUID | None,
    ) -> AgentVersion:
        version = await self._next_version(agent_id, workspace_id)
        model = AgentVersionModel(
            agent_id=agent_id,
            workspace_id=workspace_id,
            version=version,
            schema_version=schema_version,
            config=config,
            is_active=False,
            created_by=created_by,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_agent_version(model)

    async def get_active_version(
        self, agent_id: str, workspace_id: UUID
    ) -> AgentVersion | None:
        stmt = select(AgentVersionModel).where(
            AgentVersionModel.agent_id == agent_id,
            AgentVersionModel.workspace_id == workspace_id,
            AgentVersionModel.is_active.is_(True),
        )
        result = await self._session.scalar(stmt)
        return _to_agent_version(result) if result else None

    async def get_version(
        self, agent_id: str, workspace_id: UUID, version: int
    ) -> AgentVersion | None:
        stmt = select(AgentVersionModel).where(
            AgentVersionModel.agent_id == agent_id,
            AgentVersionModel.workspace_id == workspace_id,
            AgentVersionModel.version == version,
        )
        result = await self._session.scalar(stmt)
        return _to_agent_version(result) if result else None

    async def list_versions(self, agent_id: str, workspace_id: UUID) -> list[AgentVersion]:
        stmt = (
            select(AgentVersionModel)
            .where(
                AgentVersionModel.agent_id == agent_id,
                AgentVersionModel.workspace_id == workspace_id,
            )
            .order_by(AgentVersionModel.version.desc())
        )
        results = await self._session.scalars(stmt)
        return [_to_agent_version(r) for r in results]

    async def activate_version(
        self, agent_id: str, workspace_id: UUID, version: int
    ) -> AgentVersion:
        target = await self.get_version(agent_id, workspace_id, version)
        if target is None:
            raise ValueError(f"Agent version not found: {agent_id} v{version}")

        await self._session.execute(
            update(AgentVersionModel)
            .where(
                AgentVersionModel.agent_id == agent_id,
                AgentVersionModel.workspace_id == workspace_id,
            )
            .values(is_active=False)
        )
        await self._session.execute(
            update(AgentVersionModel)
            .where(
                AgentVersionModel.agent_id == agent_id,
                AgentVersionModel.workspace_id == workspace_id,
                AgentVersionModel.version == version,
            )
            .values(is_active=True)
        )
        await self._session.flush()
        activated = await self.get_version(agent_id, workspace_id, version)
        assert activated is not None
        return activated


class PostgresAuditStore(AuditStore):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def append(self, record: AuditRecord) -> AuditRecord:
        model = AuditRecordModel(
            id=record.id,
            trace_id=record.trace_id,
            actor_id=record.actor_id,
            tenant_id=record.tenant_id,
            workspace_id=record.workspace_id,
            action=record.action,
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            payload_hash=record.payload_hash,
            details=record.details,
            created_at=record.created_at,
        )
        self._session.add(model)
        await self._session.flush()
        return _to_audit(model)

    async def query_by_trace(self, trace_id: str) -> list[AuditRecord]:
        stmt = (
            select(AuditRecordModel)
            .where(AuditRecordModel.trace_id == trace_id)
            .order_by(AuditRecordModel.created_at.asc())
        )
        results = await self._session.scalars(stmt)
        return [_to_audit(r) for r in results]

    async def query_by_tenant(
        self, tenant_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[AuditRecord]:
        stmt = (
            select(AuditRecordModel)
            .where(AuditRecordModel.tenant_id == tenant_id)
            .order_by(AuditRecordModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        results = await self._session.scalars(stmt)
        return [_to_audit(r) for r in results]
