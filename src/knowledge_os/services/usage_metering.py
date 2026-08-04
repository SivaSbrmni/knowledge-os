"""Usage metering foundation for enterprise billing."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import UsageEventModel


class UsageMeteringService:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def record(
        self,
        *,
        workspace_id: UUID,
        event_type: str,
        units: int = 1,
        actor_id: UUID | None = None,
        organization_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> None:
        model = UsageEventModel(
            id=uuid4(),
            organization_id=organization_id,
            workspace_id=workspace_id,
            actor_id=actor_id,
            event_type=event_type,
            units=units,
            event_metadata=metadata or {},
            occurred_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()

    async def sum_for_workspace(
        self, workspace_id: UUID, event_type: str | None = None
    ) -> int:
        stmt = select(func.coalesce(func.sum(UsageEventModel.units), 0)).where(
            UsageEventModel.workspace_id == workspace_id
        )
        if event_type:
            stmt = stmt.where(UsageEventModel.event_type == event_type)
        result = await self._session.scalar(stmt)
        return int(result or 0)
