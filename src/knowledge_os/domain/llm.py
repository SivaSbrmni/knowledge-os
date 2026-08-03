"""Domain models for open-source LLM inference."""

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class ModelSpec:
    model_id: str
    model_family: str
    open_source: bool
    license: str | None = None
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderEndpoint:
    """A single LLM provider endpoint — tokens resolved via credential_ref at runtime."""

    provider: str
    auth_type: str
    model: ModelSpec
    credential_ref: str | None = None
    base_url: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMPolicy:
    require_open_source: bool
    inference_primary: ProviderEndpoint
    inference_fallbacks: list[ProviderEndpoint]
    embedding: ProviderEndpoint


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatCompletionRequest:
    messages: list[ChatMessage]
    model_id: str
    temperature: float = 0.2
    max_tokens: int = 4096
    top_p: float | None = None


@dataclass(frozen=True)
class ChatCompletionResponse:
    content: str
    model_id: str
    provider: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    finish_reason: str | None = None


@dataclass(frozen=True)
class EmbeddingRequest:
    texts: list[str]
    model_id: str


@dataclass(frozen=True)
class EmbeddingResponse:
    embeddings: list[list[float]]
    model_id: str
    provider: str


@dataclass(frozen=True)
class ProviderCredential:
    """Tenant-scoped secret — never exposed in agent config or API responses."""

    id: UUID
    workspace_id: UUID
    credential_ref: str
    provider: str
    auth_type: str
    description: str
    is_active: bool
    created_by: UUID | None
