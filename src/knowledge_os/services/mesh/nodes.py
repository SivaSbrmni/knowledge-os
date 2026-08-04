"""Default agentic mesh nodes — independently composable pipeline stages."""

from uuid import UUID

import structlog

from knowledge_os.config import get_settings
from knowledge_os.domain.mesh import MeshContext
from knowledge_os.ports.knowledge import KnowledgeProvider
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.services.reasoning_agent import ReasoningAgent
from knowledge_os.services.trust_evaluator import detect_conflicts, evaluate_trust

logger = structlog.get_logger()


class IntentAnalyzerNode:
    node_id = "intent_analyzer"

    async def run(self, ctx: MeshContext) -> MeshContext:
        q = ctx.question.lower()
        if any(w in q for w in ("quiz", "test me", "mcq")):
            ctx.intent = "quiz"
        elif any(w in q for w in ("summarize", "summary")):
            ctx.intent = "summarize"
        else:
            ctx.intent = "question"
        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, intent=ctx.intent)
        return ctx


class KnowledgeRouterNode:
    node_id = "knowledge_router"

    def __init__(self, provider: KnowledgeProvider):
        self._provider = provider

    async def run(self, ctx: MeshContext) -> MeshContext:
        if ctx.stop:
            return ctx

        platform_ws = UUID(get_settings().platform_workspace_id)
        allowed_layers = ctx.knowledge_policy.get("allowed_layers", ["tenant"])

        ctx.can_answer_score = await self._provider.can_answer(ctx.question, ctx.workspace_id)
        ctx.packets = await self._provider.retrieve_evidence(
            ctx.question,
            ctx.workspace_id,
            top_k=5,
            allowed_layers=allowed_layers,
            platform_workspace_id=platform_ws,
            knowledge_policy=ctx.knowledge_policy,
            agent_config=ctx.agent_config,
        )

        min_packets = ctx.reasoning_policy.get("min_evidence_packets", 1)
        if ctx.can_answer_score < 0.3 or len(ctx.packets) < min_packets:
            ctx.halt("I cannot confidently answer this — insufficient evidence in your knowledge base.")

        ctx.node_trace.append(self.node_id)
        logger.info(
            "mesh_node_complete",
            node=self.node_id,
            packets=len(ctx.packets),
            can_answer=ctx.can_answer_score,
        )
        return ctx


class ConflictDetectorNode:
    node_id = "conflict_detector"

    async def run(self, ctx: MeshContext) -> MeshContext:
        if ctx.stop:
            return ctx

        ctx.conflicts = detect_conflicts(ctx.packets)
        behavior = ctx.reasoning_policy.get("conflict_behavior", "surface_and_explain")

        if ctx.conflicts and behavior == "prefer_authority":
            authoritative = [p for p in ctx.packets if p.authority_flag]
            if authoritative:
                ctx.packets = authoritative
                ctx.conflicts = []

        if ctx.conflicts and behavior == "withhold":
            ctx.halt("I cannot confidently answer this — conflicting evidence detected.")

        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, conflicts=len(ctx.conflicts))
        return ctx


class ReasoningAgentNode:
    node_id = "reasoning_agent"

    def __init__(self, llm_gateway: LLMGateway | None = None):
        self._agent = ReasoningAgent(llm_gateway)

    async def run(self, ctx: MeshContext) -> MeshContext:
        if ctx.stop:
            return ctx

        claims, answer, llm_used = await self._agent.reason(
            ctx.question,
            ctx.packets,
            ctx.workspace_id,
            ctx.agent_config,
            intent=ctx.intent,
            session_messages=ctx.session_messages,
        )
        ctx.claims = claims
        ctx.answer = answer
        ctx.llm_used = llm_used

        if ctx.reasoning_policy.get("grounding_required", True) and claims:
            if not any(c.evidence_packet_ids for c in claims):
                ctx.halt("I cannot confidently answer this — answer is not grounded in evidence.")

        if ctx.conflicts and ctx.reasoning_policy.get("conflict_behavior") == "surface_and_explain":
            note = "Note: conflicting evidence was detected in your knowledge base.\n" + "\n".join(
                f"- {c}" for c in ctx.conflicts
            )
            ctx.answer = f"{note}\n\n{ctx.answer}"

        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, claims=len(claims), llm_used=llm_used)
        return ctx


class CitationBuilderNode:
    node_id = "citation_builder"

    async def run(self, ctx: MeshContext) -> MeshContext:
        if ctx.stop:
            return ctx

        packet_map = {str(p.chunk_id): p for p in ctx.packets}
        citations = []
        for claim in ctx.claims:
            for ref in claim.evidence_packet_ids:
                pkt = packet_map.get(ref)
                if pkt:
                    citations.append({
                        "claim_id": claim.claim_id,
                        "chunk_id": str(pkt.chunk_id),
                        "document_id": str(pkt.document_id),
                        "page": pkt.page,
                        "text_excerpt": pkt.text[:200],
                        "confidence": pkt.confidence,
                    })
        ctx.citations = citations
        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, citations=len(citations))
        return ctx


class TrustEvaluatorNode:
    node_id = "trust_evaluator"

    async def run(self, ctx: MeshContext) -> MeshContext:
        behavior = ctx.reasoning_policy.get("conflict_behavior", "surface_and_explain")
        ctx.trust = evaluate_trust(
            ctx.packets,
            ctx.claims,
            ctx.trust_policy,
            conflicts=ctx.conflicts,
            llm_used=ctx.llm_used,
            grounding_required=ctx.reasoning_policy.get("grounding_required", True),
            conflicts_block_threshold=behavior != "surface_and_explain",
        )
        ctx.show_trust_vector = ctx.trust_policy.get("show_trust_vector", True)

        if (
            not ctx.stop
            and ctx.trust_policy.get("withhold_below_threshold")
            and not ctx.trust.threshold_met
        ):
            ctx.halt("I cannot confidently answer this — trust threshold not met.")

        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, trust_overall=ctx.trust.overall)
        return ctx


class ResponseAssemblerNode:
    node_id = "response_assembler"

    async def run(self, ctx: MeshContext) -> MeshContext:
        ctx.node_trace.append(self.node_id)
        logger.info("mesh_node_complete", node=self.node_id, withheld=ctx.withheld)
        return ctx
