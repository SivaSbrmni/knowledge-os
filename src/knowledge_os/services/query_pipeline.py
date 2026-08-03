"""Phase 1 linear query pipeline: retrieve → reason → cite → trust."""

import re
from uuid import UUID, uuid4

import structlog

from knowledge_os.domain.knowledge import (
    CitedResponse,
    EvidencePacket,
    ReasonedClaim,
    TrustVector,
)
from knowledge_os.domain.llm import ChatCompletionRequest, ChatMessage
from knowledge_os.ports.knowledge import KnowledgeProvider
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.schemas.llm_policy import parse_llm_policy

logger = structlog.get_logger()


class QueryPipeline:
    """
    Fixed DAG (Phase 1 — not full mesh):
    Intent → Retrieve → Reason → Cite → Trust → Assemble
    """

    def __init__(self, provider: KnowledgeProvider, llm_gateway: LLMGateway | None = None):
        self._provider = provider
        self._llm_gateway = llm_gateway

    async def query(
        self,
        question: str,
        workspace_id: UUID,
        agent_config: dict,
    ) -> CitedResponse:
        intent = self._analyze_intent(question)
        logger.info("query_intent", intent=intent, workspace_id=str(workspace_id))

        can_answer = await self._provider.can_answer(question, workspace_id)
        packets = await self._provider.retrieve_evidence(question, workspace_id, top_k=5)

        min_packets = agent_config.get("reasoning_policy", {}).get("min_evidence_packets", 1)
        trust_policy = agent_config.get("trust_policy", {})

        if can_answer < 0.3 or len(packets) < min_packets:
            return self._withhold_response(
                "I cannot confidently answer this — insufficient evidence in your knowledge base.",
                packets,
                trust_policy,
            )

        claims, answer = await self._reason(question, packets, workspace_id, agent_config)
        citations = self._build_citations(claims, packets)
        trust = self._evaluate_trust(packets, claims, trust_policy)

        if trust_policy.get("withhold_below_threshold") and not trust.threshold_met:
            return CitedResponse(
                answer="I cannot confidently answer this — trust threshold not met.",
                claims=claims,
                evidence_packets=packets,
                citations=citations,
                trust=trust,
                withheld=True,
            )

        return CitedResponse(
            answer=answer,
            claims=claims,
            evidence_packets=packets,
            citations=citations,
            trust=trust,
            withheld=False,
        )

    def _analyze_intent(self, question: str) -> str:
        q = question.lower()
        if any(w in q for w in ("quiz", "test me", "mcq")):
            return "quiz"
        if any(w in q for w in ("summarize", "summary")):
            return "summarize"
        return "question"

    async def _reason(
        self,
        question: str,
        packets: list[EvidencePacket],
        workspace_id: UUID,
        agent_config: dict,
    ) -> tuple[list[ReasonedClaim], str]:
        evidence_block = "\n\n".join(
            f"[CHUNK:{p.chunk_id}]\n{p.text}" for p in packets
        )
        system_prompt = (
            "You are a knowledge-grounded mentor. Answer ONLY using the evidence below. "
            "For every claim, reference the chunk ID in brackets like [CHUNK:uuid]. "
            "If evidence is insufficient, say you don't know. Do not use outside knowledge."
        )
        user_prompt = f"Evidence:\n{evidence_block}\n\nQuestion: {question}"

        if (
            self._llm_gateway
            and agent_config.get("schema_version") == "2.1"
        ):
            try:
                policy = parse_llm_policy(agent_config)
                response = await self._llm_gateway.chat(
                    policy,
                    workspace_id,
                    ChatCompletionRequest(
                        messages=[
                            ChatMessage(role="system", content=system_prompt),
                            ChatMessage(role="user", content=user_prompt),
                        ],
                        model_id=policy.inference_primary.model.model_id,
                        temperature=0.2,
                        max_tokens=2048,
                    ),
                )
                answer = response.content
            except Exception as exc:
                logger.warning("llm_reason_fallback", error=str(exc))
                answer = self._fallback_answer(question, packets)
        else:
            answer = self._fallback_answer(question, packets)

        claims = self._extract_claims(answer, packets)
        return claims, answer

    def _fallback_answer(self, question: str, packets: list[EvidencePacket]) -> str:
        if not packets:
            return "I don't have enough information to answer that."
        top = packets[0]
        return (
            f"Based on your uploaded knowledge ({top.page and f'page {top.page}, ' or ''}"
            f"confidence {top.confidence:.0%}):\n\n{top.text[:800]}\n\n"
            f"[CHUNK:{top.chunk_id}]"
        )

    def _extract_claims(
        self, answer: str, packets: list[EvidencePacket]
    ) -> list[ReasonedClaim]:
        chunk_ids = {str(p.chunk_id) for p in packets}
        claims: list[ReasonedClaim] = []
        sentences = re.split(r"(?<=[.!?])\s+", answer.strip())
        for i, sentence in enumerate(sentences):
            if not sentence.strip():
                continue
            refs = re.findall(r"\[CHUNK:([a-f0-9-]{36})\]", sentence, re.I)
            valid_refs = [r for r in refs if r in chunk_ids]
            if not valid_refs and packets:
                valid_refs = [str(packets[0].chunk_id)]
            claims.append(
                ReasonedClaim(
                    claim_id=str(uuid4()),
                    text=sentence.strip(),
                    evidence_packet_ids=valid_refs,
                    reasoning_path=["reasoning_agent"],
                )
            )
        return claims

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

    def _evaluate_trust(
        self,
        packets: list[EvidencePacket],
        claims: list[ReasonedClaim],
        trust_policy: dict,
    ) -> TrustVector:
        min_source = trust_policy.get("min_source_trust", 0.7)
        min_grounded = trust_policy.get("min_groundedness", 0.8)

        source_trust = sum(p.confidence for p in packets) / len(packets) if packets else 0.0
        retrieval_trust = min(1.0, len(packets) / 3.0)

        grounded = 0
        for claim in claims:
            if claim.evidence_packet_ids:
                grounded += 1
        groundedness = grounded / len(claims) if claims else 0.0

        reasoning_trust = 0.85 if claims else 0.0
        overall = (source_trust + retrieval_trust + reasoning_trust + groundedness) / 4.0
        threshold_met = (
            source_trust >= min_source
            and groundedness >= min_grounded
            and len(packets) > 0
        )

        return TrustVector(
            source_trust=round(source_trust, 3),
            retrieval_trust=round(retrieval_trust, 3),
            reasoning_trust=round(reasoning_trust, 3),
            groundedness=round(groundedness, 3),
            overall=round(overall, 3),
            threshold_met=threshold_met,
            explanation=(
                f"Grounded {grounded}/{len(claims)} claims from {len(packets)} evidence packets."
            ),
        )

    def _withhold_response(
        self, message: str, packets: list[EvidencePacket], trust_policy: dict
    ) -> CitedResponse:
        trust = self._evaluate_trust(packets, [], trust_policy)
        return CitedResponse(
            answer=message,
            claims=[],
            evidence_packets=packets,
            citations=[],
            trust=TrustVector(
                source_trust=trust.source_trust,
                retrieval_trust=trust.retrieval_trust,
                reasoning_trust=0.0,
                groundedness=0.0,
                overall=0.0,
                threshold_met=False,
                explanation="Insufficient evidence to answer.",
            ),
            withheld=True,
        )
