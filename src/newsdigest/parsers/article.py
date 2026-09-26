"""Article extractor for NewsDigest."""

import hashlib
from datetime import datetime
from urllib.parse import urlparse

from newsdigest.core.article import Article, SourceType
from newsdigest.parsers.html import HTMLCleaner
from newsdigest.parsers.metadata import MetadataParser


class ArticleExtractor:
    """Extracts main article content from web pages.

    Uses readability algorithms and heuristics to:
    - Extract title
    - Extract author
    - Extract published date
    - Extract main body text
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize article extractor.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.html_cleaner = HTMLCleaner(config)
        self.metadata_parser = MetadataParser(config)
        self._readability_available = self._check_readability()

    def _check_readability(self) -> bool:
        """Check if readability-lxml is available."""
        try:
            from readability import Document  # noqa: F401

            return True
        except ImportError:
            return False

    def extract(self, html: str, url: str | None = None) -> Article:
        """Extract article from HTML.

        Args:
            html: Raw HTML content.
            url: Optional URL for the article.

        Returns:
            Article object with extracted content.
        """
        # Extract metadata first
        metadata = self.metadata_parser.parse(html)

        # Try readability-lxml for better article extraction
        if self._readability_available:
            content, title = self._extract_with_readability(html)
        else:
            content = self.html_cleaner.clean(html)
            title = metadata.get("title")

        # Use metadata title if readability didn't get one
        if not title:
            title = metadata.get("title")

        # The page's own headline is usually the first block of the body;
        # it is already the title, so keep it out of the content
        content = self._strip_leading_title(content, title)

        # Generate article ID
        article_id = self._generate_id(url, content)

        # Parse source name from URL
        source_name = None
        if url:
            parsed = urlparse(url)
            source_name = parsed.netloc.replace("www.", "")

        # Override with metadata source if available
        if metadata.get("site_name"):
            source_name = metadata.get("site_name")

        # Parse published date
        published_at = self._parse_date(metadata.get("published_time"))

        return Article(
            id=article_id,
            content=content,
            url=url,
            title=title,
            source_name=source_name,
            source_type=SourceType.URL,
            author=metadata.get("author"),
            published_at=published_at,
            language=metadata.get("language", "en"),
        )

    def _extract_with_readability(self, html: str) -> tuple[str, str | None]:
        """Extract using readability-lxml.

        Args:
            html: Raw HTML.

        Returns:
            Tuple of (content, title).
        """
        try:
            from readability import Document

            doc = Document(html)
            title = doc.title()

            # Get summary HTML and clean it
            summary_html = doc.summary()
            content = self.html_cleaner.clean(summary_html)

            return content, title
        except Exception:
            # Fall back to basic HTML cleaning
            content = self.html_cleaner.clean(html)
            return content, None

    @staticmethod
    def _strip_leading_title(content: str, title: str | None) -> str:
        """Remove a first paragraph that repeats the title.

        Args:
            content: Extracted text, paragraphs separated by blank lines.
            title: Article title.

        Returns:
            Content without the duplicated headline.
        """
        if not title:
            return content
        first, sep, rest = content.partition("\n\n")
        if sep and " ".join(first.split()).casefold() == " ".join(title.split()).casefold():
            return rest
        return content

    def _generate_id(self, url: str | None, content: str) -> str:
        """Generate unique article ID.

        Args:
            url: Article URL.
            content: Article content.

        Returns:
            Unique ID string.
        """
        # Hash URL if available, otherwise hash content
        if url:
            hash_input = url
        else:
            hash_input = content[:1000]  # First 1000 chars

        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]

    def _parse_date(self, date_str: str | None) -> datetime | None:
        """Parse date string to datetime.

        Args:
            date_str: Date string from metadata.

        Returns:
            Datetime object or None.
        """
        if not date_str:
            return None

        try:
            from dateutil import parser

            return parser.parse(date_str)
        except (ImportError, ValueError):
            pass

        # Try common formats manually
        formats = [
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d",
            "%B %d, %Y",
            "%d %B %Y",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except ValueError:
                continue

        return None

    def extract_from_text(
        self,
        text: str,
        title: str | None = None,
        source_name: str | None = None,
    ) -> Article:
        """Create article from plain text.

        Args:
            text: Plain text content.
            title: Optional title.
            source_name: Optional source name.

        Returns:
            Article object.
        """
        article_id = self._generate_id(None, text)

        return Article(
            id=article_id,
            content=text,
            title=title,
            source_name=source_name,
            source_type=SourceType.TEXT,
        )
