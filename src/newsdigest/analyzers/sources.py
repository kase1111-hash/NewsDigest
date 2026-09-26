"""Source validator for NewsDigest."""

import re

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence


# Patterns for named source attribution
NAMED_SOURCE_PATTERNS: list[str] = [
    # Direct attribution: "said John Smith"
    r"(?:said|says|told|tells|stated|announced|confirmed|denied|claimed|reported)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    # Title attribution: "CEO John Smith said"
    r"(?:CEO|CFO|CTO|COO|President|Chairman|Director|Secretary|Minister|Senator|Representative|Governor|Mayor|Chief|Professor|Dr\.|Mr\.|Mrs\.|Ms\.)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(?:said|says|told|stated)",
    # According to Name
    r"according to\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)",
    # Name, title, said
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+),\s+(?:a|an|the)?\s*(?:\w+\s+)*(?:at|of|for|with)\s+[\w\s]+,?\s+(?:said|says|told|stated)",
    # Organization announced/said
    r"(?:the\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\s+(?:announced|said|stated|reported|confirmed|denied)",
]

# Patterns for unnamed sources (flag these)
UNNAMED_SOURCE_PATTERNS: list[str] = [
    r"sources?\s+(?:say|said|indicate|suggest|claim|report)",
    r"sources?\s+familiar\s+with",
    r"sources?\s+close\s+to",
    r"sources?\s+within",
    r"sources?\s+inside",
    r"according\s+to\s+sources?",
    r"officials?\s+(?:say|said|who\s+spoke)",
    r"experts?\s+(?:say|said|believe|think)",
    r"people\s+(?:familiar|close|briefed)",
    r"(?:a|an)\s+(?:person|official|source)\s+who",
    r"those\s+with\s+knowledge",
    r"insiders?\s+(?:say|said)",
    r"someone\s+(?:familiar|close)",
    r"(?:an?\s+)?(?:senior|administration|government|company|industry)\s+official",
    r"speaking\s+(?:on\s+)?(?:condition\s+of\s+)?(?:anonymity|background)",
    r"who\s+(?:spoke|asked|declined)\s+(?:on\s+)?(?:condition\s+of\s+)?(?:anonymity|not\s+to\s+be\s+(?:named|identified))",
    r"(?:would|could)\s+not\s+be\s+(?:named|identified)",
    r"requested\s+anonymity",
]


class SourceValidator(BaseAnalyzer):
    """Validates and extracts source attribution.

    Identifies:
    - Named sources with proper attribution
    - Unnamed/anonymous sources (flag or remove)
    - Organizations as sources
    - Quote attributions

    Can operate in different modes:
    - 'keep': Keep all sources, just annotate
    - 'flag': Keep but add warnings for unnamed sources
    - 'remove': Remove sentences with only unnamed sources
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize source validator."""
        super().__init__(config)
        self._named_patterns = [
            re.compile(p, re.IGNORECASE) for p in NAMED_SOURCE_PATTERNS
        ]
        self._unnamed_patterns = [
            re.compile(p, re.IGNORECASE) for p in UNNAMED_SOURCE_PATTERNS
        ]
        self.mode = self.config.get("unnamed_sources", "flag")  # keep, flag, remove

        # Stats
        self.named_sources: list[str] = []
        self.unnamed_source_count = 0

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for source attribution.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with source information annotated.
        """
        if not self.enabled:
            return sentences

        self.named_sources = []
        self.unnamed_source_count = 0

        for sentence in sentences:
            # Skip already marked sentences
            if not sentence.keep:
                continue

            # Check for named sources
            named = self._find_named_sources(sentence.text)
            if named:
                sentence.has_named_source = True
                sentence.source_name = named[0]  # Primary source
                self.named_sources.extend(named)

            # Check for unnamed sources
            has_unnamed = self._has_unnamed_source(sentence.text)
            if has_unnamed:
                sentence.has_unnamed_source = True
                self.unnamed_source_count += 1

                if self.mode == "remove" and not sentence.has_named_source:
                    # Only remove if no named source in sentence
                    sentence.keep = False
                    sentence.removal_reason = RemovalReason.UNNAMED_SOURCE.value

        return sentences

    def _find_named_sources(self, text: str) -> list[str]:
        """Find named sources in text.

        Args:
            text: Text to search.

        Returns:
            List of found named sources.
        """
        sources = []
        for pattern in self._named_patterns:
            matches = pattern.finditer(text)
            for match in matches:
                if match.groups():
                    source = match.group(1).strip()
                    # Filter out common false positives
                    if self._is_valid_source_name(source):
                        sources.append(source)

        return list(set(sources))  # Remove duplicates

    def _is_valid_source_name(self, name: str) -> bool:
        """Check if a name is a valid source name.

        Args:
            name: Name to validate.

        Returns:
            True if valid source name.
        """
        # Filter out common false positives
        false_positives = {
            "The",
            "A",
            "An",
            "This",
            "That",
            "These",
            "Those",
            "It",
            "He",
            "She",
            "They",
            "We",
            "I",
            "You",
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        }

        name_clean = name.strip()
        if name_clean in false_positives:
            return False

        # Must have at least 2 characters
        if len(name_clean) < 2:
            return False

        # Should start with capital letter
        return name_clean[0].isupper()

    def _has_unnamed_source(self, text: str) -> bool:
        """Check if text references unnamed sources.

        Args:
            text: Text to check.

        Returns:
            True if unnamed source reference found.
        """
        text_lower = text.lower()
        return any(pattern.search(text_lower) for pattern in self._unnamed_patterns)

    def get_source_warnings(self, sentences: list[Sentence]) -> list[dict]:
        """Generate warnings for unnamed sources.

        Args:
            sentences: Analyzed sentences.

        Returns:
            List of warning dictionaries.
        """
        warnings = []
        for i, sentence in enumerate(sentences):
            if sentence.has_unnamed_source:
                warnings.append(
                    {
                        "type": "UNNAMED_SOURCE",
                        "text": sentence.text[:100] + "..."
                        if len(sentence.text) > 100
                        else sentence.text,
                        "location": f"sentence {i + 1}",
                    }
                )
        return warnings

    def get_unique_named_sources(self) -> list[str]:
        """Get list of unique named sources found.

        Returns:
            List of unique source names.
        """
        return list(set(self.named_sources))

    def get_unnamed_source_count(self) -> int:
        """Get count of unnamed source references.

        Returns:
            Number of unnamed source references.
        """
        return self.unnamed_source_count
