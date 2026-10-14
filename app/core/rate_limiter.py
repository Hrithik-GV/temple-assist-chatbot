"""Rate limiting foundation and FastAPI dependencies for public chatbot endpoints."""

from abc import ABC, abstractmethod
import time
from typing import Dict, List, Optional, Tuple
from fastapi import HTTPException, Request, Response, status

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class BaseRateLimiter(ABC):
    """Abstract interface for rate limiters (memory, Redis, Memcached, etc.)."""

    @abstractmethod
    async def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> Tuple[bool, int, int]:
        """Check if request is allowed under rate limits.

        Args:
            key: Unique client identifier (IP address, token, or templeId).
            max_requests: Maximum allowed requests within the window.
            window_seconds: Time window duration in seconds.

        Returns:
            Tuple[bool, int, int]: (is_allowed, remaining_requests, retry_after_seconds)
        """
        pass


class InMemorySlidingWindowRateLimiter(BaseRateLimiter):
    """In-memory sliding window rate limiter tracking request timestamps."""

    def __init__(self) -> None:
        self._history: Dict[str, List[float]] = {}

    async def is_allowed(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> Tuple[bool, int, int]:
        now = time.time()
        window_start = now - window_seconds

        # Clean old timestamps
        timestamps = self._history.get(key, [])
        valid_timestamps = [ts for ts in timestamps if ts > window_start]

        if len(valid_timestamps) >= max_requests:
            oldest_in_window = valid_timestamps[0]
            retry_after = max(1, int(oldest_in_window + window_seconds - now))
            self._history[key] = valid_timestamps
            return False, 0, retry_after

        # Record this request
        valid_timestamps.append(now)
        self._history[key] = valid_timestamps
        remaining = max_requests - len(valid_timestamps)
        return True, remaining, 0

    def clear(self) -> None:
        """Clear all stored rate limit history (useful for testing)."""
        self._history.clear()


# Default in-memory rate limiter instance
default_rate_limiter = InMemorySlidingWindowRateLimiter()


class RateLimiter:
    """FastAPI dependency for applying rate limits to endpoints.

    Designed for multi-origin public chat widgets.
    """

    def __init__(
        self,
        requests_per_minute: Optional[int] = None,
        limiter: Optional[BaseRateLimiter] = None,
        key_func: Optional[callable] = None,
    ) -> None:
        self.requests_per_minute = requests_per_minute or getattr(
            settings, "RATE_LIMIT_REQUESTS_PER_MINUTE", 60
        )
        self.limiter = limiter or default_rate_limiter
        self.key_func = key_func or self._get_client_ip

    async def __call__(self, request: Request, response: Response) -> None:
        """Evaluate rate limit and attach standard headers to response."""
        # Allow disabling rate limiting via config (e.g. testing)
        if not getattr(settings, "RATE_LIMIT_ENABLED", True):
            return

        client_key = self.key_func(request)
        is_allowed, remaining, retry_after = await self.limiter.is_allowed(
            key=client_key,
            max_requests=self.requests_per_minute,
            window_seconds=60,
        )

        # Set standard rate-limit headers
        response.headers["X-RateLimit-Limit"] = str(self.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(max(0, remaining))

        if not is_allowed:
            logger.warning("Rate limit exceeded for client '%s' on %s", client_key, request.url.path)
            response.headers["Retry-After"] = str(retry_after)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests. Please slow down and try again shortly.",
                headers={"Retry-After": str(retry_after)},
            )

    @staticmethod
    def _get_client_ip(request: Request) -> str:
        """Extract client IP, honoring X-Forwarded-For if running behind a proxy/load balancer."""
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # First IP in comma-separated list is the client IP
            return forwarded.split(",")[0].strip()
        if request.client and request.client.host:
            return request.client.host
        return "127.0.0.1"
