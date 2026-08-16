"""Security headers and production-oriented HTTP hardening."""

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from knowledge_os.config import get_settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        settings = get_settings()
        path = request.url.path

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        response.headers.setdefault("X-Trace-Id", getattr(request.state, "trace_id", "unknown"))

        if settings.is_production:
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=63072000; includeSubDomains",
            )
            if not path.startswith(("/docs", "/redoc", "/openapi.json", "/ui")):
                response.headers.setdefault(
                    "Content-Security-Policy",
                    "default-src 'self'; frame-ancestors 'none'; base-uri 'self'",
                )

        return response
