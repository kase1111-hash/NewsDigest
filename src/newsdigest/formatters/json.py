"""JSON formatter for NewsDigest."""

import json
from datetime import datetime
from typing import Any

from newsdigest.core.result import ExtractionResult
from newsdigest.formatters.base import BaseFormatter


class JSONFormatter(BaseFormatter):
    """Formats output as JSON.

    Provides structured JSON output matching the API response format.
    """

    def __init__(self, config: dict | None = None) -> None:
        """Initialize JSON formatter.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.indent = self.config.get("indent", 2)
        self.include_removed = self.config.get("include_removed", False)
        self.include_sentences = self.config.get("include_sentences", False)

    def format_result(self, result: ExtractionResult) -> str:
        """Format a single extraction result as JSON.

        Args:
            result: ExtractionResult object.

        Returns:
            JSON string.
        """
        data = self._result_to_dict(result)
        return json.dumps(data, indent=self.indent, default=self._json_serializer)

    def _result_to_dict(self, result: ExtractionResult) -> dict[str, Any]:
        """Convert ExtractionResult to dictionary.

        Args:
            result: ExtractionResult object.

        Returns:
            Dictionary representation.
        """
        data: dict[str, Any] = {
            "id": result.id,
            "url": result.url,
            "title": result.title,
            "source": result.source,
            "published": result.published_at.isoformat()
            if result.published_at
            else None,
            "processed": result.processed_at.isoformat()
            if result.processed_at
            else None,
            "extracted": {
                "text": result.text,
                "claims": [
                    {
                        "text": c.text,
                        "type": c.claim_type.value,
                        "source": c.source,
                        "confidence": c.confidence,
                    }
                    for c in result.claims
                ],
            },
            "sources_named": result.sources_named,
            "statistics": {
                "original_words": result.statistics.original_words,
                "compressed_words": result.statistics.compressed_words,
                "compression_ratio": result.statistics.compression_ratio,
                "original_density": result.statistics.original_density,
                "compressed_density": result.statistics.compressed_density,
                "novel_claims": result.statistics.novel_claims,
                "named_sources": result.statistics.named_sources,
                "unnamed_sources": result.statistics.unnamed_sources,
                "emotional_words_removed": result.statistics.emotional_words_removed,
                "speculation_sentences_removed": result.statistics.speculation_removed,
                "repeated_sentences_collapsed": result.statistics.repetition_collapsed,
            },
            "warnings": result.warnings,
        }

        if self.include_removed:
            data["removed"] = [
                {
                    "text": r.text,
                    "reason": r.reason.value,
                    "sentence_index": r.sentence_index,
                }
                for r in result.removed
            ]

        if self.include_sentences:
            data["sentences"] = [
                {
                    "text": s.text,
                    "index": s.index,
                    "keep": s.keep,
                    "category": s.category.value,
                    "removal_reason": s.removal_reason,
                    "scores": {
                        "density": s.density_score,
                        "novelty": s.novelty_score,
                        "speculation": s.speculation_score,
                        "emotional": s.emotional_score,
                    },
                }
                for s in result.sentences
            ]

        return data

    def format_stats(self, result: ExtractionResult) -> str:
        """Format statistics only as JSON.

        Args:
            result: ExtractionResult object.

        Returns:
            JSON string with stats.
        """
        stats = {
            "original_words": result.statistics.original_words,
            "compressed_words": result.statistics.compressed_words,
            "compression_ratio": result.statistics.compression_ratio,
            "original_density": result.statistics.original_density,
            "compressed_density": result.statistics.compressed_density,
            "breakdown": {
                "novel_claims": result.statistics.novel_claims,
                "named_sources": result.statistics.named_sources,
                "unnamed_sources": result.statistics.unnamed_sources,
                "emotional_words_removed": result.statistics.emotional_words_removed,
                "speculation_removed": result.statistics.speculation_removed,
                "repetition_collapsed": result.statistics.repetition_collapsed,
                "background_removed": result.statistics.background_removed,
            },
        }
        return json.dumps(stats, indent=self.indent)

    def format_comparison(self, result: ExtractionResult) -> str:
        """Format side-by-side comparison as JSON.

        Args:
            result: ExtractionResult with sentences.

        Returns:
            JSON string with comparison data.
        """
        comparison = {
            "title": result.title,
            "url": result.url,
            "sentences": [
                {
                    "text": s.text,
                    "kept": s.keep,
                    "reason": s.removal_reason,
                    "category": s.category.value,
                }
                for s in result.sentences
            ],
            "summary": {
                "total": len(result.sentences),
                "kept": sum(1 for s in result.sentences if s.keep),
                "removed": sum(1 for s in result.sentences if not s.keep),
            },
        }
        return json.dumps(comparison, indent=self.indent, default=self._json_serializer)

    def format_digest(self, digest: Any) -> str:
        """Format a complete digest as JSON.

        Args:
            digest: Digest object.

        Returns:
            JSON string.
        """
        data = {
            "generated_at": digest.generated_at.isoformat(),
            "period": digest.period,
            "sources_processed": digest.sources_processed,
            "articles_analyzed": digest.articles_analyzed,
            "topics": [
                {
                    "name": topic.name,
                    "emoji": topic.emoji,
                    "items": [
                        {
                            "id": item.id,
                            "summary": item.summary,
                            "article_count": item.article_count,
                            "sources": item.sources,
                            "urls": item.urls,
                            "topic": item.topic,
                            "compression": {
                                "original": item.original_words,
                                "compressed": item.compressed_words,
                            },
                        }
                        for item in topic.items
                    ],
                }
                for topic in digest.topics
            ],
            "meta_stats": {
                "total_words_processed": digest.total_original_words,
                "total_words_delivered": digest.total_compressed_words,
                "compression_ratio": (
                    1 - digest.total_compressed_words / digest.total_original_words
                    if digest.total_original_words > 0
                    else 0
                ),
                "emotional_removed": digest.emotional_removed,
                "speculation_stripped": digest.speculation_stripped,
                "duplicates_collapsed": digest.duplicates_collapsed,
                "unnamed_sources_flagged": digest.unnamed_sources_flagged,
            },
        }
        return json.dumps(data, indent=self.indent, default=self._json_serializer)

    def _json_serializer(self, obj: Any) -> Any:
        """Custom JSON serializer for non-standard types.

        Args:
            obj: Object to serialize.

        Returns:
            Serializable representation.
        """
        if isinstance(obj, datetime):
            return obj.isoformat()
        if hasattr(obj, "value"):
            # Enum
            return obj.value
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
