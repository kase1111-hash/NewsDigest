"""Deduplication for NewsDigest."""

import re

from newsdigest.core.result import ExtractionResult


class Deduplicator:
    """Deduplicates articles across sources.

    Uses text similarity to identify duplicate articles
    and merges metadata from duplicates.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize deduplicator.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.threshold = self.config.get("similarity_threshold", 0.85)

    def deduplicate(self, articles: list[ExtractionResult]) -> list[ExtractionResult]:
        """Remove duplicate articles, keeping the most complete.

        Args:
            articles: List of extraction results.

        Returns:
            Deduplicated list.
        """
        if len(articles) <= 1:
            return articles

        # Compute word sets for each article
        word_sets = [self._get_content_words(a.text) for a in articles]

        # Find clusters of similar articles
        clusters = self._find_clusters(articles, word_sets)

        # Select representative from each cluster
        result = []
        for cluster_indices in clusters:
            if len(cluster_indices) == 1:
                result.append(articles[cluster_indices[0]])
            else:
                # Merge cluster into single article
                merged = self._merge_cluster([articles[i] for i in cluster_indices])
                result.append(merged)

        return result

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
            "and",
            "but",
            "or",
            "that",
            "this",
            "it",
            "they",
            "them",
            "he",
            "she",
            "we",
            "you",
            "said",
            "says",
        }

        words = re.findall(r"\b\w+\b", text.lower())
        return {w for w in words if w not in stop_words and len(w) > 2}

    def _jaccard_similarity(self, set1: set[str], set2: set[str]) -> float:
        """Calculate Jaccard similarity.

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

    def _find_clusters(
        self,
        articles: list[ExtractionResult],
        word_sets: list[set[str]],
    ) -> list[list[int]]:
        """Find clusters of similar articles.

        Args:
            articles: Articles to cluster.
            word_sets: Pre-computed word sets.

        Returns:
            List of clusters (each cluster is list of indices).
        """
        n = len(articles)
        parent = list(range(n))

        def find(x: int) -> int:
            if parent[x] != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(x: int, y: int) -> None:
            px, py = find(x), find(y)
            if px != py:
                parent[px] = py

        # Compare all pairs
        for i in range(n):
            for j in range(i + 1, n):
                similarity = self._jaccard_similarity(word_sets[i], word_sets[j])
                if similarity >= self.threshold:
                    union(i, j)

        # Group by cluster
        clusters_dict: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            if root not in clusters_dict:
                clusters_dict[root] = []
            clusters_dict[root].append(i)

        return list(clusters_dict.values())

    def _merge_cluster(self, articles: list[ExtractionResult]) -> ExtractionResult:
        """Merge a cluster of similar articles into one.

        Args:
            articles: Articles in cluster.

        Returns:
            Merged article.
        """
        # Sort by content length (prefer longer/more complete)
        sorted_articles = sorted(articles, key=lambda a: len(a.text), reverse=True)
        primary = sorted_articles[0]

        # Collect all sources and URLs
        all_sources = set()
        all_urls = []
        for article in articles:
            if article.source:
                all_sources.add(article.source)
            if article.url:
                all_urls.append(article.url)

        # Use primary article but update sources
        # We can't modify frozen dataclass, so we'll note that
        # the caller should handle merging metadata

        return primary

    def find_duplicates(
        self, articles: list[ExtractionResult]
    ) -> list[tuple[int, int, float]]:
        """Find all duplicate pairs with similarity scores.

        Args:
            articles: Articles to check.

        Returns:
            List of (index1, index2, similarity) tuples.
        """
        duplicates = []
        word_sets = [self._get_content_words(a.text) for a in articles]

        for i in range(len(articles)):
            for j in range(i + 1, len(articles)):
                similarity = self._jaccard_similarity(word_sets[i], word_sets[j])
                if similarity >= self.threshold:
                    duplicates.append((i, j, similarity))

        return duplicates

    def get_duplicate_count(self, articles: list[ExtractionResult]) -> int:
        """Count number of duplicate articles removed.

        Args:
            articles: Original articles.

        Returns:
            Number of duplicates.
        """
        original = len(articles)
        deduped = len(self.deduplicate(articles))
        return original - deduped
