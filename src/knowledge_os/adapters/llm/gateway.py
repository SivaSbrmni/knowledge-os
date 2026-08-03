from uuid import UUID

import structlog

from knowledge_os.adapters.llm.openai_compatible import create_provider_adapter
from knowledge_os.domain.llm import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMPolicy,
    ProviderEndpoint,
)
from knowledge_os.ports.llm import CredentialStore, LLMGateway
from knowledge_os.schemas.llm_policy import enforce_open_source_policy

logger = structlog.get_logger()


class AgentLLMGateway(LLMGateway):
    """
    Routes agent inference per llm_policy.
    Primary design: open-source Llama-family models via token-authenticated providers.
    """

    def __init__(self, credential_store: CredentialStore):
        self._credentials = credential_store
        self._adapters: dict[str, object] = {}

    def _get_adapter(self, provider: str):
        if provider not in self._adapters:
            self._adapters[provider] = create_provider_adapter(provider)
        return self._adapters[provider]

    async def _resolve_token(
        self, workspace_id: UUID, endpoint: ProviderEndpoint
    ) -> str | None:
        if endpoint.auth_type == "none":
            return None
        if not endpoint.credential_ref:
            raise ValueError(f"credential_ref missing for {endpoint.provider}")
        secret = await self._credentials.resolve_secret(workspace_id, endpoint.credential_ref)
        if secret is None:
            raise ValueError(
                f"Credential '{endpoint.credential_ref}' not found for workspace {workspace_id}"
            )
        return secret

    async def validate_policy(self, policy: LLMPolicy, workspace_id: UUID) -> list[str]:
        errors = list(enforce_open_source_policy(policy))
        endpoints = [policy.inference_primary, *policy.inference_fallbacks, policy.embedding]
        for ep in endpoints:
            if ep.auth_type != "none":
                if not ep.credential_ref:
                    errors.append(f"{ep.provider}: credential_ref required")
                    continue
                secret = await self._credentials.resolve_secret(workspace_id, ep.credential_ref)
                if secret is None:
                    errors.append(
                        f"{ep.provider}: credential '{ep.credential_ref}' not found in vault"
                    )
        return errors

    async def chat(
        self,
        policy: LLMPolicy,
        workspace_id: UUID,
        request: ChatCompletionRequest,
    ) -> ChatCompletionResponse:
        endpoints = [policy.inference_primary, *policy.inference_fallbacks]
        last_error: Exception | None = None

        for endpoint in endpoints:
            try:
                token = await self._resolve_token(workspace_id, endpoint)
                adapter = self._get_adapter(endpoint.provider)
                model_request = ChatCompletionRequest(
                    messages=request.messages,
                    model_id=endpoint.model.model_id,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    top_p=request.top_p,
                )
                logger.info(
                    "llm_chat_request",
                    provider=endpoint.provider,
                    model=endpoint.model.model_id,
                    family=endpoint.model.model_family,
                    open_source=endpoint.model.open_source,
                )
                return await adapter.chat_completion(endpoint, model_request, token)
            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_chat_fallback",
                    provider=endpoint.provider,
                    error=str(exc),
                )
                continue

        raise RuntimeError(f"All inference providers failed: {last_error}")

    async def embed(
        self,
        policy: LLMPolicy,
        workspace_id: UUID,
        request: EmbeddingRequest,
    ) -> EmbeddingResponse:
        endpoint = policy.embedding
        token = await self._resolve_token(workspace_id, endpoint)
        adapter = self._get_adapter(endpoint.provider)
        model_request = EmbeddingRequest(
            texts=request.texts,
            model_id=endpoint.model.model_id,
        )
        logger.info(
            "llm_embed_request",
            provider=endpoint.provider,
            model=endpoint.model.model_id,
        )
        return await adapter.embed(endpoint, model_request, token)
