"""Tests for the RSSParser."""

from datetime import UTC, datetime

import pytest

from newsdigest.ingestors.rss import RSSParser


FEED = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Example Feed</title>
<item><title>Old story</title><link>https://example.com/old</link>
<pubDate>Mon, 01 Jan 2024 12:00:00 GMT</pubDate>
<description>Old news about the economy and markets.</description></item>
<item><title>New story</title><link>https://example.com/new</link>
<pubDate>Sat, 26 Sep 2026 12:00:00 GMT</pubDate>
<description>New figures show the economy grew 2% last quarter.</description></item>
</channel></rss>"""


@pytest.fixture
def parser(monkeypatch) -> RSSParser:
    """RSS parser whose downloads return FEED instead of hitting the network."""
    parser = RSSParser({"fetch_full_content": False})
    fetched: list[str] = []

    async def fake_fetch_bytes(url: str) -> bytes:
        fetched.append(url)
        return FEED

    monkeypatch.setattr(parser._url_fetcher, "fetch_bytes", fake_fetch_bytes)
    parser.fetched = fetched  # type: ignore[attr-defined]
    return parser


class TestRSSParser:
    """Tests for feed parsing."""

    async def test_feed_downloaded_through_fetcher(self, parser) -> None:
        """Test feeds go through URLFetcher (and its URL validation)."""
        articles = await parser.parse("https://example.com/feed.xml")

        assert parser.fetched == ["https://example.com/feed.xml"]
        assert [a.title for a in articles] == ["Old story", "New story"]
        assert articles[0].source_name == "Example Feed"

    async def test_dates_are_utc(self, parser) -> None:
        """Test feed dates are converted as UTC, not local time."""
        articles = await parser.parse("https://example.com/feed.xml")
        assert articles[0].published_at == datetime(2024, 1, 1, 12, tzinfo=UTC)

    async def test_get_new_items_accepts_naive_since(self, parser) -> None:
        """Test a naive cutoff is treated as UTC instead of failing to compare."""
        articles = await parser.get_new_items(
            "https://example.com/feed.xml", datetime(2025, 1, 1)
        )
        assert [a.title for a in articles] == ["New story"]

    async def test_internal_feed_url_rejected(self) -> None:
        """Test feed URLs pointing at internal hosts are refused."""
        from newsdigest.utils.validation import ValidationError  # noqa: PLC0415

        with pytest.raises(ValidationError):
            await RSSParser().parse("http://127.0.0.1:8080/feed.xml")
