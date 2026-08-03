import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from knowledge_os.config import get_settings


class AgentSchemaValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Agent schema validation failed: {'; '.join(errors)}")


SUPPORTED_SCHEMA_VERSIONS = ("2.0", "2.1")


def _resolve_schema_path(version: str) -> Path:
    settings = get_settings()
    schemas_dir = Path(settings.agent_schema_path).parent
    if not schemas_dir.exists():
        schemas_dir = Path(__file__).resolve().parents[3] / "schemas"
    if not schemas_dir.exists():
        schemas_dir = Path("/app/schemas")

    filename = f"agent-schema-v{version}.json"
    path = schemas_dir / filename
    if not path.exists():
        raise FileNotFoundError(f"Agent schema {version} not found at {path}")
    return path


class AgentSchemaValidator:
    """Validates agent configurations against versioned JSON Schema contracts."""

    def __init__(self, schema_version: str | None = None):
        self._validators: dict[str, Draft7Validator] = {}
        self._schemas: dict[str, dict] = {}
        for version in SUPPORTED_SCHEMA_VERSIONS:
            path = _resolve_schema_path(version)
            with path.open(encoding="utf-8") as f:
                schema = json.load(f)
            self._schemas[version] = schema
            self._validators[version] = Draft7Validator(schema)

    def validate(self, config: dict[str, Any]) -> dict[str, Any]:
        version = config.get("schema_version")
        if version not in SUPPORTED_SCHEMA_VERSIONS:
            raise AgentSchemaValidationError(
                [f"schema_version must be one of: {', '.join(SUPPORTED_SCHEMA_VERSIONS)}"]
            )

        validator = self._validators[version]
        errors = sorted(validator.iter_errors(config), key=lambda e: list(e.path))
        if errors:
            messages = [
                f"{'.'.join(str(p) for p in err.path) or 'root'}: {err.message}" for err in errors
            ]
            raise AgentSchemaValidationError(messages)

        if version == "2.1":
            from knowledge_os.schemas.llm_policy import (
                LLMPolicyError,
                enforce_open_source_policy,
                parse_llm_policy,
            )

            try:
                policy = parse_llm_policy(config)
            except LLMPolicyError as exc:
                raise AgentSchemaValidationError(exc.errors) from exc
            policy_errors = enforce_open_source_policy(policy)
            if policy_errors:
                raise AgentSchemaValidationError(policy_errors)

        return config

    def get_schema(self, version: str = "2.1") -> dict[str, Any]:
        return self._schemas[version]
