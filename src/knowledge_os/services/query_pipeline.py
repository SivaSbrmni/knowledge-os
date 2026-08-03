"""Phase 3 query pipeline: intent → retrieve → reason → cite → trust → assemble."""

from uuid import UUID

import structlog

from knowledge_os.domain.knowledge import CitedResponse, EvidencePacket, ReasonedClaim
from knowledge_os.ports.knowledge import KnowledgeProvider
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.services.reasoning_agent import ReasoningAgent
from knowledge_os.services.trust_evaluator import detect_conflicts, evaluate_trust

logger = structlog.get_logger()


class QueryPipeline:
    """
    Fixed DAG (Phase 3 inference runtime):
    Intent → Retrieve → Reason → Cite → Trust → Assemble
    """

    def __init__(self, provider: KnowledgeProvider, llm_gateway: LLMGateway | None = None):
        self._provider = provider
        self._reasoning = ReasoningAgent(llm_gateway)

    async def query(
        self,
        question: str,
        workspace_id: UUID,
        agent_config: dict,
        session_messages: list[dict] | None = None,
    ) -> CitedResponse:
        intent = self._analyze_intent(question)
        logger.info("query_intent", intent=intent, workspace_id=str(workspace_id))

        knowledge_policy = agent_config.get("knowledge_policy", {})
        reasoning_policy = agent_config.get("reasoning_policy", {})
        trust_policy = agent_config.get("trust_policy", {})

        allowed_layers = knowledge_policy.get("allowed_layers", ["tenant"])
        from knowledge_os.config import get_settings

        platform_ws = UUID(get_settings().platform_workspace_id)

        can_answer = await self._provider.can_answer(question, workspace_id)
        packets = await self._provider.retrieve_evidence(
            question,
            workspace_id,
            top_k=5,
            allowed_layers=allowed_layers,
            platform_workspace_id=platform_ws,
            knowledge_policy=knowledge_policy,
            agent_config=agent_config,
        )

        min_packets = reasoning_policy.get("min_evidence_packets", 1)
        if can_answer < 0.3 or len(packets) < min_packets:
            return self._withhold_response(
                "I cannot confidently answer this — insufficient evidence in your knowledge base.",
                packets,
                trust_policy,
                reasoning_policy,
            )

        conflicts = detect_conflicts(packets)
        packets, conflicts = self._apply_conflict_behavior(
            packets, conflicts, reasoning_policy.get("conflict_behavior", "surface_and_explain")
        )

        if reasoning_policy.get("conflict_behavior") == "withhold" and conflicts:
            return self._withhold_response(
                "I cannot confidently answer this — conflicting evidence detected.",
                packets,
                trust_policy,
                reasoning_policy,
                conflicts=conflicts,
            )

        claims, answer, llm_used = await self._reasoning.reason(
            question,
            packets,
            workspace_id,
            agent_config,
            intent=intent,
            session_messages=session_messages,
        )

        grounding_required = reasoning_policy.get("grounding_required", True)
        if grounding_required and claims and not any(c.evidence_packet_ids for c in claims):
            return self._withhold_response(
                "I cannot confidently answer this — answer is not grounded in evidence.",
                packets,
                trust_policy,
                reasoning_policy,
                conflicts=conflicts,
            )

        if conflicts and reasoning_policy.get("conflict_behavior") == "surface_and_explain":
            answer = self._surface_conflicts(answer, conflicts)

        citations = self._build_citations(claims, packets)
        conflict_behavior = reasoning_policy.get("conflict_behavior", "surface_and_explain")
        trust = evaluate_trust(
            packets,
            claims,
            trust_policy,
            conflicts=conflicts,
            llm_used=llm_used,
            grounding_required=grounding_required,
            conflicts_block_threshold=conflict_behavior != "surface_and_explain",
        )

        if trust_policy.get("withhold_below_threshold") and not trust.threshold_met:
            return CitedResponse(
                answer="I cannot confidently answer this — trust threshold not met.",
                claims=claims,
                evidence_packets=packets,
                citations=citations,
                trust=trust,
                withheld=True,
                show_trust_vector=trust_policy.get("show_trust_vector", True),
            )

        return CitedResponse(
            answer=answer,
            claims=claims,
            evidence_packets=packets,
            citations=citations,
            trust=trust,
            withheld=False,
            show_trust_vector=trust_policy.get("show_trust_vector", True),
        )

    def _analyze_intent(self, question: str) -> str:
        q = question.lower()
        if any(w in q for w in ("quiz", "test me", "mcq")):
            return "quiz"
        if any(w in q for w in ("summarize", "summary")):
            return "summarize"
        return "question"

    def _apply_conflict_behavior(
        self,
        packets: list[EvidencePacket],
        conflicts: list[str],
        conflict_behavior: str,
    ) -> tuple[list[EvidencePacket], list[str]]:
        if not conflicts:
            return packets, conflicts
        if conflict_behavior == "prefer_authority":
            authoritative = [p for p in packets if p.authority_flag]
            if authoritative:
                return authoritative, []
        return packets, conflicts

    def _surface_conflicts(self, answer: str, conflicts: list[str]) -> str:
        note = "Note: conflicting evidence was detected in your knowledge base.\n" + "\n".join(
            f"- {c}" for c in conflicts
        )
        return f"{note}\n\n{answer}"

    def _build_citations(
        self, claims: list[ReasonedClaim], packets: list[EvidencePacket]
    ) -> list[dict]:
        packet_map = {str(p.chunk_id): p for p in packets}
        citations = []
        for claim in claims:
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
        return citations

    def _withhold_response(
        self,
        message: str,
        packets: list[EvidencePacket],
        trust_policy: dict,
        reasoning_policy: dict,
        *,
        conflicts: list[str] | None = None,
    ) -> CitedResponse:
        trust = evaluate_trust(
            packets,
            [],
            trust_policy,
            conflicts=conflicts,
            llm_used=False,
            grounding_required=reasoning_policy.get("grounding_required", True),
        )
        return CitedResponse(
            answer=message,
            claims=[],
            evidence_packets=packets,
            citations=[],
            trust=trust,
            withheld=True,
            show_trust_vector=trust_policy.get("show_trust_vector", True),
        )
