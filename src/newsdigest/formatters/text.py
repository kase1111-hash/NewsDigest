"""Plain text formatter for NewsDigest."""

from typing import Any

from newsdigest.core.result import ExtractionResult
from newsdigest.formatters.base import BaseFormatter


class TextFormatter(BaseFormatter):
    """Formats output as plain text.

    Provides clean, readable text output without Markdown formatting.
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize text formatter.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.show_stats = self.config.get("show_stats", True)
        self.show_warnings = self.config.get("show_warnings", True)
        self.width = self.config.get("width", 80)

    def format_result(self, result: ExtractionResult) -> str:
        """Format a single extraction result as text.

        Args:
            result: ExtractionResult object.

        Returns:
            Formatted text string.
        """
        lines = []

        # Header
        lines.append("=" * self.width)
        if result.title:
            lines.append(f"ARTICLE: {result.title}")
        if result.source:
            lines.append(f"SOURCE: {result.source}")
        if result.published_at:
            lines.append(f"DATE: {result.published_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * self.width)
        lines.append("")

        # Extracted content
        lines.append("EXTRACTED CONTENT:")
        lines.append("-" * 40)
        lines.append("")
        lines.append(result.text)
        lines.append("")

        # Claims
        if result.claims:
            lines.append("KEY CLAIMS:")
            lines.append("-" * 40)
            for i, claim in enumerate(result.claims, 1):
                source_info = f" (Source: {claim.source})" if claim.source else ""
                lines.append(f"{i}. {claim.text}{source_info}")
            lines.append("")

        # Warnings
        if self.show_warnings and result.warnings:
            lines.append("WARNINGS:")
            lines.append("-" * 40)
            lines.extend(
                f"- {warning.get('type', 'Warning')}: {warning.get('text', '')}"
                for warning in result.warnings
            )
            lines.append("")

        # Statistics
        if self.show_stats:
            lines.append(self.format_stats(result))

        lines.append("=" * self.width)

        return "\n".join(lines)

    def format_stats(self, result: ExtractionResult) -> str:
        """Format statistics only.

        Args:
            result: ExtractionResult object.

        Returns:
            Formatted statistics string.
        """
        stats = result.statistics
        lines = []

        lines.append("STATISTICS:")
        lines.append("-" * 40)
        lines.append(f"  Original length:     {stats.original_words} words")
        lines.append(f"  Compressed length:   {stats.compressed_words} words")

        if stats.original_words > 0:
            ratio = (1 - stats.compressed_words / stats.original_words) * 100
            lines.append(f"  Compression ratio:   {ratio:.1f}%")

        lines.append(
            f"  Semantic density:    {stats.original_density:.2f} -> {stats.compressed_density:.2f}"
        )
        lines.append("")

        lines.append("  Breakdown:")
        lines.append(f"    Novel claims:      {stats.novel_claims}")
        lines.append(f"    Named sources:     {stats.named_sources}")
        lines.append(f"    Unnamed sources:   {stats.unnamed_sources}")
        lines.append(f"    Emotional words:   {stats.emotional_words_removed} removed")
        lines.append(
            f"    Speculation:       {stats.speculation_removed} sentences removed"
        )
        lines.append(f"    Repetition:        {stats.repetition_collapsed} collapsed")
        lines.append("")

        return "\n".join(lines)

    def format_comparison(self, result: ExtractionResult) -> str:
        """Format side-by-side comparison.

        Args:
            result: ExtractionResult with sentences.

        Returns:
            Formatted comparison string.
        """
        lines = []

        lines.append("=" * self.width)
        lines.append("EXTRACTION COMPARISON")
        lines.append("=" * self.width)
        lines.append("")

        if result.title:
            lines.append(f"Article: {result.title}")
            lines.append("")

        for i, sentence in enumerate(result.sentences):
            lines.append(f"[{i + 1}] {sentence.text[:60]}...")

            if sentence.keep:
                lines.append("    -> KEPT")
            else:
                reason = sentence.removal_reason or "REMOVED"
                lines.append(f"    -> REMOVED ({reason})")

            lines.append("")

        # Summary
        kept = sum(1 for s in result.sentences if s.keep)
        removed = sum(1 for s in result.sentences if not s.keep)
        lines.append("-" * 40)
        lines.append(
            f"Summary: {kept} kept, {removed} removed out of {len(result.sentences)} sentences"
        )
        lines.append("=" * self.width)

        return "\n".join(lines)

    def format_digest(self, digest: Any) -> str:
        """Format a complete digest.

        Args:
            digest: Digest object.

        Returns:
            Formatted digest string.
        """
        lines = []

        # Header
        lines.append("=" * self.width)
        lines.append("NEWS DIGEST")
        lines.append(f"Generated: {digest.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Period: {digest.period}")
        lines.append("=" * self.width)
        lines.append("")

        # Topics
        for topic in digest.topics:
            lines.append(f"[{topic.name.upper()}]")
            lines.append("-" * 40)

            for item in topic.items:
                lines.append(f"* {item.summary}")
                if item.sources:
                    lines.append(f"  Sources: {', '.join(item.sources)}")
                if item.article_count > 1:
                    lines.append(f"  ({item.article_count} articles)")
                lines.append("")

        # Footer stats
        lines.append("-" * 40)
        lines.append("DIGEST STATISTICS:")
        lines.append(f"  Sources processed:   {digest.sources_processed}")
        lines.append(f"  Articles analyzed:   {digest.articles_analyzed}")
        lines.append(f"  Words processed:     {digest.total_original_words:,}")
        lines.append(f"  Words delivered:     {digest.total_compressed_words:,}")
        lines.append(f"  Emotional removed:   {digest.emotional_removed}")
        lines.append(f"  Speculation removed: {digest.speculation_stripped}")
        lines.append(f"  Duplicates merged:   {digest.duplicates_collapsed}")
        lines.append("=" * self.width)

        return "\n".join(lines)
