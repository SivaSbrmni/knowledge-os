"""Startup validation for production deployments."""

from knowledge_os.config import Settings

_INSECURE_JWT_SECRETS = frozenset({
    "dev-secret-change-in-production",
    "change-me",
    "secret",
})


def validate_production_settings(settings: Settings) -> list[str]:
    """Return blocking configuration errors for regulated production use."""
    if not settings.is_production:
        return []

    errors: list[str] = []

    if settings.jwt_secret in _INSECURE_JWT_SECRETS or len(settings.jwt_secret) < 32:
        errors.append("JWT_SECRET must be set to a strong random value (min 32 chars) in production")

    if settings.use_dev_embeddings:
        errors.append("USE_DEV_EMBEDDINGS must be false in production")

    if not settings.redis_url or settings.redis_url.startswith("redis://localhost"):
        errors.append("REDIS_URL must point to a managed Redis instance in production")

    if not settings.database_url or "localhost" in settings.database_url:
        errors.append("DATABASE_URL must not use localhost in production")

    return errors
