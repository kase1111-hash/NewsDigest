"""Filler content detector for NewsDigest."""

import re
from typing import Any

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory


# Engagement hooks and filler patterns
ENGAGEMENT_HOOKS: list[str] = [
    r"here'?s what you need to know",
    r"what happened next will surprise you",
    r"but that'?s not the whole story",
    r"^but that'?s not all\b",
    r"stay tuned for more",
    r"we'?ll keep you posted",
    r"you won'?t believe",
    r"what this means for you",
    r"the real story behind",
    r"everything you need to know",
    r"here'?s why that matters",
    r"here'?s the bottom line",
    r"the takeaway",
    r"let'?s dive in",
    r"read on to find out",
    r"keep reading",
    r"scroll down",
    r"click here",
    r"don'?t miss",
    r"must[- ]read",
    r"what we know so far",
    r"developing story",
    r"more details to come",
    r"this is a breaking",
    r"breaking news",
]

# Low-information transitional phrases
TRANSITIONAL_FILLER: list[str] = [
    r"^meanwhile,?$",
    r"^however,?$",
    r"^furthermore,?$",
    r"^additionally,?$",
    r"^in addition,?$",
    r"^on the other hand,?$",
    r"^that said,?$",
    r"^having said that,?$",
    r"^at the end of the day,?$",
    r"^when all is said and done,?$",
    r"^it goes without saying",
    r"^needless to say",
    r"^as we all know",
    r"^it'?s worth noting",
    r"^it should be noted",
    r"^interestingly enough",
    r"^as you might expect",
]


class FillerDetector(BaseAnalyzer):
    """Detects sentences with no information content.

    Identifies:
    - Engagement hooks designed to drive clicks/reads
    - Low-information transitional phrases
    - Sentences with low entity density
    - Very short sentences with no substantive content
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize filler detector."""
        super().__init__(config)
        self._engagement_patterns = [
            re.compile(p, re.IGNORECASE) for p in ENGAGEMENT_HOOKS
        ]
        self._transitional_patterns = [
            re.compile(p, re.IGNORECASE) for p in TRANSITIONAL_FILLER
        ]
        self.min_word_count = self.config.get("min_word_count", 4)
        self.min_entity_density = self.config.get("min_entity_density", 0.1)

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for filler content.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with filler sentences flagged.
        """
        if not self.enabled:
            return sentences

        for sentence in sentences:
            # Skip already marked sentences
            if not sentence.keep:
                continue

            is_filler, reason = self._is_filler(sentence)
            if is_filler:
                sentence.keep = False
                sentence.category = SentenceCategory.FILLER
                sentence.removal_reason = reason

        return sentences

    def _is_filler(self, sentence: Sentence) -> tuple[bool, str | None]:
        """Check if a sentence is filler content.

        Args:
            sentence: Sentence to check.

        Returns:
            Tuple of (is_filler, reason).
        """
        text = sentence.text.strip()
        # Patterns use straight apostrophes; web text often has curly ones
        text_lower = text.lower().replace("\u2019", "'")

        # Check engagement hooks
        for pattern in self._engagement_patterns:
            if pattern.search(text_lower):
                return True, RemovalReason.ENGAGEMENT_HOOK.value

        # Check transitional filler (entire sentence is just a transition)
        for pattern in self._transitional_patterns:
            if pattern.fullmatch(text_lower):
                return True, RemovalReason.LOW_DENSITY.value

        # Check for very short sentences with no entities
        words = text.split()
        # Allow short sentences with entities or quotes
        if (
            len(words) < self.min_word_count
            and not sentence.entities
            and '"' not in text
            and "'" not in text
        ):
            return True, RemovalReason.LOW_DENSITY.value

        # Check entity density for longer sentences
        if len(words) >= 10:
            entity_count = len(sentence.entities) if sentence.entities else 0
            density = entity_count / len(words)
            if density < self.min_entity_density and sentence.density_score < 0.2:
                # Only mark as low density if also lacking other content indicators
                has_numbers = any(c.isdigit() for c in text)
                has_quotes = '"' in text or "'" in text
                if not has_numbers and not has_quotes:
                    return True, RemovalReason.LOW_DENSITY.value

        return False, None

    def get_engagement_hook_count(self, sentences: list[Sentence]) -> int:
        """Count engagement hooks in sentences.

        Args:
            sentences: List of sentences to check.

        Returns:
            Number of engagement hooks found.
        """
        count = 0
        for sentence in sentences:
            text_lower = sentence.text.lower().replace("\u2019", "'")
            for pattern in self._engagement_patterns:
                if pattern.search(text_lower):
                    count += 1
                    break
        return count
