"""Emotional language detector for NewsDigest."""

import re

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory
from newsdigest.utils.text import (
    fix_punctuation_spacing,
    has_excessive_punctuation,
    has_meaningful_content,
    is_all_caps,
    normalize_whitespace,
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


# Reported reactions: they describe how people felt, not what happened
EMOTIONAL_REACTIONS: set[str] = {
    "shocked",
    "stunned",
    "alarmed",
    "terrified",
    "shockwave",
    "shockwaves",
}

# Idioms whose only content is the reaction ("sent shockwaves through markets")
EMOTIONAL_IDIOMS: list[str] = [
    r"\b(?:sends?|sent|sending)\s+shock\s?waves\b",
    r"\bleft\s+(?:\w+\s+){0,2}(?:stunned|shocked|reeling|speechless|alarmed)\b",
    r"\bsen[dt]\w*\s+(?:\w+\s+){0,2}(?:reeling|into\s+a\s+(?:panic|frenzy|tailspin))\b",
    r"\bcaught\s+(?:\w+\s+){0,2}off[\s-]guard\b",
]

# Placeholder left where a word was removed, so the surrounding grammar
# ("a"/"an", "X and Y") can be repaired before it is collapsed
_REMOVED = "\x00"

# Direct quotes are reproduced verbatim, never edited
_QUOTED_SPAN = re.compile('("[^"]*"|\u201c[^\u201d]*\u201d)')

# Introductory clause before the first comma: "In a shocking move, ..."
_LEAD_CLAUSE = re.compile(
    r"^(?P<lead>[^,\"\u201c\u201d]{3,160}),\s+(?P<rest>\S.*)$", re.DOTALL
)
MAX_LEAD_CLAUSE_WORDS = 15


class EmotionalDetector(BaseAnalyzer):
    """Detects emotional activation language.

    Identifies and optionally removes:
    - Emotional activation words (shocking, stunning, alarming)
    - Superlatives and hyperbole (biggest, worst, unprecedented)
    - Urgency words (breaking, urgent, critical)
    - Fear/anger words designed to provoke emotional response

    Behavior (in "remove" mode):
    - Sensational adjectives ("shocking", "stunning") are always stripped
    - Sentences scoring above the threshold lose all emotional words
    - Sensational lead-in clauses ("In a shocking development, ...") are
      dropped when the rest of the sentence stands on its own
    - Sentences that only report a reaction are removed
    - Direct quotes are never edited
    - Tracks count of removed words for statistics
    - If nothing meaningful remains after removal, the sentence is removed
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize emotional detector."""
        super().__init__(config)
        self.mode = self.config.get("mode", "remove")  # keep, flag, remove
        self.threshold = self.config.get("emotional_threshold", 0.3)
        self.track_superlatives = self.config.get("track_superlatives", True)

        # Build combined word set
        self._emotional_words = (
            EMOTIONAL_ACTIVATION | FEAR_ANGER_WORDS | EMOTIONAL_REACTIONS
        )
        self._lead_words = EMOTIONAL_ACTIVATION | EMOTIONAL_REACTIONS
        self._idiom_patterns = [re.compile(p, re.IGNORECASE) for p in EMOTIONAL_IDIOMS]
        if self.track_superlatives:
            self._emotional_words |= SUPERLATIVES
        # Words that can be cut without breaking the sentence: not reactions
        # (usually verbs) and not idioms (whole phrases)
        self._removable_words = (
            self._emotional_words - EMOTIONAL_REACTIONS
        ) | URGENCY_WORDS
        self._urgency_patterns = [
            (word, re.compile(rf"\b{re.escape(word)}\b")) for word in URGENCY_WORDS
        ]

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
            is_emotional = score >= self.threshold

            if is_emotional:
                sentence.category = SentenceCategory.EMOTIONAL

            if self.mode == "remove" and emotional_words:
                self._remove_emotional_content(sentence, emotional_words, is_emotional)

        return sentences

    def _remove_emotional_content(
        self, sentence: Sentence, emotional_words: list[str], is_emotional: bool
    ) -> None:
        """Strip emotional language from a sentence, or drop the sentence.

        Args:
            sentence: Sentence to clean (modified in place).
            emotional_words: Emotional words found by _score_emotional.
            is_emotional: Whether the sentence scored above the threshold.
        """
        text, removed = self._strip_emotional_lead(sentence.text)

        # Nothing but a reaction, or strongly emotional with no facts at all
        strongly_emotional = sentence.emotional_score >= 2 * self.threshold
        if self._is_reaction_only(text) or (
            strongly_emotional and not self._has_facts(text, sentence)
        ):
            found = [w for w in emotional_words if not w.startswith("[")]
            self.words_removed += max(1, removed, len(found))
            sentence.keep = False
            sentence.removal_reason = RemovalReason.EMOTIONAL_ACTIVATION.value
            return

        # Below the threshold only sensational adjectives go; markers like
        # [CAPS] / [PUNCTUATION] are never in the removable set
        candidates = [
            w
            for w in emotional_words
            if w in self._removable_words
            and (is_emotional or w in EMOTIONAL_ACTIVATION)
        ]
        words_to_remove = [
            w for w in candidates if not self._is_named_entity_word(sentence, w)
        ]
        text, count = self._remove_words(text, words_to_remove)
        removed += count

        if removed == 0:
            return
        self.words_removed += removed

        # Check if anything meaningful remains (uses shared utility)
        if not has_meaningful_content(text, min_content_words=2):
            sentence.keep = False
            sentence.removal_reason = RemovalReason.EMOTIONAL_ACTIVATION.value
        else:
            sentence.text = text

    def _strip_emotional_lead(self, text: str) -> tuple[str, int]:
        """Drop a sensational introductory clause.

        "In a shocking development, the Fed held rates." becomes
        "The Fed held rates." The clause is kept if it carries facts
        (numbers, proper nouns) or the remainder cannot stand alone.

        Args:
            text: Sentence text.

        Returns:
            Tuple of (text, number of emotional words removed).
        """
        match = _LEAD_CLAUSE.match(text)
        if not match:
            return text, 0

        lead, rest = match.group("lead"), match.group("rest")
        lead_words = lead.split()
        if len(lead_words) > MAX_LEAD_CLAUSE_WORDS or any(c.isdigit() for c in lead):
            return text, 0
        # Title-case words after the first are likely names worth keeping
        if any(w[:1].isupper() and not w.isupper() for w in lead_words[1:]):
            return text, 0

        hits = sum(
            1 for w in lead_words if strip_punctuation(w).lower() in self._lead_words
        )
        hits += sum(1 for p in self._idiom_patterns if p.search(lead))
        if hits == 0 or not has_meaningful_content(rest, min_content_words=3):
            return text, 0

        return rest[0].upper() + rest[1:], hits

    def _is_reaction_only(self, text: str) -> bool:
        """Check if a sentence only reports an emotional reaction.

        Args:
            text: Sentence text.

        Returns:
            True if an emotional idiom is present and no facts are.
        """
        if not any(p.search(text) for p in self._idiom_patterns):
            return False
        return not (any(c.isdigit() for c in text) or _QUOTED_SPAN.search(text))

    @staticmethod
    def _has_facts(text: str, sentence: Sentence) -> bool:
        """Check if a sentence carries checkable information.

        Args:
            text: Current sentence text.
            sentence: Sentence with NLP annotations.

        Returns:
            True if it has numbers, a direct quote or a named entity.
        """
        return bool(
            any(c.isdigit() for c in text)
            or _QUOTED_SPAN.search(text)
            or sentence.entities
        )

    @staticmethod
    def _is_named_entity_word(sentence: Sentence, word: str) -> bool:
        """Check if a word is part of a name ("Revolutionary Guard").

        Args:
            sentence: Sentence containing the word.
            word: Lowercase word.

        Returns:
            True if the word belongs to a named entity.
        """
        return any(
            re.search(rf"\b{re.escape(word)}\b", ent.get("text", ""), re.IGNORECASE)
            for ent in sentence.entities
        )

    @staticmethod
    def _remove_words(text: str, words: list[str]) -> tuple[str, int]:
        """Remove words outside direct quotes, repairing the grammar around them.

        Args:
            text: Sentence text.
            words: Lowercase words or phrases to remove.

        Returns:
            Tuple of (cleaned text, number of occurrences removed).
        """
        if not words:
            return text, 0

        removed = 0
        segments = _QUOTED_SPAN.split(text)
        # Even indices are outside quotes, odd indices are quoted spans
        for i in range(0, len(segments), 2):
            segment = segments[i]
            for word in set(words):
                segment, n = re.subn(
                    rf"\b{re.escape(word)}\b", _REMOVED, segment, flags=re.IGNORECASE
                )
                removed += n
            if _REMOVED not in segment:
                continue
            # "a shocking and unprecedented rise" -> one gap, not "and" alone
            segment = re.sub(
                rf"{_REMOVED}(?:\s*(?:,|\band\b|\bor\b)\s*{_REMOVED})+",
                _REMOVED,
                segment,
                flags=re.IGNORECASE,
            )
            # "an unprecedented rise" -> "a rise"
            segment = re.sub(
                rf"\b(an?)\s+{_REMOVED}\s*(?=(\w))",
                _fix_article,
                segment,
                flags=re.IGNORECASE,
            )
            segments[i] = segment.replace(_REMOVED, " ")

        if removed == 0:
            return text, 0

        cleaned = fix_punctuation_spacing(normalize_whitespace("".join(segments)))
        cleaned = re.sub(r"^[\s,;:]+", "", cleaned)
        if text[:1].isupper() and cleaned[:1].islower():
            cleaned = cleaned[0].upper() + cleaned[1:]
        return cleaned, removed

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

        # Check individual words (using shared strip_punctuation utility).
        # Record the bare word: removal matches on word boundaries, which
        # a token with trailing punctuation ("shocking,") never satisfies.
        for word in words:
            clean_word = strip_punctuation(word).lower()
            if clean_word in self._emotional_words:
                emotional_found.append(clean_word)

        # Check urgency phrases as whole words ("alert" but not "alerted")
        emotional_found.extend(
            urgency
            for urgency, pattern in self._urgency_patterns
            if pattern.search(text)
        )

        # Check reaction idioms ("sent shockwaves", "caught off guard")
        for pattern in self._idiom_patterns:
            match = pattern.search(text)
            if match:
                emotional_found.append(match.group().lower())

        # Check for ALL CAPS (using shared utility)
        if is_all_caps(sentence.text, threshold=0.3):
            emotional_found.append("[CAPS]")

        # Check for excessive punctuation (using shared utility)
        if has_excessive_punctuation(sentence.text):
            emotional_found.append("[PUNCTUATION]")

        # Calculate score
        # Base: ratio of emotional words to total words
        emotional_count = len([w for w in emotional_found if not w.startswith("[")])
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


def _fix_article(match: re.Match[str]) -> str:
    """Choose "a" or "an" for the word that now follows the article."""
    article = "an" if match.group(2).lower() in "aeiou" else "a"
    if match.group(1)[0].isupper():
        article = article.capitalize()
    return f"{article} "
