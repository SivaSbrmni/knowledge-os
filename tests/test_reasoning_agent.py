"""Tests for reasoning agent behavior."""

from uuid import uuid4

import pytest

from knowledge_os.domain.knowledge import EvidencePacket
from knowledge_os.services.reasoning_agent import ReasoningAgent


def _packet(text: str) -> EvidencePacket:
    cid = uuid4()
    did = uuid4()
    return EvidencePacket(
        claim=text[:50],
        chunk_id=cid,
        document_id=did,
        source_id=did,
        layer="tenant",
        tenant_scope=uuid4(),
        text=text,
        page=1,
        section=None,
        version={},
        timestamp="2026-01-01T00:00:00Z",
        confidence=0.9,
        freshness=1.0,
        trust_level="tenant",
        authority_flag=False,
    )


@pytest.mark.asyncio
async def test_reasoning_fallback_includes_chunk_reference():
    agent = ReasoningAgent(llm_gateway=None)
    packets = [_packet("The President is elected by an electoral college.")]
    claims, answer, llm_used = await agent.reason(
        "How is the President elected?",
        packets,
        uuid4(),
        {"schema_version": "2.1", "memory_policy": {"session_memory": "enabled"}},
        session_messages=[{"role": "user", "content": "Hello"}],
    )
    assert llm_used is False
    assert f"[CHUNK:{packets[0].chunk_id}]" in answer
    assert len(claims) >= 1
    assert all(claims[0].evidence_packet_ids)
