"""Known open-source LLM provider defaults. Replaceable without agent config changes."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderDefaults:
    provider: str
    default_base_url: str
    docs_url: str
    supports_openai_api: bool
    typical_auth: str


OPEN_LLM_PROVIDERS: dict[str, ProviderDefaults] = {
    "ollama": ProviderDefaults(
        provider="ollama",
        default_base_url="http://localhost:11434/v1",
        docs_url="https://github.com/ollama/ollama",
        supports_openai_api=True,
        typical_auth="none",
    ),
    "together": ProviderDefaults(
        provider="together",
        default_base_url="https://api.together.xyz/v1",
        docs_url="https://docs.together.ai/",
        supports_openai_api=True,
        typical_auth="api_key",
    ),
    "groq": ProviderDefaults(
        provider="groq",
        default_base_url="https://api.groq.com/openai/v1",
        docs_url="https://console.groq.com/docs",
        supports_openai_api=True,
        typical_auth="api_key",
    ),
    "huggingface": ProviderDefaults(
        provider="huggingface",
        default_base_url="https://api-inference.huggingface.co/v1",
        docs_url="https://huggingface.co/docs/api-inference",
        supports_openai_api=True,
        typical_auth="personal_access_token",
    ),
    "openrouter": ProviderDefaults(
        provider="openrouter",
        default_base_url="https://openrouter.ai/api/v1",
        docs_url="https://openrouter.ai/docs",
        supports_openai_api=True,
        typical_auth="api_key",
    ),
    "replicate": ProviderDefaults(
        provider="replicate",
        default_base_url="https://api.replicate.com/v1",
        docs_url="https://replicate.com/docs",
        supports_openai_api=False,
        typical_auth="api_key",
    ),
    "fireworks": ProviderDefaults(
        provider="fireworks",
        default_base_url="https://api.fireworks.ai/inference/v1",
        docs_url="https://docs.fireworks.ai/",
        supports_openai_api=True,
        typical_auth="api_key",
    ),
    "custom_openai_compatible": ProviderDefaults(
        provider="custom_openai_compatible",
        default_base_url="",
        docs_url="",
        supports_openai_api=True,
        typical_auth="api_key",
    ),
}

RECOMMENDED_LLAMA_MODELS = {
    "together": "meta-llama/Llama-3.3-70B-Instruct-Turbo",
    "groq": "llama-3.3-70b-versatile",
    "ollama": "llama3.3",
    "openrouter": "meta-llama/llama-3.3-70b-instruct",
    "fireworks": "accounts/fireworks/models/llama-v3p3-70b-instruct",
}

RECOMMENDED_EMBEDDING_MODELS = {
    "huggingface": "BAAI/bge-large-en-v1.5",
    "ollama": "nomic-embed-text",
    "together": "togethercomputer/m2-bert-80M-8k-retrieval",
}
