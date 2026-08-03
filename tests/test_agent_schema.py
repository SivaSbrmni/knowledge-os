import json
from pathlib import Path

import pytest

from knowledge_os.schemas.agent_validator import AgentSchemaValidationError, AgentSchemaValidator


@pytest.fixture
def validator() -> AgentSchemaValidator:
    return AgentSchemaValidator()


@pytest.fixture
def valid_agent_config() -> dict:
    path = Path(__file__).resolve().parents[1] / "examples" / "upsc-mentor-agent.json"
    return json.loads(path.read_text())


def test_valid_agent_config_passes(validator: AgentSchemaValidator, valid_agent_config: dict):
    result = validator.validate(valid_agent_config)
    assert result["schema_version"] == "2.1"
    assert result["agent_id"] == "upsc-mentor-v1"
    assert "llm_policy" in result


def test_missing_required_field_fails(validator: AgentSchemaValidator, valid_agent_config: dict):
    config = {**valid_agent_config}
    del config["trust_policy"]
    with pytest.raises(AgentSchemaValidationError) as exc:
        validator.validate(config)
    assert any("trust_policy" in err for err in exc.value.errors)


def test_invalid_schema_version_fails(validator: AgentSchemaValidator, valid_agent_config: dict):
    config = {**valid_agent_config, "schema_version": "1.0"}
    with pytest.raises(AgentSchemaValidationError):
        validator.validate(config)


def test_missing_llm_policy_fails_v21(validator: AgentSchemaValidator, valid_agent_config: dict):
    config = {k: v for k, v in valid_agent_config.items() if k != "llm_policy"}
    config["model_policy"] = {
        "preferred_model": "gpt-4o",
        "fallback_models": ["claude"],
        "embedding_model": "text-embedding-3-large",
    }
    with pytest.raises(AgentSchemaValidationError):
        validator.validate(config)


def test_invalid_agent_id_pattern_fails(validator: AgentSchemaValidator, valid_agent_config: dict):
    config = {**valid_agent_config, "agent_id": "Invalid Agent ID"}
    with pytest.raises(AgentSchemaValidationError):
        validator.validate(config)
