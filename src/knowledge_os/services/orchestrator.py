"""Session orchestrator — thin stateless coordinator for Phase 1 query plane."""

from uuid import UUID

import structlog

from knowledge_os.adapters.session.redis_store import RedisSessionStore, SessionContext
from knowledge_os.domain.knowledge import CitedResponse
from knowledge_os.ports.repositories import AgentRepository
from knowledge_os.services.query_pipeline import QueryPipeline

logger = structlog.get_logger()


class SessionOrchestrator:
    def __init__(
        self,
        session_store: RedisSessionStore,
        agent_repo: AgentRepository,
        query_pipeline: QueryPipeline,
    ):
        self._sessions = session_store
        self._agent_repo = agent_repo
        self._pipeline = query_pipeline

    async def create_session(self, workspace_id: UUID, agent_id: str) -> SessionContext:
        version = await self._agent_repo.get_active_version(agent_id, workspace_id)
        if version is None:
            raise ValueError(f"No active agent '{agent_id}' in workspace")
        return await self._sessions.create(workspace_id, agent_id)

    async def query(
        self,
        session_id: UUID,
        question: str,
    ) -> tuple[SessionContext, CitedResponse]:
        ctx = await self._sessions.get(session_id)
        if ctx is None:
            raise ValueError("Session not found")

        version = await self._agent_repo.get_active_version(ctx.agent_id, ctx.workspace_id)
        if version is None:
            raise ValueError("Agent configuration not found")

        response = await self._pipeline.query(
            question=question,
            workspace_id=ctx.workspace_id,
            agent_config=version.config,
        )

        ctx.messages.append({"role": "user", "content": question})
        ctx.messages.append({"role": "assistant", "content": response.answer})
        await self._sessions.save(ctx)

        logger.info(
            "session_query_complete",
            session_id=str(session_id),
            withheld=response.withheld,
            trust_overall=response.trust.overall,
        )
        return ctx, response
