"""Quote isolator for NewsDigest."""

import re

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory


# Attribution patterns
ATTRIBUTION_PATTERNS: list[str] = [
    r'(?:said|says|told|stated|announced|declared|claimed|reported|confirmed|denied|acknowledged|admitted|argued|asserted|wrote|explained|added|warned)\s+(?:that\s+)?["\']',
    r'["\'][^"\']+["\'],?\s+(?:said|says|told|stated|announced|declared|claimed)',
    r'according\s+to\s+[^,]+,?\s+["\']',
    r'["\'][^"\']+["\'],?\s+according\s+to',
]


class QuoteIsolator(BaseAnalyzer):
    """Separates direct quotes from paraphrase.

    Identifies quote types:
    - Informative quote: adds new information (keep)
    - Circular quote: restates what was just reported (remove)
    - Attribution quote: identifies a source (keep)

    Detection:
    - Quotation marks
    - Attribution verbs
    - Paraphrase patterns
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize quote isolator."""
        super().__init__(config)
        self._attribution_patterns = [
            re.compile(p, re.IGNORECASE) for p in ATTRIBUTION_PATTERNS
        ]
        self.keep_attributed = self.config.get("keep_attributed", True)
        self.keep_unattributed = self.config.get("keep_unattributed", False)
        self.flag_circular = self.config.get("flag_circular", True)

        # Stats
        self.informative_quotes = 0
        self.circular_quotes = 0
        self.unattributed_quotes = 0

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for quotes.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with quotes classified.
        """
        if not self.enabled:
            return sentences

        self.informative_quotes = 0
        self.circular_quotes = 0
        self.unattributed_quotes = 0

        # Track context for circular quote detection
        recent_content: list[str] = []

        for sentence in sentences:
            if not sentence.keep:
                continue

            quote_info = self._analyze_quote(sentence, recent_content)

            if quote_info:
                quote_type, is_attributed = quote_info
                sentence.category = SentenceCategory.QUOTE

                if quote_type == "circular":
                    self.circular_quotes += 1
                    if self.flag_circular:
                        sentence.keep = False
                        sentence.removal_reason = RemovalReason.CIRCULAR_QUOTE.value
                elif quote_type == "informative":
                    self.informative_quotes += 1
                    if not is_attributed and not self.keep_unattributed:
                        sentence.keep = False
                        sentence.removal_reason = RemovalReason.CIRCULAR_QUOTE.value
                        self.unattributed_quotes += 1
                else:
                    # Unattributed
                    self.unattributed_quotes += 1
                    if not self.keep_unattributed:
                        sentence.keep = False
                        sentence.removal_reason = RemovalReason.CIRCULAR_QUOTE.value

            # Update recent content for context
            if sentence.keep:
                recent_content.append(sentence.text.lower())
                if len(recent_content) > 5:  # Keep last 5 sentences
                    recent_content.pop(0)

        return sentences

    def _analyze_quote(
        self, sentence: Sentence, recent_content: list[str]
    ) -> tuple[str, bool] | None:
        """Analyze a potential quote sentence.

        Args:
            sentence: Sentence to analyze.
            recent_content: Recent preceding content for context.

        Returns:
            Tuple of (quote_type, is_attributed) or None if not a quote.
        """
        text = sentence.text

        # Check if sentence contains a quote
        if not self._has_quote(text):
            return None

        # Check if attributed
        is_attributed = self._is_attributed(text) or sentence.has_named_source

        # Extract quoted content
        quoted = self._extract_quoted_content(text)
        if not quoted:
            return None

        # Check if circular (repeats recent content)
        is_circular = self._is_circular(quoted, recent_content)

        if is_circular:
            return ("circular", is_attributed)
        elif is_attributed:
            return ("informative", True)
        else:
            return ("unattributed", False)

    def _has_quote(self, text: str) -> bool:
        """Check if text contains a quote.

        Args:
            text: Text to check.

        Returns:
            True if quote found.
        """
        # Check for quotation marks
        if '"' in text or "\u201c" in text or "\u201d" in text:
            return True

        # Check for single quotes used as quote marks
        return bool(re.search(r"'[^']{10,}'", text))  # At least 10 chars in quotes

    def _is_attributed(self, text: str) -> bool:
        """Check if quote is attributed.

        Args:
            text: Text to check.

        Returns:
            True if attribution found.
        """
        if any(pattern.search(text) for pattern in self._attribution_patterns):
            return True

        # Also check for simple attribution verbs near quotes
        attribution_verbs = [
            "said", "says", "told", "stated", "announced", "declared",
            "claimed", "reported", "confirmed", "denied", "added", "wrote",
        ]
        text_lower = text.lower()
        return any(verb in text_lower for verb in attribution_verbs)

    def _extract_quoted_content(self, text: str) -> str | None:
        """Extract quoted content from text.

        Args:
            text: Text to process.

        Returns:
            Quoted content or None.
        """
        # Try double quotes first
        match = re.search(r'"([^"]+)"', text)
        if match:
            return match.group(1).lower()

        # Try curly quotes
        match = re.search("\u201c([^\u201d]+)\u201d", text)
        if match:
            return match.group(1).lower()

        # Try single quotes
        match = re.search(r"'([^']{10,})'", text)
        if match:
            return match.group(1).lower()

        return None

    def _is_circular(self, quoted: str, recent_content: list[str]) -> bool:
        """Check if quote repeats recent content.

        Args:
            quoted: Quoted text (lowercase).
            recent_content: Recent sentences (lowercase).

        Returns:
            True if circular.
        """
        if not recent_content:
            return False

        quoted_words = set(self._get_content_words(quoted))
        if not quoted_words:
            return False

        for recent in recent_content:
            recent_words = set(self._get_content_words(recent))
            if not recent_words:
                continue

            # Check overlap
            overlap = len(quoted_words & recent_words)
            overlap_ratio = overlap / len(quoted_words)

            if overlap_ratio > 0.7:  # 70% overlap = circular
                return True

        return False

    def _get_content_words(self, text: str) -> list[str]:
        """Extract content words from text.

        Args:
            text: Text to process.

        Returns:
            List of content words.
        """
        stop_words = {
            "the", "a", "an", "is", "are", "was", "were", "be", "been",
            "have", "has", "had", "do", "does", "did", "will", "would",
            "could", "should", "to", "of", "in", "for", "on", "with", "at",
            "by", "from", "as", "and", "but", "or", "that", "this", "it",
            "they", "them", "he", "she", "we", "you", "said", "says",
        }

        words = text.lower().split()
        return [
            w.strip(".,!?;:'\"()-[]")
            for w in words
            if w.strip(".,!?;:'\"()-[]") not in stop_words
            and len(w.strip(".,!?;:'\"()-[]")) > 2
        ]

    def get_quote_stats(self) -> dict:
        """Get quote statistics.

        Returns:
            Dict with quote counts.
        """
        return {
            "informative": self.informative_quotes,
            "circular": self.circular_quotes,
            "unattributed": self.unattributed_quotes,
        }
