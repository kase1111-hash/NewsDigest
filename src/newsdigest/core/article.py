"""Article data structures for NewsDigest."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum


def _utc_now() -> datetime:
    """Return current UTC time (timezone-aware)."""
    return datetime.now(UTC)


class SourceType(Enum):
    """Type of content source."""

    URL = "url"
    RSS = "rss"
    NEWSAPI = "newsapi"
    EMAIL = "email"
    TWITTER = "twitter"
    PDF = "pdf"
    TEXT = "text"  # Direct text input


@dataclass
class Article:
    """Represents a parsed news article."""

    # Required fields
    id: str
    content: str

    # Metadata
    url: str | None = None
    title: str | None = None
    source_name: str | None = None
    source_type: SourceType = SourceType.URL
    author: str | None = None
    published_at: datetime | None = None
    fetched_at: datetime = field(default_factory=_utc_now)

    # Computed fields
    word_count: int = 0
    language: str = "en"

    def __post_init__(self) -> None:
        """Compute word count after initialization."""
        if self.word_count == 0 and self.content:
            self.word_count = len(self.content.split())
