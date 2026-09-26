"""Novelty scorer for NewsDigest."""

from collections import Counter
from typing import Any

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import Sentence


class NoveltyScorer(BaseAnalyzer):
    """Scores sentences by information novelty.

    Algorithm:
    1. Extract key entities and facts from each sentence
    2. Compare against earlier sentences in same article (internal novelty)
    3. Score based on new information introduced

    Higher novelty = sentence introduces new information
    Lower novelty = sentence repeats earlier content
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize novelty scorer."""
        super().__init__(config)
        self.min_novelty = self.config.get("min_novelty_score", 0.3)
        self.decay_factor = self.config.get("decay_factor", 0.9)

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for novelty.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with novelty scores.
        """
        if not self.enabled:
            return sentences

        if not sentences:
            return sentences

        # Track seen information
        seen_entities: set[str] = set()
        seen_terms: Counter[str] = Counter()

        for i, sentence in enumerate(sentences):
            if not sentence.keep:
                continue

            # Calculate novelty based on new information
            novelty = self._calculate_novelty(sentence, seen_entities, seen_terms, i)
            sentence.novelty_score = novelty

            # Update seen information
            self._update_seen(sentence, seen_entities, seen_terms)

        return sentences

    def _calculate_novelty(
        self,
        sentence: Sentence,
        seen_entities: set[str],
        seen_terms: Counter[str],
        position: int,
    ) -> float:
        """Calculate novelty score for a sentence.

        Args:
            sentence: Sentence to score.
            seen_entities: Previously seen entities.
            seen_terms: Previously seen terms with counts.
            position: Position in article.

        Returns:
            Novelty score 0.0-1.0.
        """
        text = sentence.text
        words = self._get_content_terms(text)

        if not words:
            return 0.5  # Neutral for empty

        # First sentence gets high novelty (establishes baseline)
        if position == 0:
            return 0.9

        # Check entity novelty
        entity_novelty = self._entity_novelty(sentence, seen_entities)

        # Check term novelty
        term_novelty = self._term_novelty(words, seen_terms)

        # Check for numbers (often novel information)
        has_numbers = any(c.isdigit() for c in text)
        number_bonus = 0.1 if has_numbers else 0

        # Check for quotes (usually novel)
        has_quotes = '"' in text or "'" in text
        quote_bonus = 0.1 if has_quotes else 0

        # Combine scores
        combined = (
            entity_novelty * 0.4 + term_novelty * 0.4 + number_bonus + quote_bonus
        )

        # Apply position decay (later sentences get small penalty)
        position_factor: float = self.decay_factor ** (position / 10)
        combined *= position_factor

        return round(min(1.0, max(0.0, combined)), 2)

    def _entity_novelty(self, sentence: Sentence, seen_entities: set[str]) -> float:
        """Calculate novelty based on entities.

        Args:
            sentence: Sentence to check.
            seen_entities: Previously seen entities.

        Returns:
            Entity novelty score.
        """
        if not sentence.entities:
            return 0.5  # Neutral if no entity info

        current_entities = set()
        for entity in sentence.entities:
            if isinstance(entity, dict):
                current_entities.add(entity.get("text", "").lower())
            else:
                current_entities.add(str(entity).lower())

        if not current_entities:
            return 0.5

        new_entities = current_entities - seen_entities
        novelty = len(new_entities) / len(current_entities)

        return novelty

    def _term_novelty(self, words: list[str], seen_terms: Counter[str]) -> float:
        """Calculate novelty based on terms.

        Args:
            words: Content words from sentence.
            seen_terms: Previously seen terms.

        Returns:
            Term novelty score.
        """
        if not words:
            return 0.5

        new_count: float = 0
        for word in words:
            if seen_terms[word] == 0:
                new_count += 1
            elif seen_terms[word] == 1:
                # Seen once before, partial novelty
                new_count += 0.5

        return new_count / len(words)

    def _get_content_terms(self, text: str) -> list[str]:
        """Extract content terms from text.

        Args:
            text: Text to process.

        Returns:
            List of content terms.
        """
        stop_words = {
            "the",
            "a",
            "an",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "must",
            "shall",
            "can",
            "to",
            "of",
            "in",
            "for",
            "on",
            "with",
            "at",
            "by",
            "from",
            "as",
            "into",
            "through",
            "during",
            "before",
            "after",
            "above",
            "below",
            "between",
            "under",
            "again",
            "further",
            "then",
            "once",
            "and",
            "but",
            "or",
            "nor",
            "so",
            "yet",
            "both",
            "either",
            "neither",
            "not",
            "only",
            "own",
            "same",
            "than",
            "too",
            "very",
            "just",
            "also",
            "that",
            "this",
            "these",
            "those",
            "it",
            "its",
            "they",
            "their",
            "them",
            "he",
            "she",
            "his",
            "her",
            "him",
            "we",
            "our",
            "us",
            "you",
            "your",
            "who",
            "which",
            "what",
            "when",
            "where",
            "why",
            "how",
            "said",
            "says",
            "told",
        }

        words = text.lower().split()
        terms = []
        for word in words:
            clean_word = word.strip(".,!?;:'\"()-[]")
            if clean_word and clean_word not in stop_words and len(clean_word) > 2:
                terms.append(clean_word)

        return terms

    def _update_seen(
        self,
        sentence: Sentence,
        seen_entities: set[str],
        seen_terms: Counter[str],
    ) -> None:
        """Update seen information with sentence content.

        Args:
            sentence: Sentence to add.
            seen_entities: Entities set to update.
            seen_terms: Terms counter to update.
        """
        # Add entities
        for entity in sentence.entities or []:
            if isinstance(entity, dict):
                seen_entities.add(entity.get("text", "").lower())
            else:
                seen_entities.add(str(entity).lower())

        # Add terms
        words = self._get_content_terms(sentence.text)
        seen_terms.update(words)
