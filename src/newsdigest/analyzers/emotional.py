"""Emotional language detector for NewsDigest."""


from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory
from newsdigest.utils.text import (
    has_excessive_punctuation,
    has_meaningful_content,
    is_all_caps,
    remove_words,
    strip_punctuation,
)


# Emotional activation words
EMOTIONAL_ACTIVATION: set[str] = {
    "shocking",
    "stunning",
    "alarming",
    "unprecedented",
    "bombshell",
    "explosive",
    "devastating",
    "terrifying",
    "outrageous",
    "scandalous",
    "horrifying",
    "incredible",
    "unbelievable",
    "jaw-dropping",
    "mind-blowing",
    "earth-shattering",
    "groundbreaking",
    "game-changing",
    "revolutionary",
    "historic",
    "monumental",
    "seismic",
    "dramatic",
    "remarkable",
    "extraordinary",
    "sensational",
    "staggering",
    "astonishing",
    "astounding",
    "breathtaking",
    "phenomenal",
    "spectacular",
}

# Superlatives and hyperbole
SUPERLATIVES: set[str] = {
    "biggest",
    "largest",
    "worst",
    "best",
    "greatest",
    "highest",
    "lowest",
    "most",
    "least",
    "first-ever",
    "never-before-seen",
    "once-in-a-lifetime",
    "record-breaking",
    "all-time",
    "ultimate",
    "absolute",
    "complete",
    "total",
    "utter",
    "sheer",
}

# Urgency words
URGENCY_WORDS: set[str] = {
    "breaking",
    "urgent",
    "critical",
    "emergency",
    "must-read",
    "must-see",
    "don't miss",
    "alert",
    "warning",
    "crisis",
    "developing",
    "just in",
    "exclusive",
    "special report",
}

# Fear/anger words
FEAR_ANGER_WORDS: set[str] = {
    "terrifying",
    "frightening",
    "scary",
    "horrific",
    "nightmare",
    "catastrophic",
    "disastrous",
    "devastating",
    "chaotic",
    "violent",
    "brutal",
    "savage",
    "vicious",
    "cruel",
    "sinister",
    "dangerous",
    "threatening",
    "menacing",
    "ominous",
    "dire",
    "grim",
    "bleak",
    "doom",
    "gloom",
    "fury",
    "rage",
    "outrage",
    "wrath",
    "anger",
}


class EmotionalDetector(BaseAnalyzer):
    """Detects emotional activation language.

    Identifies and optionally removes:
    - Emotional activation words (shocking, stunning, alarming)
    - Superlatives and hyperbole (biggest, worst, unprecedented)
    - Urgency words (breaking, urgent, critical)
    - Fear/anger words designed to provoke emotional response

    Behavior:
    - Can remove words from sentence while keeping factual content
    - Tracks count of removed words for statistics
    - If sentence becomes empty after removal, marks as filler
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize emotional detector."""
        super().__init__(config)
        self.mode = self.config.get("mode", "remove")  # keep, flag, remove
        self.threshold = self.config.get("emotional_threshold", 0.3)
        self.track_superlatives = self.config.get("track_superlatives", True)

        # Build combined word set
        self._emotional_words = EMOTIONAL_ACTIVATION | FEAR_ANGER_WORDS
        if self.track_superlatives:
            self._emotional_words |= SUPERLATIVES
        self._urgency_words = URGENCY_WORDS

        # Stats tracking
        self.words_removed = 0

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for emotional language.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with emotional content scored and flagged.
        """
        if not self.enabled:
            return sentences

        self.words_removed = 0

        for sentence in sentences:
            # Skip already marked sentences
            if not sentence.keep:
                continue

            score, emotional_words = self._score_emotional(sentence)
            sentence.emotional_score = score

            if score >= self.threshold:
                sentence.category = SentenceCategory.EMOTIONAL

                if self.mode == "remove" and emotional_words:
                    # Remove emotional words but keep factual content
                    # Filter out markers like [CAPS], [PUNCTUATION]
                    # FIXME: Words with trailing punctuation (e.g. "shocking!")
                    # fail to match \b regex anchors in remove_words — strip
                    # punctuation from tokens before passing to remove_words
                    words_to_remove = [w for w in emotional_words if not w.startswith("[")]
                    cleaned_text = remove_words(sentence.text, words_to_remove)
                    self.words_removed += len(words_to_remove)

                    # Check if anything meaningful remains (uses shared utility)
                    if not has_meaningful_content(cleaned_text, min_content_words=2):
                        sentence.keep = False
                        sentence.removal_reason = (
                            RemovalReason.EMOTIONAL_ACTIVATION.value
                        )
                    else:
                        # Update sentence with cleaned text
                        sentence.text = cleaned_text

        return sentences

    def _score_emotional(self, sentence: Sentence) -> tuple[float, list[str]]:
        """Calculate emotional score for a sentence.

        Args:
            sentence: Sentence to score.

        Returns:
            Tuple of (emotional_score 0.0-1.0, list of emotional words found).
        """
        text = sentence.text.lower()
        words = text.split()
        word_count = len(words)

        if word_count == 0:
            return 0.0, []

        emotional_found = []

        # Check individual words (using shared strip_punctuation utility)
        for word in words:
            clean_word = strip_punctuation(word).lower()
            if clean_word in self._emotional_words:
                emotional_found.append(word)

        # Check urgency phrases
        emotional_found.extend(urgency for urgency in self._urgency_words if urgency in text)

        # Check for ALL CAPS (using shared utility)
        if is_all_caps(sentence.text, threshold=0.3):
            emotional_found.append("[CAPS]")

        # Check for excessive punctuation (using shared utility)
        if has_excessive_punctuation(sentence.text):
            emotional_found.append("[PUNCTUATION]")

        # Calculate score
        # Base: ratio of emotional words to total words
        emotional_count = len(
            [w for w in emotional_found if not w.startswith("[")]
        )
        base_score = emotional_count / word_count if word_count > 0 else 0

        # Bonus for caps and punctuation
        bonus = 0.1 if "[CAPS]" in emotional_found else 0
        bonus += 0.1 if "[PUNCTUATION]" in emotional_found else 0

        total_score = min(1.0, base_score * 3 + bonus)  # Scale up base score

        return round(total_score, 2), emotional_found

    def get_emotional_word_count(self) -> int:
        """Get count of emotional words removed.

        Returns:
            Number of words removed.
        """
        return self.words_removed
