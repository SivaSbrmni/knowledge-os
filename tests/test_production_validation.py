"""Production configuration validation tests."""

import pytest

from knowledge_os.config import Settings
from knowledge_os.services.production_validation import validate_production_settings


def test_production_rejects_default_jwt_secret():
    settings = Settings(
        environment="production",
        jwt_secret="dev-secret-change-in-production",
        use_dev_embeddings=False,
    )
    errors = validate_production_settings(settings)
    assert any("JWT_SECRET" in e for e in errors)


def test_production_rejects_dev_embeddings():
    settings = Settings(
        environment="production",
        jwt_secret="a-very-long-and-secure-production-secret-key-32chars",
        use_dev_embeddings=True,
    )
    errors = validate_production_settings(settings)
    assert any("USE_DEV_EMBEDDINGS" in e for e in errors)


def test_production_accepts_valid_config():
    settings = Settings(
        environment="production",
        jwt_secret="a-very-long-and-secure-production-secret-key-32chars",
        use_dev_embeddings=False,
        database_url="postgresql+asyncpg://user:pass@db.example.com:5432/knowledge_os",
        redis_url="redis://redis.example.com:6379/0",
    )
    assert validate_production_settings(settings) == []


def test_development_skips_validation():
    settings = Settings(environment="development")
    assert validate_production_settings(settings) == []


@pytest.mark.asyncio
async def test_app_boots_in_testing_environment():
    from knowledge_os.api.app import create_app

    app = create_app()
    assert app is not None
