"""Tests for the URLFetcher."""

import asyncio

import httpx
import pytest

from newsdigest.ingestors.url import URLFetcher
from newsdigest.utils.validation import ValidationError


class TestURLFetcherClient:
    """Tests for HTTP client management."""

    def test_client_recreated_for_each_event_loop(self) -> None:
        """Test a client from a finished loop is not reused in a new one."""
        fetcher = URLFetcher()

        first = asyncio.run(fetcher._get_client())
        second = asyncio.run(fetcher._get_client())

        assert first is not second

    async def test_client_reused_within_loop(self) -> None:
        """Test connection pooling within one event loop."""
        fetcher = URLFetcher()
        assert await fetcher._get_client() is await fetcher._get_client()
        await fetcher.close()


class TestURLFetcherSafety:
    """Tests for request validation."""

    @pytest.mark.parametrize(
        "url",
        [
            "http://127.0.0.1/admin",
            "http://169.254.169.254/latest/meta-data/",
            "http://[::1]/",
        ],
    )
    async def test_redirect_targets_are_validated(self, url) -> None:
        """Test every request (including redirects) goes through URL checks."""
        with pytest.raises(ValidationError):
            await URLFetcher._validate_request_url(httpx.Request("GET", url))

    async def test_fetch_raw_validates_url(self) -> None:
        """Test raw fetching cannot be pointed at internal hosts."""
        with pytest.raises(ValidationError):
            await URLFetcher().fetch_raw("http://localhost/secret")


class TestURLFetcherRetries:
    """Tests for retry behavior."""

    @pytest.mark.parametrize("retries,expected_attempts", [(0, 1), (2, 3)])
    async def test_retries_count_additional_attempts(
        self, monkeypatch, retries, expected_attempts
    ) -> None:
        """Test retries=0 still makes one attempt and N retries make N+1."""
        attempts = 0

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal attempts
            attempts += 1
            return httpx.Response(503, request=request)

        async def no_sleep(_: float) -> None:
            return None

        monkeypatch.setattr(asyncio, "sleep", no_sleep)
        fetcher = URLFetcher({"retries": retries, "requests_per_second": 0})
        fetcher._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        fetcher._client_loop = asyncio.get_running_loop()

        with pytest.raises(httpx.HTTPStatusError):
            await fetcher._fetch_with_retry("https://example.com/")
        assert attempts == expected_attempts
