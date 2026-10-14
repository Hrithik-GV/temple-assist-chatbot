"""Security middleware and secure headers enforcement for production deployments."""

from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects essential security headers into every HTTP response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response: Response = await call_next(request)

        if not getattr(settings, "SECURE_HEADERS_ENABLED", True):
            return response

        # Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Prevent clickjacking for API endpoints
        response.headers["X-Frame-Options"] = "DENY"

        # Enable browser XSS filtering
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Control referrer information sent in requests
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Restrict browser features/permissions
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"

        # Enforce HTTPS in production environments via HSTS
        if settings.is_production or request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains; preload"

        return response
