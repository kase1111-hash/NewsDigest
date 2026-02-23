"""API middleware for NewsDigest.

Provides authentication, rate limiting, and request tracking.
"""

import hashlib
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from newsdigest.api.models import ErrorResponse


# =============================================================================
# API Key Authentication
# =============================================================================


@dataclass
class APIKey:
    """API key with metadata."""

    key: str
    name: str
    created_at: float = field(default_factory=time.time)
    rate_limit: int = 100  # requests per minute
    enabled: bool = True
    scopes: list[str] = field(default_factory=lambda: ["read", "write"])


class APIKeyManager:
    """Manages API keys for authentication.

    Supports in-memory storage with optional persistence callback.

    Example:
        >>> manager = APIKeyManager()
        >>> key = manager.create_key("my-app")
        >>> print(key.key)  # Use this key in X-API-Key header
        >>> manager.validate_key("abc123...")
    """

    def __init__(self) -> None:
        """Initialize API key manager."""
        self._keys: dict[str, APIKey] = {}
        self._key_hashes: dict[str, str] = {}  # hash -> key_id

    def create_key(
        self,
        name: str,
        rate_limit: int = 100,
        scopes: list[str] | None = None,
    ) -> APIKey:
        """Create a new API key.

        Args:
            name: Human-readable name for the key.
            rate_limit: Requests per minute allowed.
            scopes: Permission scopes.

        Returns:
            New API key object.
        """
        import secrets  # noqa: PLC0415

        # Generate a secure random key
        raw_key = secrets.token_urlsafe(32)
        key_hash = self._hash_key(raw_key)

        api_key = APIKey(
            key=raw_key,
            name=name,
            rate_limit=rate_limit,
            scopes=scopes or ["read", "write"],
        )

        self._keys[key_hash] = api_key
        self._key_hashes[key_hash] = key_hash

        return api_key

    def validate_key(self, key: str) -> APIKey | None:
        """Validate an API key.

        Args:
            key: The API key to validate.

        Returns:
            APIKey object if valid, None otherwise.
        """
        key_hash = self._hash_key(key)
        api_key = self._keys.get(key_hash)

        if api_key and api_key.enabled:
            return api_key

        return None

    def revoke_key(self, key: str) -> bool:
        """Revoke an API key.

        Args:
            key: The API key to revoke.

        Returns:
            True if revoked, False if not found.
        """
        key_hash = self._hash_key(key)
        if key_hash in self._keys:
            self._keys[key_hash].enabled = False
            return True
        return False

    def delete_key(self, key: str) -> bool:
        """Delete an API key.

        Args:
            key: The API key to delete.

        Returns:
            True if deleted, False if not found.
        """
        key_hash = self._hash_key(key)
        if key_hash in self._keys:
            del self._keys[key_hash]
            del self._key_hashes[key_hash]
            return True
        return False

    def list_keys(self) -> list[dict[str, str | int | bool]]:
        """List all API keys (without the actual key values).

        Returns:
            List of key metadata.
        """
        return [
            {
                "name": k.name,
                "created_at": k.created_at,
                "rate_limit": k.rate_limit,
                "enabled": k.enabled,
                "scopes": k.scopes,
            }
            for k in self._keys.values()
        ]

    def _hash_key(self, key: str) -> str:
        """Hash an API key for storage.

        Args:
            key: The raw API key.

        Returns:
            SHA-256 hash of the key.
        """
        return hashlib.sha256(key.encode()).hexdigest()


# Global key manager instance
api_key_manager = APIKeyManager()


class AuthMiddleware(BaseHTTPMiddleware):
    """Authentication middleware using API keys.

    Validates X-API-Key header for protected endpoints.
    """

    def __init__(
        self,
        app: Callable,
        key_manager: APIKeyManager | None = None,
        exclude_paths: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize auth middleware.

        Args:
            app: The FastAPI application.
            key_manager: API key manager instance.
            exclude_paths: Paths to exclude from auth.
            enabled: Whether auth is enabled.
        """
        super().__init__(app)
        self.key_manager = key_manager or api_key_manager
        self.exclude_paths = exclude_paths or [
            "/api/v1/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """Process request through auth middleware."""
        if not self.enabled:
            return await call_next(request)

        # Skip excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Get API key from header
        api_key = request.headers.get("X-API-Key")

        if not api_key:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="authentication_error",
                    message="Missing API key. Include X-API-Key header.",
                ).model_dump(),
            )

        # Validate key
        key_obj = self.key_manager.validate_key(api_key)
        if not key_obj:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content=ErrorResponse(
                    error="authentication_error",
                    message="Invalid or revoked API key.",
                ).model_dump(),
            )

        # Store key info in request state for use by rate limiter
        request.state.api_key = key_obj

        return await call_next(request)


# =============================================================================
# Rate Limiting
# =============================================================================


@dataclass
class RateLimitBucket:
    """Token bucket for rate limiting."""

    tokens: float
    last_update: float
    max_tokens: int
    refill_rate: float  # tokens per second


class RateLimiter:
    """Token bucket rate limiter.

    Implements a token bucket algorithm for rate limiting.
    Each API key gets its own bucket.

    TODO: This assumes single-process deployment. For multi-worker
    setups (gunicorn, etc.), use a Redis-backed limiter instead.

    Example:
        >>> limiter = RateLimiter(requests_per_minute=100)
        >>> if limiter.is_allowed("user-123"):
        ...     # Process request
        >>> else:
        ...     # Return 429 Too Many Requests
    """

    def __init__(
        self,
        requests_per_minute: int = 100,
        burst_size: int | None = None,
    ) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_minute: Base rate limit.
            burst_size: Max burst size (defaults to 2x rate limit).
        """
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size or (requests_per_minute * 2)
        self._buckets: dict[str, RateLimitBucket] = {}

    def is_allowed(
        self,
        key: str,
        cost: int = 1,
        custom_limit: int | None = None,
    ) -> tuple[bool, dict[str, int]]:
        """Check if request is allowed.

        Args:
            key: Identifier (API key, IP, etc.).
            cost: Token cost for this request.
            custom_limit: Override rate limit for this key.

        Returns:
            Tuple of (allowed, headers) where headers contains
            rate limit info for response headers.
        """
        now = time.time()
        limit = custom_limit or self.requests_per_minute
        refill_rate = limit / 60.0  # tokens per second

        # Get or create bucket
        if key not in self._buckets:
            self._buckets[key] = RateLimitBucket(
                tokens=float(self.burst_size),
                last_update=now,
                max_tokens=self.burst_size,
                refill_rate=refill_rate,
            )

        bucket = self._buckets[key]

        # Refill tokens
        elapsed = now - bucket.last_update
        bucket.tokens = min(
            bucket.max_tokens,
            bucket.tokens + (elapsed * bucket.refill_rate),
        )
        bucket.last_update = now

        # Check if allowed
        allowed = bucket.tokens >= cost
        if allowed:
            bucket.tokens -= cost

        # Build headers
        tokens_needed = bucket.max_tokens - bucket.tokens
        reset_time = int(now + tokens_needed / bucket.refill_rate)
        headers = {
            "X-RateLimit-Limit": limit,
            "X-RateLimit-Remaining": max(0, int(bucket.tokens)),
            "X-RateLimit-Reset": reset_time,
        }

        return allowed, headers

    def get_wait_time(self, key: str, cost: int = 1) -> float:
        """Get time to wait before request is allowed.

        Args:
            key: Identifier.
            cost: Token cost.

        Returns:
            Seconds to wait (0 if allowed now).
        """
        if key not in self._buckets:
            return 0.0

        bucket = self._buckets[key]
        if bucket.tokens >= cost:
            return 0.0

        needed = cost - bucket.tokens
        return needed / bucket.refill_rate

    def reset(self, key: str) -> None:
        """Reset rate limit for a key.

        Args:
            key: Identifier to reset.
        """
        if key in self._buckets:
            del self._buckets[key]

    def clear(self) -> None:
        """Clear all rate limit buckets."""
        self._buckets.clear()


# Global rate limiter instance
rate_limiter = RateLimiter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware.

    Applies rate limits based on API key or IP address.
    """

    def __init__(
        self,
        app: Callable,
        limiter: RateLimiter | None = None,
        exclude_paths: list[str] | None = None,
        enabled: bool = True,
    ) -> None:
        """Initialize rate limit middleware.

        Args:
            app: The FastAPI application.
            limiter: Rate limiter instance.
            exclude_paths: Paths to exclude from rate limiting.
            enabled: Whether rate limiting is enabled.
        """
        super().__init__(app)
        self.limiter = limiter or rate_limiter
        self.exclude_paths = exclude_paths or [
            "/api/v1/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        self.enabled = enabled

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """Process request through rate limit middleware."""
        if not self.enabled:
            return await call_next(request)

        # Skip excluded paths
        if any(request.url.path.startswith(p) for p in self.exclude_paths):
            return await call_next(request)

        # Get identifier (API key or IP)
        api_key = getattr(request.state, "api_key", None)
        if api_key:
            identifier = f"key:{api_key.name}"
            custom_limit = api_key.rate_limit
        else:
            # Fall back to IP
            identifier = f"ip:{request.client.host if request.client else 'unknown'}"
            custom_limit = None

        # Check rate limit
        allowed, headers = self.limiter.is_allowed(
            identifier,
            custom_limit=custom_limit,
        )

        if not allowed:
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content=ErrorResponse(
                    error="rate_limit_exceeded",
                    message="Too many requests. Please slow down.",
                    details={
                        "retry_after": self.limiter.get_wait_time(identifier),
                    },
                ).model_dump(),
            )
            # Add rate limit headers
            for key, value in headers.items():
                response.headers[key] = str(value)
            return response

        # Process request
        response = await call_next(request)

        # Add rate limit headers to successful responses
        for key, value in headers.items():
            response.headers[key] = str(value)

        return response


# =============================================================================
# Request Tracking
# =============================================================================


class RequestTracker:
    """Tracks API request metrics.

    Collects statistics about API usage for monitoring.
    """

    def __init__(self) -> None:
        """Initialize request tracker."""
        self._requests: dict[str, int] = defaultdict(int)
        self._errors: dict[str, int] = defaultdict(int)
        self._latencies: dict[str, list[float]] = defaultdict(list)
        self._start_time = time.time()

    def record_request(
        self,
        path: str,
        method: str,
        status_code: int,
        latency_ms: float,
    ) -> None:
        """Record a request.

        Args:
            path: Request path.
            method: HTTP method.
            status_code: Response status code.
            latency_ms: Request latency in milliseconds.
        """
        key = f"{method}:{path}"
        self._requests[key] += 1

        if status_code >= 400:
            self._errors[key] += 1

        # Keep last 1000 latencies per endpoint
        latencies = self._latencies[key]
        latencies.append(latency_ms)
        if len(latencies) > 1000:
            self._latencies[key] = latencies[-1000:]

    def get_stats(self) -> dict[str, float | int | dict]:
        """Get aggregated statistics.

        Returns:
            Dictionary with request statistics.
        """
        total_requests = sum(self._requests.values())
        total_errors = sum(self._errors.values())

        all_latencies = []
        for latencies in self._latencies.values():
            all_latencies.extend(latencies)

        avg_latency = (
            sum(all_latencies) / len(all_latencies) if all_latencies else 0.0
        )

        uptime = time.time() - self._start_time

        return {
            "uptime_seconds": uptime,
            "total_requests": total_requests,
            "total_errors": total_errors,
            "error_rate": total_errors / total_requests if total_requests > 0 else 0.0,
            "avg_latency_ms": avg_latency,
            "requests_per_endpoint": dict(self._requests),
            "errors_per_endpoint": dict(self._errors),
        }

    def reset(self) -> None:
        """Reset all statistics."""
        self._requests.clear()
        self._errors.clear()
        self._latencies.clear()
        self._start_time = time.time()


# Global request tracker
request_tracker = RequestTracker()


class RequestTrackingMiddleware(BaseHTTPMiddleware):
    """Middleware for tracking request metrics."""

    def __init__(
        self,
        app: Callable,
        tracker: RequestTracker | None = None,
    ) -> None:
        """Initialize tracking middleware.

        Args:
            app: The FastAPI application.
            tracker: Request tracker instance.
        """
        super().__init__(app)
        self.tracker = tracker or request_tracker

    async def dispatch(self, request: Request, call_next: Callable) -> JSONResponse:
        """Process request and record metrics."""
        start_time = time.perf_counter()

        response = await call_next(request)

        latency_ms = (time.perf_counter() - start_time) * 1000

        self.tracker.record_request(
            path=request.url.path,
            method=request.method,
            status_code=response.status_code,
            latency_ms=latency_ms,
        )

        return response
