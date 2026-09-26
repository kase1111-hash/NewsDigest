"""Base class for all ingestors."""

from abc import ABC, abstractmethod
from typing import Any

from newsdigest.core.article import Article


class BaseIngestor(ABC):
    """Base class for all content ingestors.

    Ingestors are responsible for fetching content from various sources
    and converting it into Article objects.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize ingestor with configuration.

        Args:
            config: Ingestor-specific configuration dictionary.
        """
        self.config = config or {}

    @property
    def name(self) -> str:
        """Return the ingestor name."""
        return self.__class__.__name__

    @abstractmethod
    async def ingest(self, source: str) -> Article:
        """
        Ingest content from a source.

        Args:
            source: Source identifier (URL, path, etc.).

        Returns:
            Article object with content and metadata.
        """
        pass

    @abstractmethod
    async def ingest_batch(self, sources: list[str]) -> list[Article]:
        """
        Ingest content from multiple sources.

        Args:
            sources: List of source identifiers.

        Returns:
            List of Article objects.
        """
        pass
