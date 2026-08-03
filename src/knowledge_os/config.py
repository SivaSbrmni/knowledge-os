from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+asyncpg://knowledge_os:knowledge_os_dev@localhost:5432/knowledge_os"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60
    environment: str = "development"
    log_level: str = "INFO"
    rate_limit_requests_per_minute: int = 120
    agent_schema_path: str = "schemas/agent-schema-v2.1.json"

    @property
    def is_development(self) -> bool:
        return self.environment == "development"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_schema_path(settings: Settings) -> Path:
    candidates = [
        Path(settings.agent_schema_path),
        Path(__file__).resolve().parents[3] / "schemas" / "agent-schema-v2.0.json",
        Path("/app/schemas/agent-schema-v2.0.json"),
    ]
    for path in candidates:
        if path.exists():
            return path
    raise FileNotFoundError("Agent schema v2.0 not found")
