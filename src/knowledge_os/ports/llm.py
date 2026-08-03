from abc import ABC, abstractmethod
from uuid import UUID

from knowledge_os.domain.llm import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMPolicy,
    ProviderCredential,
    ProviderEndpoint,
)


class CredentialStore(ABC):
    """Tenant-scoped secret vault for API keys, PATs, and bearer tokens."""

    @abstractmethod
    async def store(
        self,
        workspace_id: UUID,
        credential_ref: str,
        provider: str,
        auth_type: str,
        secret: str,
        description: str,
        created_by: UUID | None,
    ) -> ProviderCredential:
        pass

    @abstractmethod
    async def resolve_secret(
        self, workspace_id: UUID, credential_ref: str
    ) -> str | None:
        """Resolve token for runtime use. Never log or persist in audit."""
        pass

    @abstractmethod
    async def get_metadata(
        self, workspace_id: UUID, credential_ref: str
    ) -> ProviderCredential | None:
        pass

    @abstractmethod
    async def list_credentials(self, workspace_id: UUID) -> list[ProviderCredential]:
        pass

    @abstractmethod
    async def deactivate(self, workspace_id: UUID, credential_ref: str) -> None:
        pass


class LLMProviderAdapter(ABC):
    """Adapter for a single open-LLM hosting provider (OpenAI-compatible where possible)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

    @abstractmethod
    async def chat_completion(
        self,
        endpoint: ProviderEndpoint,
        request: ChatCompletionRequest,
        api_token: str | None,
    ) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def embed(
        self,
        endpoint: ProviderEndpoint,
        request: EmbeddingRequest,
        api_token: str | None,
    ) -> EmbeddingResponse:
        pass

    @abstractmethod
    async def health_check(
        self, endpoint: ProviderEndpoint, api_token: str | None
    ) -> bool:
        pass


class LLMGateway(ABC):
    """
    Routes inference and embedding calls per agent llm_policy.
    Resolves credentials, enforces open-source policy, handles fallbacks.
    """

    @abstractmethod
    async def chat(
        self,
        policy: LLMPolicy,
        workspace_id: UUID,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        pass

    @abstractmethod
    async def embed(
        self,
        policy: LLMPolicy,
        workspace_id: UUID,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        pass

    @abstractmethod
    async def validate_policy(
        self, policy: LLMPolicy, workspace_id: UUID
    ) -> list[str]:
        """Pre-flight check: credentials exist, models are open-source if required."""
        pass
