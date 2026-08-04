"""Reasoning agent — LLM-grounded answers with session memory and intent modes."""

import re
from uuid import UUID, uuid4

import structlog

from knowledge_os.domain.knowledge import EvidencePacket, ReasonedClaim
from knowledge_os.domain.llm import ChatCompletionRequest, ChatMessage
from knowledge_os.ports.llm import LLMGateway
from knowledge_os.schemas.llm_policy import parse_llm_policy

logger = structlog.get_logger()

_INTENT_PROMPTS = {
    "question": (
        "You are a knowledge-grounded mentor. Answer ONLY using the evidence below. "
        "For every claim, reference the chunk ID in brackets like [CHUNK:uuid]. "
        "If evidence is insufficient, say you don't know."
    ),
    "summarize": (
        "You are a knowledge-grounded mentor. Summarize the relevant evidence below for the user. "
        "Reference chunk IDs like [CHUNK:uuid] for each point. Do not add outside knowledge."
    ),
    "quiz": (
        "You are a knowledge-grounded mentor. Create a short quiz (2-3 MCQs) from the evidence below. "
        "Reference chunk IDs like [CHUNK:uuid]. Only use facts present in the evidence."
    ),
}


class ReasoningAgent:
    def __init__(self, llm_gateway: LLMGateway | None = None):
        self._llm_gateway = llm_gateway

    async def reason(
        self,
        question: str,
        packets: list[EvidencePacket],
        workspace_id: UUID,
        agent_config: dict,
        *,
        intent: str = "question",
        session_messages: list[dict] | None = None,
    ) -> tuple[list[ReasonedClaim], str, bool]:
        reasoning_policy = agent_config.get("reasoning_policy", {})
        memory_policy = agent_config.get("memory_policy", {})
        allow_recall = reasoning_policy.get("allow_foundation_model_recall", False)

        system_prompt = _INTENT_PROMPTS.get(intent, _INTENT_PROMPTS["question"])
        if not allow_recall:
            system_prompt += " Do not use outside knowledge."

        evidence_block = "\n\n".join(f"[CHUNK:{p.chunk_id}]\n{p.text}" for p in packets)
        user_parts: list[str] = []

        if memory_policy.get("session_memory") == "enabled" and session_messages:
            history = "\n".join(
                f"{msg['role']}: {msg['content']}" for msg in session_messages[-6:]
            )
            user_parts.append(f"Prior conversation:\n{history}")

        user_parts.append(f"Evidence:\n{evidence_block}")
        user_parts.append(f"Question: {question}")
        user_prompt = "\n\n".join(user_parts)

        llm_used = False
        if self._llm_gateway and agent_config.get("schema_version") == "2.1":
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
                llm_used = True
            except Exception as exc:
                logger.warning("llm_reason_fallback", error=str(exc))
                answer = self._fallback_answer(question, packets)
        else:
            answer = self._fallback_answer(question, packets)

        claims = self._extract_claims(answer, packets)
        return claims, answer, llm_used

    def _fallback_answer(self, question: str, packets: list[EvidencePacket]) -> str:
        if not packets:
            return "I don't have enough information to answer that."
        top = packets[0]
        return f"{top.text[:800]} [CHUNK:{top.chunk_id}]"

    def _extract_claims(
        self, answer: str, packets: list[EvidencePacket]
    ) -> list[ReasonedClaim]:
        chunk_ids = {str(p.chunk_id) for p in packets}
        global_refs = [
            ref for ref in re.findall(r"\[CHUNK:([a-f0-9-]{36})\]", answer, re.I) if ref in chunk_ids
        ]
        claims: list[ReasonedClaim] = []
        for sentence in re.split(r"(?<=[.!?])\s+", answer.strip()):
            stripped = sentence.strip()
            if not stripped:
                continue
            if re.fullmatch(r"\[CHUNK:[a-f0-9-]{36}\]\.?", stripped, re.I):
                continue
            refs = re.findall(r"\[CHUNK:([a-f0-9-]{36})\]", stripped, re.I)
            valid_refs = [ref for ref in refs if ref in chunk_ids]
            if not valid_refs and global_refs:
                valid_refs = [global_refs[0]]
            claims.append(
                ReasonedClaim(
                    claim_id=str(uuid4()),
                    text=stripped,
                    evidence_packet_ids=valid_refs,
                    reasoning_path=["reasoning_agent"],
                )
            )
        return claims
