"""HTTP client utilities for NewsDigest.

This module provides a shared async HTTP client with:
- Connection pooling
- Rate limiting
- Retry logic with exponential backoff
- Timeout handling
"""

import asyncio
import time
from typing import Any

import httpx


class RateLimiter:
    """Simple rate limiter for HTTP requests."""

    def __init__(self, requests_per_second: float = 2.0) -> None:
        """Initialize rate limiter.

        Args:
            requests_per_second: Maximum requests per second.
        """
        self.requests_per_second = requests_per_second
        self.min_interval = 1.0 / requests_per_second
        self._last_request_time: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait if necessary to respect rate limit."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request_time
            wait_time = self.min_interval - elapsed

            if wait_time > 0:
                await asyncio.sleep(wait_time)

            self._last_request_time = time.monotonic()


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        retry_status_codes: set[int] | None = None,
    ) -> None:
        """Initialize retry configuration.

        Args:
            max_retries: Maximum number of retry attempts.
            base_delay: Initial delay between retries (seconds).
            max_delay: Maximum delay between retries (seconds).
            exponential_base: Base for exponential backoff.
            retry_status_codes: HTTP status codes to retry on.
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retry_status_codes = retry_status_codes or {429, 500, 502, 503, 504}

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt number.

        Args:
            attempt: Current attempt number (0-indexed).

        Returns:
            Delay in seconds.
        """
        delay = self.base_delay * (self.exponential_base**attempt)
        return min(delay, self.max_delay)

    def should_retry(self, status_code: int) -> bool:
        """Check if status code should trigger retry.

        Args:
            status_code: HTTP status code.

        Returns:
            True if should retry.
        """
        return status_code in self.retry_status_codes


class HTTPClient:
    """Async HTTP client with rate limiting and retry support."""

    # Default user agent
    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (compatible; NewsDigest/1.0; "
        "+https://github.com/newsdigest/newsdigest)"
    )

    def __init__(
        self,
        timeout: float = 30.0,
        rate_limit: float = 2.0,
        retry_config: RetryConfig | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Initialize HTTP client.

        Args:
            timeout: Request timeout in seconds.
            rate_limit: Requests per second limit.
            retry_config: Retry configuration.
            headers: Default headers for requests.
        """
        self.timeout = timeout
        self.rate_limiter = RateLimiter(rate_limit)
        self.retry_config = retry_config or RetryConfig()

        self._headers = {
            "User-Agent": self.DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }
        if headers:
            self._headers.update(headers)

        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                follow_redirects=True,
                headers=self._headers,
            )
        return self._client

    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make GET request with rate limiting and retry.

        Args:
            url: URL to fetch.
            headers: Additional headers.
            **kwargs: Additional httpx parameters.

        Returns:
            HTTP response.

        Raises:
            httpx.HTTPError: If request fails after retries.
        """
        return await self._request("GET", url, headers=headers, **kwargs)

    async def post(
        self,
        url: str,
        data: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make POST request with rate limiting and retry.

        Args:
            url: URL to post to.
            data: Form data.
            json: JSON data.
            headers: Additional headers.
            **kwargs: Additional httpx parameters.

        Returns:
            HTTP response.

        Raises:
            httpx.HTTPError: If request fails after retries.
        """
        return await self._request(
            "POST", url, data=data, json=json, headers=headers, **kwargs
        )

    async def _request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make HTTP request with rate limiting and retry.

        Args:
            method: HTTP method.
            url: URL.
            headers: Additional headers.
            **kwargs: Additional httpx parameters.

        Returns:
            HTTP response.

        Raises:
            httpx.HTTPError: If request fails after retries.
        """
        client = await self._get_client()
        last_error: Exception | None = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Rate limit
                await self.rate_limiter.acquire()

                # Make request
                response = await client.request(method, url, headers=headers, **kwargs)

                # Check if we should retry on this status
                if (
                    response.status_code >= 400
                    and self.retry_config.should_retry(response.status_code)
                    and attempt < self.retry_config.max_retries
                ):
                    delay = self.retry_config.get_delay(attempt)
                    await asyncio.sleep(delay)
                    continue

                return response

            except (httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < self.retry_config.max_retries:
                    delay = self.retry_config.get_delay(attempt)
                    await asyncio.sleep(delay)
                    continue
                raise

        if last_error:
            raise last_error

        # Should never reach here
        raise RuntimeError("Unexpected state in HTTP client")

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "HTTPClient":
        """Enter async context."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context."""
        await self.close()


# Shared client instance for module-level use
_shared_client: HTTPClient | None = None


async def get_shared_client(
    timeout: float = 30.0,
    rate_limit: float = 2.0,
) -> HTTPClient:
    """Get shared HTTP client instance.

    Args:
        timeout: Request timeout.
        rate_limit: Rate limit.

    Returns:
        Shared HTTPClient instance.
    """
    global _shared_client

    if _shared_client is None:
        _shared_client = HTTPClient(timeout=timeout, rate_limit=rate_limit)

    return _shared_client


async def fetch_url(
    url: str,
    timeout: float = 30.0,
    headers: dict[str, str] | None = None,
) -> str:
    """Simple URL fetch function.

    Args:
        url: URL to fetch.
        timeout: Request timeout.
        headers: Additional headers.

    Returns:
        Response text content.

    Raises:
        httpx.HTTPError: If request fails.
    """
    client = await get_shared_client(timeout=timeout)
    response = await client.get(url, headers=headers)
    response.raise_for_status()
    return response.text
