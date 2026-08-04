"""Tests for trust evaluation and conflict detection."""

from uuid import uuid4

import pytest

from knowledge_os.domain.knowledge import EvidencePacket, ReasonedClaim
from knowledge_os.services.trust_evaluator import (
    compute_freshness,
    detect_conflicts,
    evaluate_trust,
)


def _packet(text: str, *, doc_id=None, confidence: float = 0.9, freshness: float = 1.0) -> EvidencePacket:
    cid = uuid4()
    did = doc_id or uuid4()
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
        confidence=confidence,
        freshness=freshness,
        trust_level="tenant",
        authority_flag=False,
    )


def test_compute_freshness_within_window():
    assert compute_freshness(10, 100) == pytest.approx(0.9)


def test_compute_freshness_expired():
    assert compute_freshness(400, 365) == 0.0


def test_detect_conflicts_finds_contradiction():
    left = _packet("The President is not elected by direct vote.", doc_id=uuid4())
    right = _packet("The President is elected by direct vote.", doc_id=uuid4())
    conflicts = detect_conflicts([left, right])
    assert len(conflicts) == 1


def test_detect_conflicts_ignores_same_document():
    doc_id = uuid4()
    left = _packet("The President is not elected by direct vote.", doc_id=doc_id)
    right = _packet("The President is elected by direct vote.", doc_id=doc_id)
    assert detect_conflicts([left, right]) == []


def test_evaluate_trust_penalizes_conflicts():
    packets = [_packet("Evidence text about electoral college composition.")]
    claims = [
        ReasonedClaim(
            claim_id="c1",
            text="Claim",
            evidence_packet_ids=[str(packets[0].chunk_id)],
        )
    ]
    trust = evaluate_trust(
        packets,
        claims,
        {"min_source_trust": 0.5, "min_groundedness": 0.5},
        conflicts=["conflict detected"],
        llm_used=True,
    )
    assert trust.threshold_met is False
    assert trust.conflicts == ["conflict detected"]
    assert trust.reasoning_trust <= 0.9


def test_evaluate_trust_passes_with_llm_and_grounding():
    packets = [_packet("The President is elected by an electoral college.", confidence=0.9)]
    claims = [
        ReasonedClaim(
            claim_id="c1",
            text="Grounded claim",
            evidence_packet_ids=[str(packets[0].chunk_id)],
        )
    ]
    trust = evaluate_trust(
        packets,
        claims,
        {"min_source_trust": 0.5, "min_groundedness": 0.5},
        llm_used=True,
        grounding_required=True,
    )
    assert trust.threshold_met is True
    assert trust.reasoning_trust >= 0.9
