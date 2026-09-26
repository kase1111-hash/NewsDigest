"""Metadata parser for NewsDigest."""

import json
from typing import Any

from bs4 import BeautifulSoup


class MetadataParser:
    """Extracts metadata from HTML.

    Parses:
    - <meta> tags
    - Open Graph tags
    - Twitter cards
    - JSON-LD structured data
    - Schema.org markup
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize metadata parser.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}

    def parse(self, html: str) -> dict[str, Any]:
        """Extract metadata from HTML.

        Args:
            html: HTML content.

        Returns:
            Dictionary of extracted metadata.
        """
        if not html:
            return {}

        soup = BeautifulSoup(html, "lxml")
        metadata: dict[str, Any] = {}

        # Extract from meta tags
        self._parse_meta_tags(soup, metadata)

        # Extract from Open Graph
        self._parse_open_graph(soup, metadata)

        # Extract from Twitter cards
        self._parse_twitter_cards(soup, metadata)

        # Extract from JSON-LD
        self._parse_json_ld(soup, metadata)

        # Extract title from <title> tag if not found
        if not metadata.get("title"):
            title_tag = soup.find("title")
            if title_tag:
                metadata["title"] = title_tag.get_text(strip=True)

        # Extract language
        html_tag = soup.find("html")
        if html_tag and html_tag.get("lang"):
            metadata["language"] = html_tag["lang"][:2]  # Just language code

        return metadata

    def _parse_meta_tags(self, soup: BeautifulSoup, metadata: dict[str, Any]) -> None:
        """Parse standard meta tags.

        Args:
            soup: BeautifulSoup object.
            metadata: Dictionary to update.
        """
        meta_mapping = {
            "author": ["author", "article:author"],
            "description": ["description"],
            "keywords": ["keywords"],
            "published_time": [
                "article:published_time",
                "date",
                "pubdate",
                "publish-date",
            ],
            "modified_time": ["article:modified_time", "last-modified"],
        }

        for key, names in meta_mapping.items():
            if key in metadata:
                continue

            for name in names:
                meta = soup.find("meta", attrs={"name": name}) or soup.find(
                    "meta", attrs={"property": name}
                )
                if meta and meta.get("content"):
                    metadata[key] = meta["content"]
                    break

    def _parse_open_graph(self, soup: BeautifulSoup, metadata: dict[str, Any]) -> None:
        """Parse Open Graph metadata.

        Args:
            soup: BeautifulSoup object.
            metadata: Dictionary to update.
        """
        og_mapping = {
            "title": "og:title",
            "description": "og:description",
            "site_name": "og:site_name",
            "url": "og:url",
            "image": "og:image",
            "type": "og:type",
            "published_time": "article:published_time",
            "author": "article:author",
        }

        for key, property_name in og_mapping.items():
            if key in metadata:
                continue

            meta = soup.find("meta", attrs={"property": property_name})
            if meta and meta.get("content"):
                metadata[key] = meta["content"]

    def _parse_twitter_cards(
        self, soup: BeautifulSoup, metadata: dict[str, Any]
    ) -> None:
        """Parse Twitter card metadata.

        Args:
            soup: BeautifulSoup object.
            metadata: Dictionary to update.
        """
        twitter_mapping = {
            "title": "twitter:title",
            "description": "twitter:description",
            "image": "twitter:image",
            "creator": "twitter:creator",
        }

        for key, name in twitter_mapping.items():
            if key in metadata:
                continue

            meta = soup.find("meta", attrs={"name": name})
            if meta and meta.get("content"):
                if key == "creator":
                    metadata["author"] = metadata.get("author") or meta["content"]
                else:
                    metadata[key] = meta["content"]

    def _parse_json_ld(self, soup: BeautifulSoup, metadata: dict[str, Any]) -> None:
        """Parse JSON-LD structured data.

        Args:
            soup: BeautifulSoup object.
            metadata: Dictionary to update.
        """
        scripts = soup.find_all("script", attrs={"type": "application/ld+json"})

        for script in scripts:
            if script.string is None:
                continue
            try:
                data = json.loads(script.string)
                self._extract_from_json_ld(data, metadata)
            except (json.JSONDecodeError, TypeError):
                continue

    def _extract_from_json_ld(self, data: Any, metadata: dict[str, Any]) -> None:
        """Extract metadata from JSON-LD object.

        Args:
            data: JSON-LD data (dict or list).
            metadata: Dictionary to update.
        """
        if isinstance(data, list):
            for item in data:
                self._extract_from_json_ld(item, metadata)
            return

        if not isinstance(data, dict):
            return

        # Handle @graph arrays
        if "@graph" in data:
            self._extract_from_json_ld(data["@graph"], metadata)
            return

        # Check @type for article types
        schema_type = data.get("@type", "")
        if isinstance(schema_type, list):
            schema_type = schema_type[0] if schema_type else ""

        article_types = [
            "Article",
            "NewsArticle",
            "BlogPosting",
            "WebPage",
            "ReportageNewsArticle",
        ]

        if schema_type in article_types or not schema_type:
            # Extract fields
            if not metadata.get("title") and data.get("headline"):
                metadata["title"] = data["headline"]

            if not metadata.get("description") and data.get("description"):
                metadata["description"] = data["description"]

            if not metadata.get("published_time") and data.get("datePublished"):
                metadata["published_time"] = data["datePublished"]

            if not metadata.get("modified_time") and data.get("dateModified"):
                metadata["modified_time"] = data["dateModified"]

            # Handle author
            if not metadata.get("author"):
                author = data.get("author")
                if isinstance(author, dict):
                    metadata["author"] = author.get("name")
                elif isinstance(author, list) and author:
                    first_author = author[0]
                    if isinstance(first_author, dict):
                        metadata["author"] = first_author.get("name")
                    else:
                        metadata["author"] = str(first_author)
                elif isinstance(author, str):
                    metadata["author"] = author

            # Handle publisher
            if not metadata.get("site_name"):
                publisher = data.get("publisher")
                if isinstance(publisher, dict):
                    metadata["site_name"] = publisher.get("name")

    def get_canonical_url(self, html: str) -> str | None:
        """Get canonical URL from HTML.

        Args:
            html: HTML content.

        Returns:
            Canonical URL or None.
        """
        soup = BeautifulSoup(html, "lxml")

        # Check link rel="canonical"
        link = soup.find("link", attrs={"rel": "canonical"})
        if link and link.get("href"):
            return str(link["href"])

        # Check og:url
        meta = soup.find("meta", attrs={"property": "og:url"})
        if meta and meta.get("content"):
            return str(meta["content"])

        return None

    def get_all_metadata(self, html: str) -> dict[str, Any]:
        """Get all metadata including raw tags.

        Args:
            html: HTML content.

        Returns:
            Complete metadata dictionary.
        """
        metadata = self.parse(html)

        # Add canonical URL
        canonical = self.get_canonical_url(html)
        if canonical:
            metadata["canonical_url"] = canonical

        return metadata
