"""Knowledge domain models — immutable assets, derived chunks, evidence packets."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class VersionVector:
    asset_id: UUID
    content_hash: str
    ingest_run_id: UUID
    effective_date: datetime


@dataclass(frozen=True)
class KnowledgeAsset:
    """Immutable original source document."""

    id: UUID
    workspace_id: UUID
    filename: str
    content_hash: str
    storage_path: str
    mime_type: str
    page_count: int | None
    status: str
    layer: str
    ingest_run_id: UUID | None
    pipeline_version: str
    superseded_by: UUID | None
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeChunk:
    """Derived chunk pointing to an immutable asset."""

    id: UUID
    asset_id: UUID
    workspace_id: UUID
    chunk_index: int
    text: str
    page: int | None
    section: str | None
    token_count: int
    layer: str
    created_at: datetime


@dataclass(frozen=True)
class KnowledgeEdge:
    id: UUID
    workspace_id: UUID
    source_id: UUID
    source_type: str
    target_id: UUID
    target_type: str
    edge_type: str
    metadata: dict[str, Any]
    created_at: datetime


@dataclass(frozen=True)
class DerivedArtifact:
    id: UUID
    workspace_id: UUID
    source_asset_id: UUID
    artifact_type: str
    content: dict[str, Any]
    status: str
    layer: str
    created_at: datetime


@dataclass(frozen=True)
class IngestionRun:
    id: UUID
    workspace_id: UUID
    content_hash: str
    pipeline_version: str
    asset_id: UUID | None
    status: str
    created_at: datetime


@dataclass(frozen=True)
class ChunkEmbedding:
    chunk_id: UUID
    workspace_id: UUID
    model_id: str
    dimensions: int


@dataclass(frozen=True)
class EvidencePacket:
    """Core data contract passed between mesh nodes."""

    claim: str
    chunk_id: UUID
    document_id: UUID
    source_id: UUID
    layer: str
    tenant_scope: UUID
    text: str
    page: int | None
    section: str | None
    version: dict[str, Any]
    timestamp: str
    confidence: float
    freshness: float
    trust_level: str
    authority_flag: bool
    reasoning_path: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReasonedClaim:
    claim_id: str
    text: str
    evidence_packet_ids: list[str]
    reasoning_path: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class TrustVector:
    source_trust: float
    retrieval_trust: float
    reasoning_trust: float
    groundedness: float
    overall: float
    threshold_met: bool
    explanation: str
    conflicts: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CitedResponse:
    answer: str
    claims: list[ReasonedClaim]
    evidence_packets: list[EvidencePacket]
    citations: list[dict[str, Any]]
    trust: TrustVector
    withheld: bool
    show_trust_vector: bool = True
