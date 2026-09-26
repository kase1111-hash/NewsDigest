"""URL fetcher for NewsDigest."""

import asyncio
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from newsdigest.core.article import Article, SourceType
from newsdigest.ingestors.base import BaseIngestor
from newsdigest.parsers.article import ArticleExtractor
from newsdigest.utils.validation import (
    sanitize_html,
    validate_url_strict,
)


class URLFetcher(BaseIngestor):
    """Fetches article content from URLs.

    Features:
    - Async HTTP with httpx
    - Automatic redirect handling
    - User-agent rotation
    - Rate limiting per domain
    - Timeout handling
    - Retry with exponential backoff
    - Input URL validation
    - HTML sanitization
    """

    DEFAULT_USER_AGENT = (
        "Mozilla/5.0 (compatible; NewsDigest/0.1; +https://github.com/newsdigest)"
    )

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize URL fetcher.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self.timeout = self.config.get("timeout", 30)
        self.retries = self.config.get("retries", 3)
        self.user_agent = self.config.get("user_agent", self.DEFAULT_USER_AGENT)
        self.requests_per_second = self.config.get("requests_per_second", 1.0)

        self._article_extractor = ArticleExtractor(config)
        self._domain_last_request: dict[str, float] = {}
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (connection pooling).

        A client's connections belong to the event loop that created it, and
        each Extractor.extract_sync() call runs a new loop, so the client is
        recreated whenever the running loop changes.
        """
        loop = asyncio.get_running_loop()
        if (
            self._client is None
            or self._client.is_closed
            or self._client_loop is not loop
        ):
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={"User-Agent": self.user_agent},
                event_hooks={"request": [self._validate_request_url]},
            )
            self._client_loop = loop
        return self._client

    @staticmethod
    async def _validate_request_url(request: httpx.Request) -> None:
        """Re-validate every request, including redirects.

        Only the initial URL is validated by ingest(), so without this a
        public URL could redirect to an internal address.
        """
        validate_url_strict(str(request.url))

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "URLFetcher":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: object) -> None:
        """Async context manager exit."""
        await self.close()

    async def ingest(self, source: str) -> Article:
        """Fetch and parse article from URL.

        Args:
            source: URL to fetch.

        Returns:
            Article object with content and metadata.

        Raises:
            ValidationError: If URL is invalid.
            httpx.HTTPError: If fetch fails after retries.
        """
        # Validate URL before fetching
        validated_url = validate_url_strict(source)

        html = await self._fetch_with_retry(validated_url)

        # Sanitize HTML before parsing
        html = sanitize_html(html)

        article = self._article_extractor.extract(html, validated_url)
        article.source_type = SourceType.URL
        return article

    async def ingest_batch(
        self,
        sources: list[str],
        max_concurrent: int = 5,
    ) -> list[Article]:
        """Fetch multiple URLs concurrently.

        Args:
            sources: List of URLs to fetch.
            max_concurrent: Maximum concurrent requests.

        Returns:
            List of Article objects (failed fetches excluded).
        """
        semaphore = asyncio.Semaphore(max_concurrent)

        async def fetch_one(url: str) -> Article | None:
            async with semaphore:
                try:
                    return await self.ingest(url)
                except Exception:
                    return None

        tasks = [fetch_one(url) for url in sources]
        results = await asyncio.gather(*tasks)

        return [a for a in results if a is not None]

    async def _fetch_with_retry(self, url: str) -> str:
        """Fetch URL with retry logic.

        Args:
            url: URL to fetch.

        Returns:
            HTML content.

        Raises:
            httpx.HTTPError: If all retries fail.
        """
        response = await self._get_with_retry(url)
        return response.text

    async def _get_with_retry(self, url: str) -> httpx.Response:
        """Send a GET request with retry logic.

        Args:
            url: URL to fetch.

        Returns:
            Successful response.

        Raises:
            httpx.HTTPError: If all retries fail.
        """
        # Rate limiting per domain
        await self._rate_limit(url)

        last_error: httpx.HTTPError | None = None
        client = await self._get_client()
        # "retries" counts additional attempts after the first one
        attempts = max(0, self.retries) + 1
        for attempt in range(attempts):
            is_last = attempt == attempts - 1
            try:
                response = await client.get(url)
                response.raise_for_status()
                return response

            except httpx.HTTPStatusError as e:
                last_error = e
                status = e.response.status_code
                if status != 429 and status < 500:
                    # Client error, don't retry
                    raise
                if not is_last:
                    # Rate limited waits longer than a server error
                    await asyncio.sleep(
                        2 ** (attempt + 2) if status == 429 else 2**attempt
                    )

            except (httpx.TimeoutException, httpx.ConnectError) as e:
                last_error = e
                if not is_last:
                    await asyncio.sleep(2**attempt)

        raise last_error or httpx.HTTPError(f"Failed to fetch {url}")

    async def _rate_limit(self, url: str) -> None:
        """Apply rate limiting for domain.

        Args:
            url: URL being fetched.
        """
        if self.requests_per_second <= 0:
            return

        domain = urlparse(url).netloc
        current_time = time.time()
        min_interval = 1.0 / self.requests_per_second

        if domain in self._domain_last_request:
            elapsed = current_time - self._domain_last_request[domain]
            if elapsed < min_interval:
                await asyncio.sleep(min_interval - elapsed)

        self._domain_last_request[domain] = time.time()

    async def fetch_raw(self, url: str) -> str:
        """Fetch raw content without parsing.

        Args:
            url: URL to fetch.

        Returns:
            Raw response body.

        Raises:
            ValidationError: If URL is invalid.
            httpx.HTTPError: If fetch fails after retries.
        """
        return await self._fetch_with_retry(validate_url_strict(url))

    async def fetch_bytes(self, url: str) -> bytes:
        """Fetch the raw response body without decoding it.

        Args:
            url: URL to fetch.

        Returns:
            Response body bytes.

        Raises:
            ValidationError: If URL is invalid.
            httpx.HTTPError: If fetch fails after retries.
        """
        response = await self._get_with_retry(validate_url_strict(url))
        return response.content
