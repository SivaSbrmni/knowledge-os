from enum import StrEnum


class Role(StrEnum):
    """Workspace-scoped RBAC roles."""

    PLATFORM_ADMIN = "platform_admin"
    ORG_ADMIN = "org_admin"
    WORKSPACE_ADMIN = "workspace_admin"
    MENTOR = "mentor"
    LEARNER = "learner"
    VIEWER = "viewer"


class KnowledgeLayer(StrEnum):
    FOUNDATION = "foundation"
    PLATFORM_PUBLIC = "platform_public"
    TENANT = "tenant"
    PERSONAL = "personal"


class GraphEdgeType(StrEnum):
    CITES = "cites"
    DERIVED_FROM = "derived_from"
    SUPERSEDES = "supersedes"
    ANNOTATES = "annotates"
    CONFLICTS_WITH = "conflicts_with"


class DerivedArtifactType(StrEnum):
    SUMMARY = "summary"
    FLASHCARD = "flashcard"
    MIND_MAP = "mind_map"
    QUIZ = "quiz"


class IngestionEventType(StrEnum):
    ASSET_UPLOADED = "knowledge.asset.uploaded"
    CHUNK_CREATED = "knowledge.chunk.created"
    EMBEDDING_COMPLETED = "knowledge.embedding.completed"
    GRAPH_INDEXED = "knowledge.graph.indexed"
    ASSET_READY = "knowledge.asset.ready"
    ASSET_SUPERSEDED = "knowledge.asset.superseded"
    DERIVED_READY = "knowledge.derived.artifact.ready"


class EventTopic(StrEnum):
    """Durable event bus topics."""

    KNOWLEDGE = "knowledge"
    SESSION = "session"
    AUDIT = "audit"
    AGENT = "agent"
    TENANT = "tenant"
