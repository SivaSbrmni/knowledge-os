from uuid import uuid4

import pytest

from knowledge_os.domain.knowledge import EvidencePacket
from knowledge_os.services.query_pipeline import QueryPipeline


class StubProvider:
    provider_id = "stub"

    def __init__(self, packets: list[EvidencePacket]):
        self._packets = packets

    async def can_answer(self, question, workspace_id):
        return 0.9 if self._packets else 0.0

    async def retrieve_evidence(self, question, workspace_id, top_k=5, **kwargs):
        return self._packets[:top_k]


def _packet(text: str, score: float = 0.85) -> EvidencePacket:
    cid = uuid4()
    did = uuid4()
    ws = uuid4()
    return EvidencePacket(
        claim="",
        chunk_id=cid,
        document_id=did,
        source_id=did,
        layer="tenant",
        tenant_scope=ws,
        text=text,
        page=1,
        section=None,
        version={"asset_id": str(did)},
        timestamp="2026-01-01T00:00:00Z",
        confidence=score,
        freshness=1.0,
        trust_level="tenant",
        authority_flag=False,
    )


@pytest.mark.asyncio
async def test_query_with_evidence_returns_citations():
    packets = [
        _packet("The President of India is elected by an electoral college."),
        _packet("Article 54 defines the electoral college composition."),
    ]
    pipeline = QueryPipeline(StubProvider(packets))
    agent_config = {
        "reasoning_policy": {"min_evidence_packets": 1},
        "trust_policy": {
            "min_source_trust": 0.5,
            "min_groundedness": 0.5,
            "withhold_below_threshold": True,
        },
    }
    response = await pipeline.query(
        "How is the President elected?",
        packets[0].tenant_scope,
        agent_config,
    )
    assert not response.withheld
    assert len(response.citations) >= 1
    assert response.trust.groundedness > 0


@pytest.mark.asyncio
async def test_query_without_evidence_withholds():
    pipeline = QueryPipeline(StubProvider([]))
    agent_config = {
        "reasoning_policy": {"min_evidence_packets": 1},
        "trust_policy": {"withhold_below_threshold": True},
    }
    response = await pipeline.query("Anything?", uuid4(), agent_config)
    assert response.withheld
