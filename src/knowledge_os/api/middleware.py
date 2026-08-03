from collections import defaultdict
from time import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from knowledge_os.config import get_settings
from knowledge_os.domain.utils import new_trace_id


class TraceContextMiddleware(BaseHTTPMiddleware):
    """Inject or propagate trace ID on every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get("X-Trace-Id") or new_trace_id()
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Trace-Id"] = trace_id
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limit stub (per client IP)."""

    def __init__(self, app, requests_per_minute: int | None = None):
        super().__init__(app)
        settings = get_settings()
        self._limit = requests_per_minute or settings.rate_limit_requests_per_minute
        self._buckets: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.url.path in {"/health", "/ready", "/docs", "/openapi.json", "/redoc"}:
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
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
