"""Mesh orchestrator — runs configurable DAG of agentic nodes."""

from uuid import UUID

import structlog

from knowledge_os.domain.knowledge import CitedResponse, TrustVector
from knowledge_os.domain.mesh import MeshContext
from knowledge_os.domain.utils import new_trace_id
from knowledge_os.ports.knowledge import KnowledgeProvider
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.ports.mesh import MeshNode
from knowledge_os.ports.repositories import EventBus
from knowledge_os.services.mesh.nodes import (
    CitationBuilderNode,
    ConflictDetectorNode,
    IntentAnalyzerNode,
    KnowledgeRouterNode,
    ReasoningAgentNode,
    ResponseAssemblerNode,
    TrustEvaluatorNode,
)
from knowledge_os.services.trust_evaluator import evaluate_trust

logger = structlog.get_logger()

DEFAULT_DAG = [
    "intent_analyzer",
    "knowledge_router",
    "conflict_detector",
    "reasoning_agent",
    "citation_builder",
    "trust_evaluator",
    "response_assembler",
]


class MeshOrchestrator:
    def __init__(self, nodes: dict[str, MeshNode], event_bus: EventBus | None = None):
        self._nodes = nodes
        self._event_bus = event_bus

    @classmethod
    def build_default(
        cls,
        provider: KnowledgeProvider,
        llm_gateway: LLMGateway | None = None,
        event_bus: EventBus | None = None,
    ) -> "MeshOrchestrator":
        registry: dict[str, MeshNode] = {
            IntentAnalyzerNode.node_id: IntentAnalyzerNode(),
            KnowledgeRouterNode.node_id: KnowledgeRouterNode(provider),
            ConflictDetectorNode.node_id: ConflictDetectorNode(),
            ReasoningAgentNode.node_id: ReasoningAgentNode(llm_gateway),
            CitationBuilderNode.node_id: CitationBuilderNode(),
            TrustEvaluatorNode.node_id: TrustEvaluatorNode(),
            ResponseAssemblerNode.node_id: ResponseAssemblerNode(),
        }
        return cls(registry, event_bus)

    def resolve_dag(self, agent_config: dict) -> list[str]:
        mesh_policy = agent_config.get("mesh_policy", {})
        if mesh_policy.get("enabled") is False:
            return DEFAULT_DAG
        return mesh_policy.get("dag", DEFAULT_DAG)

    async def execute(
        self,
        question: str,
        workspace_id: UUID,
        agent_config: dict,
        session_messages: list[dict] | None = None,
        trace_id: str | None = None,
    ) -> CitedResponse:
        trace_id = trace_id or new_trace_id()
        ctx = MeshContext(
            question=question,
            workspace_id=workspace_id,
            agent_config=agent_config,
            session_messages=session_messages or [],
            trace_id=trace_id,
        )

        dag = self.resolve_dag(agent_config)
        logger.info("mesh_execute_start", trace_id=trace_id, dag=dag)

        for node_id in dag:
            node = self._nodes.get(node_id)
            if node is None:
                logger.warning("mesh_node_unknown", node_id=node_id)
                continue
            ctx = await node.run(ctx)
            await self._emit_node_event(ctx, node_id)
            if ctx.stop:
                break

        return self._to_response(ctx)

    async def _emit_node_event(self, ctx: MeshContext, node_id: str) -> None:
        if self._event_bus is None:
            return
        from knowledge_os.adapters.messaging.event_bus import build_platform_event

        event = build_platform_event(
            topic="mesh.node.completed",
            event_type="mesh.node.completed",
            trace_id=ctx.trace_id,
            workspace_id=ctx.workspace_id,
            payload={
                "node_id": node_id,
                "withheld": ctx.withheld,
                "packet_count": len(ctx.packets),
                "node_trace": list(ctx.node_trace),
            },
        )
        await self._event_bus.publish(event)

    def _to_response(self, ctx: MeshContext) -> CitedResponse:
        trust = ctx.trust or evaluate_trust(
            ctx.packets,
            ctx.claims,
            ctx.trust_policy,
            conflicts=ctx.conflicts,
            llm_used=ctx.llm_used,
            grounding_required=ctx.reasoning_policy.get("grounding_required", True),
        )

        if ctx.withheld:
            return CitedResponse(
                answer=ctx.withhold_message,
                claims=ctx.claims if ctx.claims else [],
                evidence_packets=ctx.packets,
                citations=ctx.citations,
                trust=trust,
                withheld=True,
                show_trust_vector=ctx.show_trust_vector,
            )

        return CitedResponse(
            answer=ctx.answer,
            claims=ctx.claims,
            evidence_packets=ctx.packets,
            citations=ctx.citations,
            trust=trust,
            withheld=False,
            show_trust_vector=ctx.show_trust_vector,
        )
