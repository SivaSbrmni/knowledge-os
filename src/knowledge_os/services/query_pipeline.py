"""Phase 4 query pipeline — delegates to agentic mesh orchestrator."""

from uuid import UUID

from knowledge_os.domain.knowledge import CitedResponse
from knowledge_os.ports.knowledge import KnowledgeProvider
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.ports.repositories import EventBus
from knowledge_os.services.mesh.orchestrator import MeshOrchestrator


class QueryPipeline:
    """Thin facade over the mesh orchestrator (backward-compatible API)."""

    def __init__(
        self,
        provider: KnowledgeProvider,
        llm_gateway: LLMGateway | None = None,
        event_bus: EventBus | None = None,
    ):
        self._mesh = MeshOrchestrator.build_default(provider, llm_gateway, event_bus)

    async def query(
        self,
        question: str,
        workspace_id: UUID,
        agent_config: dict,
        session_messages: list[dict] | None = None,
    ) -> CitedResponse:
        return await self._mesh.execute(
            question=question,
            workspace_id=workspace_id,
            agent_config=agent_config,
            session_messages=session_messages,
        )
