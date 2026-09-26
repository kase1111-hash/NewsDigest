"""Speculation content stripper for NewsDigest."""

import re
from typing import Any

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory


# Modal verbs indicating speculation
MODAL_VERBS: list[str] = [
    "could",
    "might",
    "may",
    "would",
    "should",
]

# Hedging words and phrases
HEDGING_WORDS: list[str] = [
    "potentially",
    "possibly",
    "perhaps",
    "apparently",
    "seemingly",
    "reportedly",
    "allegedly",
    "supposedly",
    "ostensibly",
    "presumably",
    "conceivably",
    "theoretically",
    "hypothetically",
]

# Uncertainty phrases
UNCERTAINTY_PHRASES: list[str] = [
    r"it appears",
    r"it seems",
    r"is thought to",
    r"is believed to",
    r"is expected to",
    r"is likely to",
    r"is set to",
    r"is poised to",
    r"could potentially",
    r"might possibly",
    r"may perhaps",
    r"remains to be seen",
    r"time will tell",
    r"only time will tell",
    r"it remains unclear",
    r"it'?s unclear",
    r"it'?s not clear",
    r"it'?s uncertain",
    r"questions remain",
    r"raises questions",
    r"raises concerns",
    r"some say",
    r"some believe",
    r"some think",
    r"many believe",
    r"many think",
    r"observers say",
    r"observers believe",
    r"analysts say",
    r"analysts believe",
    r"analysts suggest",
    r"experts? (?:say|says|suggest|suggests|believe|believes)",
    r"would appear",
]

# Future speculation
FUTURE_SPECULATION: list[str] = [
    r"is expected to",
    r"are expected to",
    r"will likely",
    r"will probably",
    r"is likely to",
    r"are likely to",
    r"is set to",
    r"are set to",
    r"is poised to",
    r"are poised to",
    r"is slated to",
    r"are slated to",
    r"could lead to",
    r"might result in",
    r"may cause",
    r"could mean",
    r"might mean",
    r"may indicate",
    r"could signal",
    r"might signal",
]


class SpeculationStripper(BaseAnalyzer):
    """Detects and removes speculative content.

    Identifies sentences heavy with:
    - Modal verbs (could, might, may)
    - Hedging words (potentially, possibly, perhaps)
    - Uncertainty phrases (it appears, it seems)
    - Future speculation (is expected to, will likely)

    Scoring:
    - Counts speculation markers
    - Weights by position (end-of-sentence speculation scores higher)
    - Threshold: >2 markers = flag/remove depending on mode
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize speculation stripper."""
        super().__init__(config)
        self._uncertainty_patterns = [
            re.compile(p, re.IGNORECASE) for p in UNCERTAINTY_PHRASES
        ]
        self._future_patterns = [
            re.compile(p, re.IGNORECASE) for p in FUTURE_SPECULATION
        ]
        self.max_hedges = self.config.get("max_hedges_per_sentence", 2)
        self.speculation_threshold = self.config.get("speculation_threshold", 0.5)
        self.mode = self.config.get("mode", "remove")  # keep, flag, remove

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for speculation.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with speculation scored and flagged.
        """
        if not self.enabled:
            return sentences

        for sentence in sentences:
            # Skip already marked sentences
            if not sentence.keep:
                continue

            score, marker_count = self._score_speculation(sentence)
            sentence.speculation_score = score

            # Mark as speculation if above threshold
            if score >= self.speculation_threshold or marker_count > self.max_hedges:
                sentence.category = SentenceCategory.SPECULATION

                if self.mode == "remove":
                    sentence.keep = False
                    sentence.removal_reason = RemovalReason.SPECULATION.value

        return sentences

    def _score_speculation(self, sentence: Sentence) -> tuple[float, int]:
        """Calculate speculation score for a sentence.

        Args:
            sentence: Sentence to score.

        Returns:
            Tuple of (speculation_score 0.0-1.0, marker_count).
        """
        # Patterns use straight apostrophes; web text often has curly ones
        text = sentence.text.lower().replace("\u2019", "'")
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 0.0, 0

        marker_count = 0
        weighted_score = 0.0

        # Check modal verbs
        for i, word in enumerate(words):
            # Strip punctuation for comparison
            clean_word = word.strip(".,!?;:'\"")
            if clean_word in MODAL_VERBS:
                marker_count += 1
                # Higher weight if near end of sentence
                position = i / word_count
                weight = 1.0 + (position * 0.5)  # Up to 1.5x at end
                weighted_score += weight

        # Check hedging words
        for hedge in HEDGING_WORDS:
            if hedge in text:
                marker_count += 1
                weighted_score += 1.2

        # Check uncertainty phrases (higher weight)
        for pattern in self._uncertainty_patterns:
            if pattern.search(text):
                marker_count += 1
                weighted_score += 1.5

        # Check future speculation
        for pattern in self._future_patterns:
            if pattern.search(text):
                marker_count += 1
                weighted_score += 1.3

        # Normalize score to 0.0-1.0
        # A sentence with 3+ markers at 1.5 weight each = 4.5 raw score
        # Normalize so that ~4.5 = 1.0
        normalized_score = min(1.0, weighted_score / 4.5)

        return round(normalized_score, 2), marker_count

    def get_speculation_markers(self, sentence: Sentence) -> list[str]:
        """Get list of speculation markers found in sentence.

        Args:
            sentence: Sentence to check.

        Returns:
            List of found speculation markers.
        """
        text = sentence.text.lower().replace("\u2019", "'")
        words = text.split()
        markers = []

        # Check modal verbs
        for word in words:
            clean_word = word.strip(".,!?;:'\"")
            if clean_word in MODAL_VERBS:
                markers.append(clean_word)

        # Check hedging words
        markers.extend(hedge for hedge in HEDGING_WORDS if hedge in text)

        # Check uncertainty phrases
        for pattern in self._uncertainty_patterns:
            match = pattern.search(text)
            if match:
                markers.append(match.group())

        # Check future speculation
        for pattern in self._future_patterns:
            match = pattern.search(text)
            if match:
                markers.append(match.group())

        return markers
