import httpx

from knowledge_os.domain.llm import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ProviderEndpoint,
)
from knowledge_os.domain.llm_registry import OPEN_LLM_PROVIDERS
from knowledge_os.ports.llm import LLMProviderAdapter


class OpenAICompatibleAdapter(LLMProviderAdapter):
    """
    Universal adapter for open-LLM providers exposing an OpenAI-compatible API.
    Works with: Ollama, Together, Groq, HuggingFace Inference, OpenRouter, Fireworks.
    """

    def __init__(self, provider_name: str):
        self._provider_name = provider_name

    @property
    def provider_name(self) -> str:
        return self._provider_name

    def _resolve_base_url(self, endpoint: ProviderEndpoint) -> str:
        if endpoint.base_url:
            return endpoint.base_url.rstrip("/")
        defaults = OPEN_LLM_PROVIDERS.get(endpoint.provider)
        if defaults and defaults.default_base_url:
            return defaults.default_base_url.rstrip("/")
        raise ValueError(f"No base_url for provider {endpoint.provider}")

    def _auth_headers(self, endpoint: ProviderEndpoint, api_token: str | None) -> dict[str, str]:
        if endpoint.auth_type == "none":
            return {}
        if not api_token:
            raise ValueError(f"API token required for {endpoint.provider}")
        return {"Authorization": f"Bearer {api_token}"}

    async def chat_completion(
        self,
        endpoint: ProviderEndpoint,
        request: ChatCompletionRequest,
        api_token: str | None,
    ) -> ChatCompletionResponse:
        base_url = self._resolve_base_url(endpoint)
        params = endpoint.parameters
        payload = {
            "model": request.model_id or endpoint.model.model_id,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": params.get("temperature", request.temperature),
            "max_tokens": params.get("max_tokens", request.max_tokens),
        }
        if params.get("top_p") is not None:
            payload["top_p"] = params["top_p"]

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{base_url}/chat/completions",
                json=payload,
                headers=self._auth_headers(endpoint, api_token),
            )
            response.raise_for_status()
            data = response.json()

        choice = data["choices"][0]
        usage = data.get("usage", {})
        return ChatCompletionResponse(
            content=choice["message"]["content"],
            model_id=data.get("model", endpoint.model.model_id),
            provider=endpoint.provider,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=choice.get("finish_reason"),
        )

    async def embed(
        self,
        endpoint: ProviderEndpoint,
        request: EmbeddingRequest,
        api_token: str | None,
    ) -> EmbeddingResponse:
        base_url = self._resolve_base_url(endpoint)
        model_id = request.model_id or endpoint.model.model_id

        async with httpx.AsyncClient(timeout=60.0) as client:
            embeddings: list[list[float]] = []
            for text in request.texts:
                response = await client.post(
                    f"{base_url}/embeddings",
                    json={"model": model_id, "input": text},
                    headers=self._auth_headers(endpoint, api_token),
                )
                response.raise_for_status()
                data = response.json()
                embeddings.append(data["data"][0]["embedding"])

        return EmbeddingResponse(
            embeddings=embeddings,
            model_id=model_id,
            provider=endpoint.provider,
        )

    async def health_check(
        self, endpoint: ProviderEndpoint, api_token: str | None
    ) -> bool:
        try:
            base_url = self._resolve_base_url(endpoint)
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{base_url}/models",
                    headers=self._auth_headers(endpoint, api_token),
                )
                return response.status_code < 400
        except Exception:
            return False


def create_provider_adapter(provider: str) -> LLMProviderAdapter:
    if provider not in OPEN_LLM_PROVIDERS:
        raise ValueError(f"Unknown provider: {provider}")
    return OpenAICompatibleAdapter(provider)
