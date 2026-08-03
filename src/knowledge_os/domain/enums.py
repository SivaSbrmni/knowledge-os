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


class EventTopic(StrEnum):
    """Durable event bus topics."""

    KNOWLEDGE = "knowledge"
    SESSION = "session"
    AUDIT = "audit"
    AGENT = "agent"
    TENANT = "tenant"
