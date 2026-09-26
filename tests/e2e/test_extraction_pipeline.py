"""End-to-end tests for the extraction pipeline.

Tests the complete flow from raw text/article to compressed output.
"""

import json

import pytest

from newsdigest.config.settings import Config
from newsdigest.core.article import Article, SourceType
from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult
from newsdigest.formatters import JSONFormatter, MarkdownFormatter, TextFormatter


class TestExtractionPipeline:
    """End-to-end tests for the extraction pipeline."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create an extractor instance."""
        config = Config()
        return Extractor(config)

    @pytest.fixture
    def news_article_text(self) -> str:
        """Sample news article with various content types."""
        return """
        In a shocking development that has left experts stunned, the Federal
        Reserve announced today that it would hold interest rates steady at
        5.25 percent.

        Fed Chair Jerome Powell stated in a press conference, "The decision
        was unanimous among committee members. We believe current rates are
        appropriate given economic conditions."

        Sources familiar with the matter suggest that more rate cuts could
        potentially come later this year, though officials have not confirmed
        this speculation.

        The announcement sent shockwaves through financial markets. Here's
        what you need to know about the decision and its implications.

        Analysts say this might signal a shift in monetary policy. The move
        could potentially affect mortgage rates and consumer borrowing costs.

        The decision comes after months of debate within the Fed about the
        appropriate pace of rate adjustments. Previous statements had hinted
        at possible changes.

        Stay tuned for more updates on this developing story.
        """

    @pytest.fixture
    def factual_article_text(self) -> str:
        """Article with mostly factual content."""
        return """
        Apple Inc. reported quarterly revenue of $89.5 billion for Q4 2024.

        CEO Tim Cook said during the earnings call, "iPhone sales exceeded
        our expectations, particularly in emerging markets."

        The company's services division generated $22.3 billion in revenue,
        up 14% from the previous year.

        Apple announced a $90 billion share buyback program and increased
        its quarterly dividend to $0.25 per share.
        """

    def test_basic_extraction(self, extractor: Extractor, news_article_text: str):
        """Test basic text extraction produces valid result."""
        result = extractor.extract_text(news_article_text)

        assert isinstance(result, ExtractionResult)
        assert result.id is not None
        assert result.text is not None
        assert len(result.text) > 0
        assert result.statistics is not None

    def test_compression_ratio(self, extractor: Extractor, news_article_text: str):
        """Test that extraction achieves meaningful compression."""
        result = extractor.extract_text(news_article_text)

        # Should achieve significant compression
        assert result.statistics.original_words > 0
        assert result.statistics.compressed_words > 0
        assert result.statistics.compression_ratio > 0.3  # At least 30% compression

    def test_removes_emotional_language(
        self, extractor: Extractor, news_article_text: str
    ):
        """Test that emotional language is removed."""
        result = extractor.extract_text(news_article_text)

        # Check that emotional words were removed
        assert result.statistics.emotional_words_removed > 0

        # Output should not contain emotional language
        output_lower = result.text.lower()
        emotional_words = ["shocking", "stunned", "shockwaves", "stunning"]
        for word in emotional_words:
            assert word not in output_lower, f"Emotional word '{word}' not removed"

    def test_removes_speculation(self, extractor: Extractor, news_article_text: str):
        """Test that speculative content is removed or flagged."""
        result = extractor.extract_text(news_article_text)

        # Check that speculation was identified
        assert result.statistics.speculation_removed > 0

    def test_preserves_quotes(self, extractor: Extractor, news_article_text: str):
        """Test that direct quotes are preserved."""
        result = extractor.extract_text(news_article_text)

        # Powell's quote should be preserved or represented
        # The quote content should appear in the output
        assert "unanimous" in result.text.lower() or any(
            "unanimous" in claim.text.lower() for claim in result.claims
        )

    def test_extracts_claims(self, extractor: Extractor, factual_article_text: str):
        """Test that factual claims are extracted."""
        result = extractor.extract_text(factual_article_text)

        # Should extract claims
        assert len(result.claims) > 0

        # Claims should contain factual information
        claim_texts = " ".join(c.text.lower() for c in result.claims)
        assert "billion" in claim_texts or "89.5" in claim_texts

    def test_identifies_sources(self, extractor: Extractor, news_article_text: str):
        """Test that named sources are identified."""
        result = extractor.extract_text(news_article_text)

        # Should identify named sources
        assert result.statistics.named_sources > 0 or len(result.sources_named) > 0

    def test_flags_unnamed_sources(self, extractor: Extractor, news_article_text: str):
        """Test that unnamed sources are flagged."""
        result = extractor.extract_text(news_article_text)

        # Should flag "Sources familiar with the matter"
        assert result.statistics.unnamed_sources > 0

    def test_sentence_categorization(
        self, extractor: Extractor, news_article_text: str
    ):
        """Test that sentences are properly categorized."""
        result = extractor.extract_text(news_article_text)

        # Should have sentences
        assert len(result.sentences) > 0

        # Should have different categories
        categories = {s.category for s in result.sentences}
        assert len(categories) > 1  # More than one category

    def test_removes_filler_content(self, extractor: Extractor, news_article_text: str):
        """Test that filler content is removed."""
        result = extractor.extract_text(news_article_text)

        # Filler phrases should be removed
        filler_phrases = [
            "here's what you need to know",
            "stay tuned",
            "developing story",
        ]

        output_lower = result.text.lower()
        for phrase in filler_phrases:
            assert phrase not in output_lower, f"Filler '{phrase}' not removed"

    def test_article_extraction(self, extractor: Extractor):
        """Test extraction from Article object."""
        article = Article(
            id="test-001",
            content="The company reported $50 million in revenue. CEO John Smith "
            "said, 'We exceeded expectations.' Analysts might expect growth.",
            url="https://example.com/news",
            title="Company Reports Strong Quarter",
            source_name="Business News",
            source_type=SourceType.URL,
        )

        result = extractor._process_article(article)

        assert result.id == "test-001"
        assert result.url == "https://example.com/news"
        assert result.title == "Company Reports Strong Quarter"
        assert result.source == "Business News"


class TestFormatters:
    """Test output formatters work with extraction results."""

    @pytest.fixture
    def extraction_result(self) -> ExtractionResult:
        """Create a sample extraction result."""
        from newsdigest.core.result import (
            Claim,
            ClaimType,
            ExtractionStatistics,
            RemovalReason,
            RemovedContent,
        )

        return ExtractionResult(
            id="test-001",
            url="https://example.com/article",
            title="Test Article",
            source="Test Source",
            text="The Federal Reserve held rates at 5.25%. Powell confirmed the decision.",
            claims=[
                Claim(
                    text="Federal Reserve held rates at 5.25%",
                    claim_type=ClaimType.FACTUAL,
                    confidence=0.95,
                ),
            ],
            sources_named=["Federal Reserve", "Jerome Powell"],
            removed=[
                RemovedContent(
                    text="In a shocking development",
                    reason=RemovalReason.EMOTIONAL_ACTIVATION,
                    sentence_index=0,
                ),
            ],
            statistics=ExtractionStatistics(
                original_words=100,
                compressed_words=15,
                compression_ratio=0.85,
                emotional_words_removed=3,
                speculation_removed=2,
            ),
        )

    def test_json_formatter(self, extraction_result: ExtractionResult):
        """Test JSON formatter produces valid output."""
        formatter = JSONFormatter()
        output = formatter.format_result(extraction_result)

        assert isinstance(output, str)
        assert len(output) > 0

        # Should be valid JSON
        data = json.loads(output)
        assert data["extracted"]["text"] == extraction_result.text

    def test_markdown_formatter(self, extraction_result: ExtractionResult):
        """Test Markdown formatter produces valid output."""
        formatter = MarkdownFormatter()
        output = formatter.format_result(extraction_result)

        assert isinstance(output, str)
        assert len(output) > 0

        # Should contain markdown elements
        assert "#" in output or "**" in output or "-" in output

    def test_text_formatter(self, extraction_result: ExtractionResult):
        """Test text formatter produces valid output."""
        formatter = TextFormatter()
        output = formatter.format_result(extraction_result)

        assert isinstance(output, str)
        assert len(output) > 0

        # Should contain the extracted text
        assert "5.25" in output or "rate" in output.lower()


class TestExtractionModes:
    """Test different extraction modes."""

    @pytest.fixture
    def mixed_content(self) -> str:
        """Content with mix of factual and noise."""
        return """
        In an absolutely stunning and unprecedented move, Company X reported
        quarterly revenue of $1.2 billion. CEO Jane Doe said, "We're pleased
        with results."

        Sources suggest profits could potentially double next year, though
        this remains speculative. The shocking announcement surprised analysts.

        Stay tuned for more updates on this developing story.
        """

    def test_conservative_mode(self, mixed_content: str):
        """Test conservative extraction keeps more content."""
        config = Config()
        config.extraction.mode = "conservative"
        extractor = Extractor(config)

        result = extractor.extract_text(mixed_content)

        # Conservative should keep more
        assert result.statistics.compression_ratio < 0.7

    def test_standard_mode(self, mixed_content: str):
        """Test standard extraction is balanced."""
        config = Config()
        config.extraction.mode = "standard"
        extractor = Extractor(config)

        result = extractor.extract_text(mixed_content)

        # Standard should be moderate
        assert 0.3 < result.statistics.compression_ratio < 0.9

    def test_aggressive_mode(self, mixed_content: str):
        """Test aggressive extraction removes more."""
        config = Config()
        config.extraction.mode = "aggressive"
        extractor = Extractor(config)

        result = extractor.extract_text(mixed_content)

        # Aggressive should compress more
        assert result.statistics.compression_ratio > 0.5
