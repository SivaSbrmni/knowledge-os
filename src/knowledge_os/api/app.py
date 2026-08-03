from pathlib import Path

import structlog
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from knowledge_os import __version__
from knowledge_os.adapters.persistence.database import get_engine
from knowledge_os.api.knowledge_routes import chat_router, knowledge_router
from knowledge_os.api.middleware import RateLimitMiddleware, TraceContextMiddleware
from knowledge_os.api.routes import router
from knowledge_os.config import get_settings

logger = structlog.get_logger()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Knowledge OS",
        description="Knowledge Operating System — Phase 1: Upload → Ask → Cite",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(TraceContextMiddleware)
    app.include_router(router, prefix="/api/v1")
    app.include_router(knowledge_router, prefix="/api/v1")
    app.include_router(chat_router, prefix="/api/v1")

    web_dir = Path(__file__).resolve().parents[3] / "web"
    if web_dir.exists():
        app.mount("/ui", StaticFiles(directory=str(web_dir), html=True), name="web")

    @app.get("/health", tags=["system"])
    async def health():
        return {
            "status": "healthy",
            "version": __version__,
            "environment": settings.environment,
        }

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
