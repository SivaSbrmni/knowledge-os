import json
from pathlib import Path

import pytest

from knowledge_os.schemas.agent_validator import AgentSchemaValidationError, AgentSchemaValidator
from knowledge_os.schemas.llm_policy import enforce_open_source_policy, parse_llm_policy


@pytest.fixture
def validator() -> AgentSchemaValidator:
    return AgentSchemaValidator()


@pytest.fixture
def valid_agent_v21() -> dict:
    path = Path(__file__).resolve().parents[1] / "examples" / "upsc-mentor-agent.json"
    return json.loads(path.read_text())


def test_valid_agent_v21_passes(validator: AgentSchemaValidator, valid_agent_v21: dict):
    result = validator.validate(valid_agent_v21)
    assert result["schema_version"] == "2.1"
    assert "llm_policy" in result
    policy = parse_llm_policy(result)
    assert policy.require_open_source is True
    assert policy.inference_primary.model.model_family == "llama"


def test_llm_policy_requires_open_source_models(valid_agent_v21: dict):
    config = json.loads(json.dumps(valid_agent_v21))
    config["llm_policy"]["inference"]["primary"]["model"]["open_source"] = False
    with pytest.raises(AgentSchemaValidationError) as exc:
        AgentSchemaValidator().validate(config)
    assert any("open_source" in err for err in exc.value.errors)


def test_credential_ref_required_for_api_key_auth(valid_agent_v21: dict):
    config = json.loads(json.dumps(valid_agent_v21))
    del config["llm_policy"]["inference"]["primary"]["credential_ref"]
    with pytest.raises(AgentSchemaValidationError):
        AgentSchemaValidator().validate(config)


def test_ollama_requires_base_url(valid_agent_v21: dict):
    config = json.loads(json.dumps(valid_agent_v21))
    del config["llm_policy"]["inference"]["fallbacks"][1]["base_url"]
    with pytest.raises(AgentSchemaValidationError):
        AgentSchemaValidator().validate(config)


def test_parse_llm_policy_enforces_open_source_flag(valid_agent_v21: dict):
    policy = parse_llm_policy(valid_agent_v21)
    errors = enforce_open_source_policy(policy)
    assert errors == []


def test_v20_still_supported(validator: AgentSchemaValidator):
    v20_config = {
        "schema_version": "2.0",
        "agent_id": "legacy-agent",
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "workspace_id": "00000000-0000-0000-0000-000000000002",
        "identity": {"name": "Legacy", "domain": "test", "persona": "test"},
        "knowledge_policy": {
            "allowed_layers": ["tenant"],
            "excluded_providers": [],
            "freshness_requirement": "moderate",
            "authority_preference": "default",
            "max_evidence_age_days": 365,
        },
        "reasoning_policy": {
            "grounding_required": True,
            "min_evidence_packets": 1,
            "allow_foundation_model_recall": False,
            "conflict_behavior": "withhold",
        },
        "trust_policy": {
            "min_source_trust": 0.5,
            "min_groundedness": 0.5,
            "withhold_below_threshold": True,
            "show_trust_vector": False,
        },
        "memory_policy": {
            "session_memory": "enabled",
            "long_term_memory": "disabled",
            "cross_session_retention_days": 30,
        },
        "tool_policy": {"allowed_tools": [], "web_search": "disabled"},
        "model_policy": {
            "preferred_model": "gpt-4o",
            "fallback_models": ["claude-3-5-sonnet"],
            "embedding_model": "text-embedding-3-large",
        },
    }
    result = validator.validate(v20_config)
    assert result["schema_version"] == "2.0"
