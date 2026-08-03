import json
from pathlib import Path
from typing import Any

from jsonschema import Draft7Validator

from knowledge_os.config import get_settings, resolve_schema_path


class AgentSchemaValidationError(Exception):
    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__(f"Agent schema validation failed: {'; '.join(errors)}")


class AgentSchemaValidator:
    """Validates agent configurations against the versioned JSON Schema contract."""

    def __init__(self, schema_path: Path | None = None):
        settings = get_settings()
        path = schema_path or resolve_schema_path(settings)
        with path.open(encoding="utf-8") as f:
            self._schema = json.load(f)
        self._validator = Draft7Validator(self._schema)

    def validate(self, config: dict[str, Any]) -> dict[str, Any]:
        errors = sorted(self._validator.iter_errors(config), key=lambda e: list(e.path))
        if errors:
            messages = [
                f"{'.'.join(str(p) for p in err.path) or 'root'}: {err.message}" for err in errors
            ]
            raise AgentSchemaValidationError(messages)

        if config.get("schema_version") != "2.0":
            raise AgentSchemaValidationError(["schema_version must be '2.0'"])

        return config

    @property
    def schema_version(self) -> str:
        return self._schema.get("properties", {}).get("schema_version", {}).get("const", "2.0")
