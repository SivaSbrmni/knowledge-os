from pathlib import Path

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from knowledge_os import __version__
from knowledge_os.adapters.persistence.database import get_engine
from knowledge_os.api.compliance_routes import compliance_router
from knowledge_os.api.knowledge_routes import chat_router, knowledge_router
from knowledge_os.api.middleware import RateLimitMiddleware, TraceContextMiddleware
from knowledge_os.api.security_middleware import SecurityHeadersMiddleware
from knowledge_os.api.routes import router
from knowledge_os.config import get_settings
from knowledge_os.services.production_validation import validate_production_settings

logger = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    config_errors = validate_production_settings(settings)
    if config_errors:
        for err in config_errors:
            logger.error("production_config_invalid", detail=err)
        if settings.is_production:
            raise RuntimeError(
                "Invalid production configuration: " + "; ".join(config_errors)
            )

    app = FastAPI(
        title="Knowledge OS",
        description="Knowledge Operating System — Phase 1: Upload → Ask → Cite",
        version=__version__,
        docs_url="/docs" if not settings.is_production else None,
        redoc_url="/redoc" if not settings.is_production else None,
        openapi_url="/openapi.json" if not settings.is_production else None,
    )

    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TraceContextMiddleware)
    app.include_router(router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")
    app.include_router(compliance_router, prefix="/api/v1")

    @app.exception_handler(PermissionError)
    async def permission_error_handler(_request: Request, exc: PermissionError):
        return JSONResponse(
            status_code=401,
            content={"detail": str(exc) or "Authentication required"},
        )

    web_dir = Path(__file__).resolve().parents[3] / "web"
    if web_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="web")

        from fastapi.responses import RedirectResponse

        @app.get("/", include_in_schema=False)
        async def root_redirect():
            return RedirectResponse(url="/ui/")

    @app.get("/health", tags=["system"])
    async def health():
        payload = {
            "status": "healthy",
            "version": __version__,
            "environment": settings.environment,
        }
        if settings.is_production:
            payload["production_validated"] = True
        return payload

    @app.get("/ready", tags=["system"])
    async def ready():
        db_status = "unknown"
        redis_status = "unknown"

        try:
            engine = get_engine()
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            db_status = "connected"
        except Exception as exc:
            logger.warning("database_readiness_failed", error=str(exc))
            db_status = "disconnected"

        try:
            import redis.asyncio as redis

            client = redis.from_url(settings.redis_url, decode_responses=True)
            await client.ping()
            await client.aclose()
            redis_status = "connected"
        except Exception as exc:
            logger.warning("redis_readiness_failed", error=str(exc))
            redis_status = "disconnected"

        overall = "ready" if db_status == "connected" else "not_ready"
        status_code = 200 if overall == "ready" else 503

        from fastapi.responses import JSONResponse

        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall,
                "database": db_status,
                "redis": redis_status,
            },
        )

    return app


app = create_app()
