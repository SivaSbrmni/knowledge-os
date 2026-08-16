"""Parse and validate llm_policy from agent configuration."""

from typing import Any

from knowledge_os.domain.llm import LLMPolicy, ModelSpec, ProviderEndpoint


class LLMPolicyError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"LLM policy error: {'; '.join(errors)}")


def _parse_model_spec(data: dict[str, Any]) -> ModelSpec:
    return ModelSpec(
        model_id=data["model_id"],
        model_family=data["model_family"],
        open_source=data["open_source"],
        license=data.get("license"),
        context_window=data.get("context_window"),
    )


def _parse_endpoint(data: dict[str, Any]) -> ProviderEndpoint:
    auth_type = data["auth_type"]
    credential_ref = data.get("credential_ref")
    if auth_type != "none" and not credential_ref:
        raise LLMPolicyError(
            [f"credential_ref required when auth_type is {auth_type}"]
        )
    if data["provider"] in ("ollama", "custom_openai_compatible") and not data.get("base_url"):
        raise LLMPolicyError(
            [f"base_url required for provider {data['provider']}"]
        )
    return ProviderEndpoint(
        provider=data["provider"],
        auth_type=auth_type,
        model=_parse_model_spec(data["model"]),
        credential_ref=credential_ref,
        base_url=data.get("base_url"),
        parameters=data.get("parameters") or {},
    )


def parse_llm_policy(config: dict[str, Any]) -> LLMPolicy:
    raw = config.get("llm_policy")
    if raw is None:
        raise LLMPolicyError(["llm_policy is required in agent schema v2.1+"])

    inference = raw["inference"]
    return LLMPolicy(
        require_open_source=raw["require_open_source"],
        inference_primary=_parse_endpoint(inference["primary"]),
        inference_fallbacks=[_parse_endpoint(f) for f in inference.get("fallbacks", [])],
        embedding=_parse_endpoint(raw["embedding"]),
    )


def enforce_open_source_policy(policy: LLMPolicy) -> list[str]:
    errors: list[str] = []
    if not policy.require_open_source:
        return errors

    all_endpoints = [policy.inference_primary, *policy.inference_fallbacks, policy.embedding]
    for ep in all_endpoints:
        if not ep.model.open_source:
            errors.append(
                f"Model {ep.model.model_id} is not open_source but require_open_source=true"
            )
    return errors
