from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class KnowledgeAssetResponse(BaseModel):
    id: UUID
    workspace_id: UUID
    filename: str
    content_hash: str
    mime_type: str
    page_count: int | None
    status: str
    layer: str
    pipeline_version: str
    superseded_by: UUID | None
    created_at: datetime


class GraphEdgeResponse(BaseModel):
    id: UUID
    source_id: UUID
    source_type: str
    target_id: UUID
    target_type: str
    edge_type: str
    metadata: dict[str, Any]


class DerivedArtifactResponse(BaseModel):
    id: UUID
    source_asset_id: UUID
    artifact_type: str
    content: dict[str, Any]
    status: str
    layer: str
    created_at: datetime


class SessionCreateRequest(BaseModel):
    agent_id: str


class SessionResponse(BaseModel):
    session_id: UUID
    workspace_id: UUID
    agent_id: str


class QueryRequest(BaseModel):
    question: str = Field(min_length=1, max_length=4000)


class TrustVectorResponse(BaseModel):
    source_trust: float
    retrieval_trust: float
    reasoning_trust: float
    groundedness: float
    overall: float
    threshold_met: bool
    explanation: str


class CitationResponse(BaseModel):
    claim_id: str
    chunk_id: str
    document_id: str
    page: int | None
    text_excerpt: str
    confidence: float


class QueryResponse(BaseModel):
    answer: str
    withheld: bool
    trust: TrustVectorResponse
    citations: list[CitationResponse]
    evidence_count: int
    session_id: UUID
