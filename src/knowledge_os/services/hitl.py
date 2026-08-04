"""Human-in-the-loop review queue for withheld or low-trust answers."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from knowledge_os.adapters.persistence.models import ReviewQueueModel
from knowledge_os.domain.knowledge import CitedResponse


class HITLService:
    def __init__(self, session: AsyncSession):
        self._session = session

    def should_enqueue(self, response: CitedResponse, agent_config: dict) -> bool:
        compliance = agent_config.get("compliance_policy", {})
        if not compliance.get("enabled", True):
            return False
        if response.withheld and compliance.get("require_hitl_on_withhold", True):
            return True
        threshold = compliance.get("require_hitl_below_trust", 0.75)
        if response.trust.overall < threshold:
            return True
        return False

    async def enqueue(
        self,
        *,
        workspace_id: UUID,
        session_id: UUID,
        requester_id: UUID,
        question: str,
        response: CitedResponse,
        trace_id: str,
    ) -> UUID:
        model = ReviewQueueModel(
            id=uuid4(),
            workspace_id=workspace_id,
            session_id=session_id,
            requester_id=requester_id,
            question=question,
            proposed_answer=response.answer,
            trust_snapshot={
                "source_trust": response.trust.source_trust,
                "retrieval_trust": response.trust.retrieval_trust,
                "reasoning_trust": response.trust.reasoning_trust,
                "groundedness": response.trust.groundedness,
                "overall": response.trust.overall,
                "threshold_met": response.trust.threshold_met,
                "explanation": response.trust.explanation,
                "conflicts": response.trust.conflicts,
            },
            citations=response.citations,
            status="pending",
            trace_id=trace_id,
            created_at=datetime.now(UTC),
        )
        self._session.add(model)
        await self._session.flush()
        return model.id

    async def list_pending(self, workspace_id: UUID, limit: int = 50) -> list[ReviewQueueModel]:
        stmt = (
            select(ReviewQueueModel)
            .where(
                ReviewQueueModel.workspace_id == workspace_id,
                ReviewQueueModel.status == "pending",
            )
            .order_by(ReviewQueueModel.created_at.asc())
            .limit(limit)
        )
        return list(await self._session.scalars(stmt))

    async def get_for_workspace(
        self, review_id: UUID, workspace_id: UUID
    ) -> ReviewQueueModel | None:
        stmt = select(ReviewQueueModel).where(
            ReviewQueueModel.id == review_id,
            ReviewQueueModel.workspace_id == workspace_id,
        )
        return await self._session.scalar(stmt)

    async def review(
        self,
        review_id: UUID,
        workspace_id: UUID,
        reviewer_id: UUID,
        status: str,
        notes: str | None = None,
    ) -> ReviewQueueModel | None:
        model = await self.get_for_workspace(review_id, workspace_id)
        if model is None:
            return None
        if model.status != "pending":
            raise ValueError("Review item is no longer pending")
        if model.requester_id == reviewer_id:
            raise PermissionError("Reviewer cannot approve their own queued answer")

        model.status = status
        model.reviewer_id = reviewer_id
        model.reviewer_notes = notes
        model.reviewed_at = datetime.now(UTC)
        await self._session.flush()
        return model
