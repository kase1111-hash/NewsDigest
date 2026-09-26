"""NewsAPI integration for NewsDigest.

Fetches articles from NewsAPI.org for digest generation.
Requires: pip install newsdigest[newsapi]
"""

import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx

from newsdigest.utils.logging import get_logger


try:
    from newsapi import NewsApiClient

    HAS_NEWSAPI = True
except ImportError:
    HAS_NEWSAPI = False
    NewsApiClient = None


logger = get_logger(__name__)


@dataclass
class NewsAPIArticle:
    """Article fetched from NewsAPI."""

    title: str
    description: str | None
    content: str | None
    url: str
    source_name: str
    author: str | None
    published_at: datetime | None
    url_to_image: str | None = None


@dataclass
class NewsAPIConfig:
    """NewsAPI configuration."""

    api_key: str
    language: str = "en"
    page_size: int = 20
    sort_by: str = "publishedAt"  # relevancy, popularity, publishedAt


class NewsAPIClient:
    """Client for fetching articles from NewsAPI.

    NewsAPI provides access to articles from 80,000+ news sources.

    Example:
        >>> client = NewsAPIClient(api_key="your-api-key")
        >>> articles = await client.get_top_headlines(category="technology")
        >>> articles = await client.search("artificial intelligence")
    """

    BASE_URL = "https://newsapi.org/v2"

    def __init__(self, config: NewsAPIConfig | None = None, api_key: str = "") -> None:
        """Initialize NewsAPI client.

        Args:
            config: NewsAPI configuration.
            api_key: API key (alternative to config).
        """
        if config:
            self.config = config
        else:
            self.config = NewsAPIConfig(api_key=api_key)

        if not self.config.api_key:
            raise ValueError("NewsAPI key is required. Get one at https://newsapi.org")

        self._client = httpx.AsyncClient(
            headers={"X-Api-Key": self.config.api_key},
            timeout=30.0,
        )

    async def get_top_headlines(
        self,
        category: str | None = None,
        country: str = "us",
        query: str | None = None,
        sources: list[str] | None = None,
        page: int = 1,
    ) -> list[NewsAPIArticle]:
        """Get top headlines.

        Args:
            category: Category (business, entertainment, general, health,
                     science, sports, technology).
            country: 2-letter country code.
            query: Keywords to search for.
            sources: Specific source IDs (cannot use with country/category).
            page: Page number for pagination.

        Returns:
            List of articles.
        """
        params: dict[str, Any] = {
            "pageSize": self.config.page_size,
            "page": page,
        }

        if sources:
            params["sources"] = ",".join(sources)
        else:
            params["country"] = country
            if category:
                params["category"] = category

        if query:
            params["q"] = query

        response = await self._client.get(
            f"{self.BASE_URL}/top-headlines",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        return self._parse_articles(data.get("articles", []))

    async def search(
        self,
        query: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
        domains: list[str] | None = None,
        exclude_domains: list[str] | None = None,
        sources: list[str] | None = None,
        page: int = 1,
    ) -> list[NewsAPIArticle]:
        """Search for articles.

        Args:
            query: Search query (supports AND/OR/NOT operators).
            from_date: Oldest article date.
            to_date: Newest article date.
            domains: Domains to include (e.g., ['bbc.co.uk', 'cnn.com']).
            exclude_domains: Domains to exclude.
            sources: Specific source IDs.
            page: Page number for pagination.

        Returns:
            List of matching articles.
        """
        params: dict[str, Any] = {
            "q": query,
            "language": self.config.language,
            "sortBy": self.config.sort_by,
            "pageSize": self.config.page_size,
            "page": page,
        }

        if from_date:
            params["from"] = from_date.isoformat()

        if to_date:
            params["to"] = to_date.isoformat()

        if domains:
            params["domains"] = ",".join(domains)

        if exclude_domains:
            params["excludeDomains"] = ",".join(exclude_domains)

        if sources:
            params["sources"] = ",".join(sources)

        response = await self._client.get(
            f"{self.BASE_URL}/everything",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        return self._parse_articles(data.get("articles", []))

    async def get_sources(
        self,
        category: str | None = None,
        language: str | None = None,
        country: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get available news sources.

        Args:
            category: Filter by category.
            language: Filter by language.
            country: Filter by country.

        Returns:
            List of source dictionaries.
        """
        params: dict[str, Any] = {}

        if category:
            params["category"] = category
        if language:
            params["language"] = language
        if country:
            params["country"] = country

        response = await self._client.get(
            f"{self.BASE_URL}/sources",
            params=params,
        )
        response.raise_for_status()

        data = response.json()
        sources: list[dict[str, Any]] = data.get("sources", [])
        return sources

    async def get_recent(
        self,
        query: str,
        hours: int = 24,
    ) -> list[NewsAPIArticle]:
        """Get recent articles matching a query.

        Convenience method for searching within a time window.

        Args:
            query: Search query.
            hours: Number of hours to look back.

        Returns:
            List of recent articles.
        """
        from_date = datetime.now(UTC) - timedelta(hours=hours)
        return await self.search(query=query, from_date=from_date)

    def _parse_articles(
        self,
        articles: list[dict[str, Any]],
    ) -> list[NewsAPIArticle]:
        """Parse article data from API response.

        Args:
            articles: Raw article data from API.

        Returns:
            List of NewsAPIArticle objects.
        """
        result = []

        for article in articles:
            # Parse published date
            published_str = article.get("publishedAt")
            published_at = None
            if published_str:
                with contextlib.suppress(ValueError):
                    published_at = datetime.fromisoformat(
                        published_str.replace("Z", "+00:00")
                    )

            result.append(
                NewsAPIArticle(
                    title=article.get("title", ""),
                    description=article.get("description"),
                    content=article.get("content"),
                    url=article.get("url", ""),
                    source_name=article.get("source", {}).get("name", "Unknown"),
                    author=article.get("author"),
                    published_at=published_at,
                    url_to_image=article.get("urlToImage"),
                )
            )

        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def __aenter__(self) -> "NewsAPIClient":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class NewsAPIIngestor:
    """Ingestor that fetches articles from NewsAPI for digest generation.

    Integrates with the NewsDigest pipeline to provide articles
    from NewsAPI as a source.

    Example:
        >>> ingestor = NewsAPIIngestor(api_key="your-key")
        >>> ingestor.add_query("technology", category="technology")
        >>> ingestor.add_query("AI news", query="artificial intelligence")
        >>> articles = await ingestor.fetch_all()
    """

    def __init__(self, api_key: str, config: NewsAPIConfig | None = None) -> None:
        """Initialize ingestor.

        Args:
            api_key: NewsAPI API key.
            config: Optional configuration.
        """
        self.config = config or NewsAPIConfig(api_key=api_key)
        self._client = NewsAPIClient(config=self.config)
        self._queries: list[dict[str, Any]] = []

    def add_headlines(
        self,
        name: str,
        category: str | None = None,
        country: str = "us",
    ) -> None:
        """Add top headlines source.

        Args:
            name: Display name for this source.
            category: News category.
            country: Country code.
        """
        self._queries.append(
            {
                "type": "headlines",
                "name": name,
                "category": category,
                "country": country,
            }
        )

    def add_search(
        self,
        name: str,
        query: str,
        domains: list[str] | None = None,
    ) -> None:
        """Add search query source.

        Args:
            name: Display name for this source.
            query: Search query.
            domains: Optional domain filter.
        """
        self._queries.append(
            {
                "type": "search",
                "name": name,
                "query": query,
                "domains": domains,
            }
        )

    async def fetch_all(
        self,
        hours: int = 24,
    ) -> list[dict[str, Any]]:
        """Fetch articles from all configured sources.

        Args:
            hours: How far back to search (for search queries).

        Returns:
            List of article dictionaries ready for extraction.
        """
        all_articles: list[dict[str, Any]] = []
        from_date = datetime.now(UTC) - timedelta(hours=hours)

        for query_config in self._queries:
            try:
                if query_config["type"] == "headlines":
                    articles = await self._client.get_top_headlines(
                        category=query_config.get("category"),
                        country=query_config.get("country", "us"),
                    )
                else:
                    articles = await self._client.search(
                        query=query_config["query"],
                        from_date=from_date,
                        domains=query_config.get("domains"),
                    )

                all_articles.extend(
                    {
                        "url": article.url,
                        "title": article.title,
                        "source_name": query_config["name"],
                        "published_at": article.published_at,
                        "content": article.content or article.description,
                    }
                    for article in articles
                )

            except Exception as e:
                # Skip failed queries
                logger.warning(f"NewsAPI query {query_config['name']!r} failed: {e}")
                continue

        return all_articles

    async def close(self) -> None:
        """Close the client."""
        await self._client.close()

    async def __aenter__(self) -> "NewsAPIIngestor":
        """Async context manager entry."""
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()
