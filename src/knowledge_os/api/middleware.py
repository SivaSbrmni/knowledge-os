from collections import defaultdict
from time import time

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from knowledge_os.config import get_settings
from knowledge_os.domain.utils import new_trace_id

logger = structlog.get_logger()


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Inject or propagate trace ID on every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting — in-memory for dev/test, Redis-backed in production."""

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        settings = get_settings()
        self._limit = requests_per_minute or settings.rate_limit_requests_per_minute
        self._use_redis = settings.is_production
        self._redis_url = settings.redis_url
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def _redis_count(self, client_ip: str) -> int:
        import redis.asyncio as redis

        key = f"kos:ratelimit:{client_ip}"
        client = redis.from_url(self._redis_url, decode_responses=True)
        try:
            count = await client.incr(key)
            if count == 1:
                await client.expire(key, 60)
            return int(count)
        finally:
            await client.aclose()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if self._use_redis:
            try:
                count = await self._redis_count(client_ip)
                if count > self._limit:
                    return Response(
                        content='{"detail":"Rate limit exceeded"}',
                        status_code=429,
                        media_type="application/json",
                        headers={"Retry-After": "60"},
                    )
            except Exception as exc:
                logger.error("redis_rate_limit_failed", error=str(exc))
                return Response(
                    content='{"detail":"Service temporarily unavailable"}',
                    status_code=503,
                    media_type="application/json",
                )
            return await call_next(request)

        now = time()
        window_start = now - 60
        bucket = [t for t in self._buckets[client_ip] if t > window_start]

        if len(bucket) >= self._limit:
            return Response(
                content='{"detail":"Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={"Retry-After": "60"},
            )

        bucket.append(now)
        self._buckets[client_ip] = bucket
        return await call_next(request)
