"""Repetition collapser for NewsDigest."""

from newsdigest.analyzers.base import BaseAnalyzer
from newsdigest.core.result import RemovalReason, Sentence


class RepetitionCollapser(BaseAnalyzer):
    """Detects and collapses repeated information.

    Algorithm:
    1. Compute similarity between sentences using word overlap (Jaccard)
    2. Identify clusters of similar sentences
    3. Keep first occurrence in each cluster
    4. Mark subsequent occurrences for removal

    Also handles:
    - Repeated factoids across paragraphs
    - Background information restated multiple times
    - Similar claims with slight rewording
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize repetition collapser."""
        super().__init__(config)
        self.similarity_threshold = self.config.get("similarity_threshold", 0.7)
        self.min_sentence_length = self.config.get("min_sentence_length", 5)

        # Stats
        self.collapsed_count = 0

    def analyze(self, sentences: list[Sentence]) -> list[Sentence]:
        """Analyze sentences for repetition.

        Args:
            sentences: List of Sentence objects to analyze.

        Returns:
            Modified list with repeated sentences marked.
        """
        if not self.enabled:
            return sentences

        self.collapsed_count = 0

        # Get indices of sentences that are still active (keep=True)
        active_indices = [
            i
            for i, s in enumerate(sentences)
            if s.keep and len(s.text.split()) >= self.min_sentence_length
        ]

        if len(active_indices) < 2:
            return sentences

        # Find clusters of similar sentences
        clusters = self._find_similar_clusters(sentences, active_indices)

        # Mark all but first in each cluster for removal
        for cluster in clusters:
            if len(cluster) > 1:
                # Sort to get first occurrence
                cluster_sorted = sorted(cluster)
                # Mark all but first for removal
                for idx in cluster_sorted[1:]:
                    sentences[idx].keep = False
                    sentences[
                        idx
                    ].removal_reason = RemovalReason.BACKGROUND_REPEAT.value
                    self.collapsed_count += 1

        return sentences

    def _find_similar_clusters(
        self, sentences: list[Sentence], active_indices: list[int]
    ) -> list[set[int]]:
        """Find clusters of similar sentences.

        Args:
            sentences: All sentences.
            active_indices: Indices of active sentences.

        Returns:
            List of sets of similar sentence indices.
        """
        # Compute word sets for each active sentence
        word_sets: dict[int, set[str]] = {}
        for idx in active_indices:
            word_sets[idx] = self._get_content_words(sentences[idx].text)

        # Build similarity graph
        similar_pairs: list[tuple[int, int]] = []
        for i, idx1 in enumerate(active_indices):
            for idx2 in active_indices[i + 1 :]:
                similarity = self._jaccard_similarity(word_sets[idx1], word_sets[idx2])
                if similarity >= self.similarity_threshold:
                    similar_pairs.append((idx1, idx2))

        # Build clusters using union-find
        clusters = self._build_clusters(similar_pairs, active_indices)

        # Filter to only clusters with more than one member
        return [c for c in clusters if len(c) > 1]

    def _get_content_words(self, text: str) -> set[str]:
        """Extract content words from text.

        Args:
            text: Text to process.

        Returns:
            Set of lowercase content words.
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
            "all",
            "each",
            "every",
            "any",
            "some",
            "no",
            "more",
            "most",
            "other",
            "such",
            "about",
        }

        words = text.lower().split()
        # Remove punctuation and filter stop words
        content_words = set()
        for word in words:
            clean_word = word.strip(".,!?;:'\"()-[]")
            if clean_word and clean_word not in stop_words and len(clean_word) > 2:
                content_words.add(clean_word)

        return content_words

    def _jaccard_similarity(self, set1: set[str], set2: set[str]) -> float:
        """Calculate Jaccard similarity between two sets.

        Args:
            set1: First set.
            set2: Second set.

        Returns:
            Similarity score 0.0-1.0.
        """
        if not set1 or not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        return intersection / union if union > 0 else 0.0

    def _build_clusters(
        self, pairs: list[tuple[int, int]], all_indices: list[int]
    ) -> list[set[int]]:
        """Build clusters from pairs using union-find.

        Args:
            pairs: List of similar sentence pairs.
            all_indices: All active sentence indices.

        Returns:
            List of cluster sets.
        """
        # Initialize parent for union-find
        parent: dict[int, int] = {idx: idx for idx in all_indices}

        def find(x: int) -> int:
            # Iterative with path halving: long runs of near-identical
            # sentences build deep chains that overflow a recursive find.
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Union similar pairs
        for idx1, idx2 in pairs:
            union(idx1, idx2)

        # Group by root
        clusters_dict: dict[int, set[int]] = {}
        for idx in all_indices:
            root = find(idx)
            if root not in clusters_dict:
                clusters_dict[root] = set()
            clusters_dict[root].add(idx)

        return list(clusters_dict.values())

    def get_collapsed_count(self) -> int:
        """Get count of collapsed repetitions.

        Returns:
            Number of sentences collapsed.
        """
        return self.collapsed_count
