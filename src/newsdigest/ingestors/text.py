"""Text ingestor for NewsDigest."""

import hashlib
import re
from pathlib import Path

from newsdigest.core.article import Article, SourceType
from newsdigest.ingestors.base import BaseIngestor
from newsdigest.utils.validation import sanitize_text


# A leading line is only a headline if it stands alone as a paragraph
_PARAGRAPH_BREAK = re.compile(r"\n[^\S\n]*\n")
MAX_TITLE_CHARS = 200
MAX_TITLE_WORDS = 25


class TextIngestor(BaseIngestor):
    """Ingests plain text content directly.

    Used for:
    - Direct text input from CLI
    - Copy-pasted article content
    - File content
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize text ingestor.

        Args:
            config: Configuration dictionary.
        """
        super().__init__(config)

    async def ingest(self, source: str) -> Article:
        """Create article from text content.

        Args:
            source: Plain text content.

        Returns:
            Article object.
        """
        return self.from_text(source)

    async def ingest_batch(self, sources: list[str]) -> list[Article]:
        """Create articles from multiple text sources.

        Args:
            sources: List of text content.

        Returns:
            List of Article objects.
        """
        return [self.from_text(text) for text in sources]

    def from_text(
        self,
        text: str,
        title: str | None = None,
        source_name: str | None = None,
        url: str | None = None,
    ) -> Article:
        """Create article from plain text.

        Args:
            text: Plain text content.
            title: Optional title.
            source_name: Optional source name.
            url: Optional URL reference.

        Returns:
            Article object.
        """
        # Pasted content often carries markup; strip it (and anything
        # executable) while keeping line structure for title detection
        text = sanitize_text(text, strip_html=True, normalize_whitespace=True)

        # Generate ID from content
        article_id = hashlib.sha256(text.encode()).hexdigest()[:16]

        # Use a standalone first paragraph as the title if not provided
        if not title and text:
            title, text = self._split_title(text)

        return Article(
            id=article_id,
            content=text,
            url=url,
            title=title,
            source_name=source_name or "Direct Input",
            source_type=SourceType.TEXT,
        )

    @staticmethod
    def _split_title(text: str) -> tuple[str | None, str]:
        """Split a headline off the start of the text, if there is one.

        The first paragraph counts as a headline only when it is a single
        short line followed by more content and does not end like a sentence,
        so hard-wrapped body text is never mistaken for a title.

        Args:
            text: Sanitized article text.

        Returns:
            Tuple of (title or None, remaining body text).
        """
        parts = _PARAGRAPH_BREAK.split(text, maxsplit=1)
        if len(parts) < 2 or not parts[1].strip():
            return None, text

        first = parts[0].strip()
        if (
            "\n" in first
            or len(first) > MAX_TITLE_CHARS
            or len(first.split()) > MAX_TITLE_WORDS
            or first.endswith((".", ",", ";", ":"))
        ):
            return None, text

        return first, parts[1].strip()

    def from_file(self, file_path: str) -> Article:
        """Create article from file.

        Args:
            file_path: Path to text file.

        Returns:
            Article object.

        Raises:
            FileNotFoundError: If file doesn't exist.
        """
        content = Path(file_path).read_text(encoding="utf-8")

        return self.from_text(content, source_name=file_path)

    def from_stdin(self) -> Article:
        """Create article from stdin.

        Returns:
            Article object.
        """
        import sys

        content = sys.stdin.read()
        return self.from_text(content, source_name="stdin")
