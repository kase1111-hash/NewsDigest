"""Base class for all output formatters."""

from abc import ABC, abstractmethod
from typing import Any

from newsdigest.core.result import ExtractionResult


class BaseFormatter(ABC):
    """Base class for all output formatters.

    Formatters convert ExtractionResult and Digest objects into
    various output formats (Markdown, JSON, HTML, etc.).
    """

    @abstractmethod
    def format_result(self, result: ExtractionResult) -> str:
        """Format a single extraction result."""
        pass

    @abstractmethod
    def format_digest(self, digest: Any) -> str:
        """Format a complete digest."""
        pass

    @abstractmethod
    def format_comparison(self, result: ExtractionResult) -> str:
        """Format side-by-side comparison."""
        pass

    @abstractmethod
    def format_stats(self, result: ExtractionResult) -> str:
        """Format statistics only."""
        pass
