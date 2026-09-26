"""Markdown formatter for NewsDigest."""

from typing import Any

from newsdigest.core.result import ExtractionResult
from newsdigest.formatters.base import BaseFormatter


class MarkdownFormatter(BaseFormatter):
    """Formats output as Markdown.

    Provides formatted output for:
    - Single extraction results
    - Side-by-side comparisons
    - Digests with topics
    - Statistics
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize Markdown formatter.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self.show_stats = self.config.get("show_stats", True)
        self.include_links = self.config.get("include_links", True)
        self.show_warnings = self.config.get("show_warnings", True)

    def format_result(self, result: ExtractionResult) -> str:
        """Format a single extraction result.

        Args:
            result: ExtractionResult object.

        Returns:
            Formatted Markdown string.
        """
        lines = []

        # Header
        lines.append("━" * 60)
        if result.title:
            lines.append(f'ARTICLE: "{result.title}"')
        if result.source:
            lines.append(f"SOURCE:  {result.source}")
        if result.published_at:
            lines.append(f"DATE:    {result.published_at.strftime('%Y-%m-%d %H:%M')}")
        if result.url and self.include_links:
            lines.append(f"URL:     {result.url}")
        lines.append("━" * 60)
        lines.append("")

        # Extracted content
        lines.append("## EXTRACTED CONTENT")
        lines.append("─" * 40)
        lines.append("")
        lines.append(result.text)
        lines.append("")

        # Claims if any
        if result.claims:
            lines.append("## KEY CLAIMS")
            lines.append("─" * 40)
            for i, claim in enumerate(result.claims, 1):
                source_info = f" (Source: {claim.source})" if claim.source else ""
                lines.append(f"{i}. {claim.text}{source_info}")
            lines.append("")

        # Warnings
        if self.show_warnings and result.warnings:
            lines.append("## ⚠️ WARNINGS")
            lines.append("─" * 40)
            lines.extend(
                f"- **{warning.get('type', 'Warning')}**: {warning.get('text', '')}"
                for warning in result.warnings
            )
            lines.append("")

        # Statistics
        if self.show_stats:
            lines.append(self.format_stats(result))

        lines.append("━" * 60)

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

        lines.append("## STATISTICS")
        lines.append("─" * 40)
        lines.append(f"Original length:        {stats.original_words} words")
        lines.append(f"Compressed length:      {stats.compressed_words} words")

        if stats.original_words > 0:
            ratio = (1 - stats.compressed_words / stats.original_words) * 100
            lines.append(f"Compression ratio:      {ratio:.1f}%")

        lines.append(
            f"Semantic density:       {stats.original_density:.2f} → {stats.compressed_density:.2f}"
        )
        lines.append("")

        # Breakdown
        lines.append("### Breakdown")
        lines.append(f"- Novel claims:          {stats.novel_claims}")
        lines.append(f"- Named sources:         {stats.named_sources}")
        lines.append(f"- Unnamed sources:       {stats.unnamed_sources}")
        lines.append(
            f"- Emotional words:       {stats.emotional_words_removed} removed"
        )
        lines.append(
            f"- Speculation:           {stats.speculation_removed} sentences removed"
        )
        lines.append(f"- Repetition:            {stats.repetition_collapsed} collapsed")
        lines.append(f"- Background:            {stats.background_removed} removed")
        lines.append("")

        return "\n".join(lines)

    def format_comparison(self, result: ExtractionResult) -> str:
        """Format side-by-side comparison.

        Args:
            result: ExtractionResult with original_text and sentences.

        Returns:
            Formatted comparison string.
        """
        lines = []

        lines.append("━" * 60)
        lines.append("EXTRACTION COMPARISON")
        lines.append("━" * 60)
        lines.append("")

        if result.title:
            lines.append(f"**Article:** {result.title}")
            lines.append("")

        # Two-column comparison
        lines.append("| Original | Status | Extracted |")
        lines.append("|----------|--------|-----------|")

        for sentence in result.sentences:
            original = (
                sentence.text[:50] + "..." if len(sentence.text) > 50 else sentence.text
            )
            original = original.replace("|", "\\|").replace("\n", " ")

            if sentence.keep:
                status = "✓ KEPT"
                extracted = original
            else:
                status = f"✗ {sentence.removal_reason or 'REMOVED'}"
                extracted = "—"

            lines.append(f"| {original} | {status} | {extracted} |")

        lines.append("")

        # Summary
        kept = sum(1 for s in result.sentences if s.keep)
        removed = sum(1 for s in result.sentences if not s.keep)
        lines.append(
            f"**Summary:** {kept} kept, {removed} removed out of {len(result.sentences)} sentences"
        )
        lines.append("")

        lines.append("━" * 60)

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
        lines.append("━" * 60)
        lines.append("📰 NEWS DIGEST")
        lines.append(f"Generated: {digest.generated_at.strftime('%Y-%m-%d %H:%M')}")
        lines.append(f"Period: {digest.period}")
        lines.append("━" * 60)
        lines.append("")

        # Topics
        for topic in digest.topics:
            emoji = topic.emoji or "📌"
            lines.append(f"## {emoji} {topic.name}")
            lines.append("")

            for item in topic.items:
                lines.append(f"### {item.summary[:100]}...")
                if item.sources:
                    lines.append(f"*Sources: {', '.join(item.sources)}*")
                if item.article_count > 1:
                    lines.append(f"*({item.article_count} articles)*")
                lines.append("")

        # Footer stats
        lines.append("─" * 40)
        lines.append("### Digest Statistics")
        lines.append(f"- Sources processed: {digest.sources_processed}")
        lines.append(f"- Articles analyzed: {digest.articles_analyzed}")
        lines.append(f"- Total words processed: {digest.total_original_words:,}")
        lines.append(f"- Words delivered: {digest.total_compressed_words:,}")

        if digest.total_original_words > 0:
            ratio = (
                1 - digest.total_compressed_words / digest.total_original_words
            ) * 100
            lines.append(f"- Compression: {ratio:.1f}%")

        lines.append("")
        lines.append(f"- Emotional content removed: {digest.emotional_removed}")
        lines.append(f"- Speculation stripped: {digest.speculation_stripped}")
        lines.append(f"- Duplicates collapsed: {digest.duplicates_collapsed}")
        lines.append(f"- Unnamed sources flagged: {digest.unnamed_sources_flagged}")
        lines.append("")
        lines.append("━" * 60)

        return "\n".join(lines)
