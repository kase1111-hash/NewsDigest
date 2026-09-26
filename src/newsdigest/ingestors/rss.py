"""RSS feed parser for NewsDigest."""

import asyncio
import calendar
import hashlib
import io
from datetime import UTC, datetime
from urllib.parse import urlparse

import feedparser

from newsdigest.core.article import Article, SourceType
from newsdigest.ingestors.base import BaseIngestor
from newsdigest.ingestors.url import URLFetcher


class RSSParser(BaseIngestor):
    """Parses RSS/Atom feeds.

    Uses feedparser to extract articles from RSS feeds.
    Can optionally fetch full article content from links.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize RSS parser.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)
        self.fetch_full_content = self.config.get("fetch_full_content", True)
        self.max_items = self.config.get("max_items", 50)
        # Feeds are downloaded through URLFetcher so they get the same URL
        # validation (no private/internal hosts), timeouts and retries
        self._url_fetcher = URLFetcher(config)

    async def _fetch_feed(self, feed_url: str) -> feedparser.FeedParserDict:
        """Download and parse a feed.

        Args:
            feed_url: URL of the RSS/Atom feed.

        Returns:
            Parsed feed.
        """
        content = await self._url_fetcher.fetch_bytes(feed_url)
        # Pass a stream: given a string, feedparser treats URLs and file
        # paths as locations to fetch/open rather than as feed content
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, feedparser.parse, io.BytesIO(content))

    async def ingest(self, source: str) -> Article:
        """Parse RSS feed and return first article.

        Args:
            source: RSS feed URL.

        Returns:
            First Article from feed.

        Raises:
            ValueError: If feed is empty or invalid.
        """
        articles = await self.parse(source, limit=1)
        if not articles:
            raise ValueError(f"No articles found in feed: {source}")
        return articles[0]

    async def ingest_batch(self, sources: list[str]) -> list[Article]:
        """Parse multiple RSS feeds.

        Args:
            sources: List of RSS feed URLs.

        Returns:
            Combined list of Articles from all feeds.
        """
        tasks = [self.parse(url) for url in sources]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        articles = []
        for result in results:
            if isinstance(result, list):
                articles.extend(result)
            # Skip exceptions

        return articles

    async def parse(
        self,
        feed_url: str,
        limit: int | None = None,
    ) -> list[Article]:
        """Parse RSS feed and return list of articles.

        Args:
            feed_url: URL of the RSS feed.
            limit: Maximum number of items to return.

        Returns:
            List of Article objects.
        """
        feed = await self._fetch_feed(feed_url)

        if feed.bozo and not feed.entries:
            # Feed has error and no entries
            raise ValueError(f"Invalid RSS feed: {feed_url}")

        # Get feed metadata
        feed_title = feed.feed.get("title", "")
        feed_link = feed.feed.get("link", "")

        # Parse source name from URL
        source_name = feed_title or urlparse(feed_url).netloc.replace("www.", "")

        # Process entries
        max_items = limit or self.max_items
        articles = []

        for entry in feed.entries[:max_items]:
            article = await self._parse_entry(entry, source_name, feed_url)
            if article:
                articles.append(article)

        return articles

    async def _parse_entry(
        self,
        entry: dict,
        source_name: str,
        feed_url: str,
    ) -> Article | None:
        """Parse a single feed entry into an Article.

        Args:
            entry: feedparser entry dict.
            source_name: Name of the feed source.
            feed_url: URL of the feed.

        Returns:
            Article object or None if parsing fails.
        """
        # Get link
        link = entry.get("link", "")

        # Get title
        title = entry.get("title", "")

        # Get content - prefer full content, fall back to summary
        content = ""
        if "content" in entry and entry.content:
            content = entry.content[0].get("value", "")
        elif "summary" in entry:
            content = entry.get("summary", "")

        # If we should fetch full content and have a link
        if self.fetch_full_content and link:
            try:
                full_article = await self._url_fetcher.ingest(link)
                # Use fetched content if longer
                if len(full_article.content) > len(content):
                    content = full_article.content
                    if not title:
                        title = full_article.title
            except Exception:
                # Fall back to feed content
                pass

        if not content:
            return None

        # Generate ID
        article_id = self._generate_id(link or content)

        # Parse published date
        published_at = self._parse_date(entry)

        # Get author
        author = entry.get("author", "")

        return Article(
            id=article_id,
            content=content,
            url=link,
            title=title,
            source_name=source_name,
            source_type=SourceType.RSS,
            author=author,
            published_at=published_at,
        )

    def _generate_id(self, identifier: str) -> str:
        """Generate unique article ID.

        Args:
            identifier: String to hash.

        Returns:
            Unique ID string.
        """
        return hashlib.sha256(identifier.encode()).hexdigest()[:16]

    def _parse_date(self, entry: dict) -> datetime | None:
        """Parse published date from entry.

        Args:
            entry: feedparser entry dict.

        Returns:
            Datetime object or None.
        """
        # feedparser provides parsed dates as UTC time structs
        for date_field in ["published_parsed", "updated_parsed", "created_parsed"]:
            if entry.get(date_field):
                try:
                    return datetime.fromtimestamp(
                        calendar.timegm(entry[date_field]), tz=UTC
                    )
                except (ValueError, OverflowError, OSError):
                    continue

        return None

    async def get_new_items(
        self,
        feed_url: str,
        since: datetime,
    ) -> list[Article]:
        """Get only items published since given time.

        Args:
            feed_url: RSS feed URL.
            since: Cutoff datetime.

        Returns:
            List of articles published after since.
        """
        all_articles = await self.parse(feed_url)

        # Treat naive datetimes as UTC so they compare with aware ones
        if since.tzinfo is None:
            since = since.replace(tzinfo=UTC)

        return [
            article
            for article in all_articles
            if article.published_at and article.published_at > since
        ]

    async def get_feed_info(self, feed_url: str) -> dict:
        """Get feed metadata without fetching articles.

        Args:
            feed_url: RSS feed URL.

        Returns:
            Dictionary with feed metadata.
        """
        feed = await self._fetch_feed(feed_url)

        return {
            "title": feed.feed.get("title", ""),
            "link": feed.feed.get("link", ""),
            "description": feed.feed.get("description", ""),
            "language": feed.feed.get("language", ""),
            "item_count": len(feed.entries),
        }
