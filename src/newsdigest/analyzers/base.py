"""Base class for all semantic analyzers."""

from abc import ABC, abstractmethod
from typing import Any

from newsdigest.core.result import Sentence


class BaseAnalyzer(ABC):
    """Base class for all semantic analyzers.

    Each analyzer receives a list of Sentence objects, analyzes them,
    updates their properties (scores, flags), and returns the list.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """
        Initialize analyzer with configuration.

        Args:
            config: Analyzer-specific configuration dictionary.
        """
        self.config = config or {}

    @property
    def name(self) -> str:
        """Return the analyzer name."""
        return self.__class__.__name__

    @property
    def enabled(self) -> bool:
        """Check if analyzer is enabled in config."""
        enabled: bool = self.config.get("enabled", True)
        return enabled

    @abstractmethod
    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """
        Analyze sentences and update their properties.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list of Sentence objects with updated scores/flags.
        """
        pass
