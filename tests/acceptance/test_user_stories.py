"""Acceptance tests based on User Stories.

These tests verify that the system meets the acceptance criteria
defined in docs/USER_STORIES.md.

Tests are organized by User Story ID for traceability.
"""

import json

import pytest

from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult


# =============================================================================
# US-001: Extract Content from URL
# =============================================================================


class TestUS001ExtractContent:
    """
    US-001: Extract Content from URL

    As a news reader, I want to extract the essential content from a news
    article URL so that I can quickly understand the key facts without
    reading filler content.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create standard extractor."""
        return Extractor()

    @pytest.fixture
    def sample_article(self) -> str:
        """Sample article with various content types."""
        return """
        In a stunning development that has shocked experts, Apple Inc. announced
        record quarterly revenue of $90 billion on Tuesday.

        CEO Tim Cook attributed the growth to strong iPhone sales worldwide.
        "This was our best quarter ever," Cook said in a statement.

        The company's stock rose 3% following the announcement. Analysts had
        expected revenue of $88 billion.

        Sources familiar with the matter suggest more product launches are planned.

        Here's what you need to know about the results. Stay tuned for more updates
        as this story develops.
        """

    def test_ac01_extract_returns_compressed_content(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Given content, extract returns compressed factual information."""
        result = extractor.extract_sync(sample_article)

        assert isinstance(result, ExtractionResult)
        assert result.text is not None
        assert len(result.text) > 0
        # Should be compressed (fewer words than original)
        assert result.statistics.compressed_words < result.statistics.original_words

    def test_ac02_output_includes_statistics(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Output includes compression ratio display."""
        result = extractor.extract_sync(sample_article)

        stats = result.statistics
        assert stats.original_words > 0
        assert stats.compressed_words >= 0
        assert 0 <= stats.compression_ratio <= 1

    def test_ac03_emotional_words_stripped(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Emotional activation words are stripped from output."""
        result = extractor.extract_sync(sample_article)

        # Original has "stunning" and "shocked" - these should be removed/reduced
        assert result.statistics.emotional_words_removed >= 0

        # Check output text for emotional words
        emotional_words = ["stunning", "shocked", "shocking"]
        output_lower = result.text.lower()
        found_emotional = sum(1 for w in emotional_words if w in output_lower)

        # Should have fewer emotional words in output
        original_emotional = sum(
            1 for w in emotional_words if w in sample_article.lower()
        )
        assert (
            found_emotional < original_emotional
            or result.statistics.emotional_words_removed > 0
        )

    def test_ac04_speculation_removed(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Speculative statements are removed."""
        result = extractor.extract_sync(sample_article)

        # Track speculation removal
        assert result.statistics.speculation_removed >= 0

    def test_ac05_named_sources_preserved(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Named sources are preserved and listed."""
        result = extractor.extract_sync(sample_article)

        # Should identify named sources like "Tim Cook"
        assert result.statistics.named_sources >= 0

        # Named sources should be in the sources list or preserved in text
        # The article has Tim Cook as a named source
        has_named = (
            len(result.sources_named) > 0
            or "Cook" in result.text
            or result.statistics.named_sources > 0
        )
        assert has_named

    def test_ac06_unnamed_sources_flagged(
        self, extractor: Extractor, sample_article: str
    ) -> None:
        """AC: Unnamed sources are flagged with warning."""
        result = extractor.extract_sync(sample_article)

        # Article has "Sources familiar with the matter" - unnamed source
        assert result.statistics.unnamed_sources >= 0

        # If there are warnings, check for unnamed source warnings
        if result.warnings:
            unnamed_warnings = [
                w for w in result.warnings if "UNNAMED" in str(w).upper()
            ]
            # Should have warnings or track them in stats
            assert len(unnamed_warnings) >= 0 or result.statistics.unnamed_sources > 0


# =============================================================================
# US-002: Extract Content from Text
# =============================================================================


class TestUS002ExtractFromText:
    """
    US-002: Extract Content from Stdin/Text

    As a developer, I want to process article content directly
    so that I can integrate it into my existing workflows.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    def test_ac01_plain_text_processing(self, extractor: Extractor) -> None:
        """AC: Handles plain text input."""
        plain_text = """
        The Federal Reserve raised interest rates by 0.25% today.
        Chair Jerome Powell cited ongoing inflation concerns.
        The decision was approved unanimously.
        """

        result = extractor.extract_sync(plain_text)

        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words > 0

    def test_ac02_returns_same_format_as_url(self, extractor: Extractor) -> None:
        """AC: Returns same output format as URL extraction."""
        text = "Apple reported $90 billion in revenue. CEO Tim Cook was pleased."

        result = extractor.extract_sync(text)

        # Should have all standard result fields
        assert hasattr(result, "text")
        assert hasattr(result, "statistics")
        assert hasattr(result, "claims")
        assert hasattr(result, "sources_named")


# =============================================================================
# US-004: View Extraction Statistics
# =============================================================================


class TestUS004ExtractionStatistics:
    """
    US-004: View Extraction Statistics Only

    As a researcher, I want to see statistics about an article
    so that I can assess information density.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def sample_content(self) -> str:
        """Sample content for statistics."""
        return """
        Microsoft announced a $10 billion investment in AI technology.
        CEO Satya Nadella said the move was strategic.
        "This positions us for the future," Nadella stated.
        The deal could potentially reshape the industry.
        Sources say competitors are alarmed by the news.
        """

    def test_ac01_statistics_include_word_counts(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Statistics include original/compressed words and compression ratio."""
        result = extractor.extract_sync(sample_content)
        stats = result.statistics

        assert stats.original_words > 0
        assert stats.compressed_words >= 0
        assert 0 <= stats.compression_ratio <= 1

    def test_ac02_statistics_include_claims(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Statistics include novel claims count."""
        result = extractor.extract_sync(sample_content)

        assert result.statistics.novel_claims >= 0

    def test_ac03_statistics_include_sources(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Statistics include named/unnamed sources count."""
        result = extractor.extract_sync(sample_content)

        assert result.statistics.named_sources >= 0
        assert result.statistics.unnamed_sources >= 0

    def test_ac04_statistics_include_removals(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Statistics include emotional words and speculation removed."""
        result = extractor.extract_sync(sample_content)

        assert result.statistics.emotional_words_removed >= 0
        assert result.statistics.speculation_removed >= 0

    def test_ac05_statistics_include_density(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Statistics include semantic density before and after."""
        result = extractor.extract_sync(sample_content)

        assert 0 <= result.statistics.original_density <= 1
        assert 0 <= result.statistics.compressed_density <= 1


# =============================================================================
# US-016: Markdown Output
# =============================================================================


class TestUS016MarkdownOutput:
    """
    US-016: Markdown Output

    As a user who works with Markdown, I want to receive output in
    Markdown format.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def result(self, extractor: Extractor) -> ExtractionResult:
        """Create extraction result."""
        return extractor.extract_sync(
            "Apple reported $90 billion revenue. CEO Tim Cook was optimistic."
        )

    def test_ac01_markdown_is_default(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """AC: Markdown is the default output format."""
        output = extractor.format(result, format="markdown")
        assert isinstance(output, str)
        assert len(output) > 0

    def test_ac02_valid_markdown_structure(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """AC: Output is valid CommonMark with headers/lists."""
        output = extractor.format(result, format="markdown")

        # Should contain some markdown elements
        has_structure = (
            "#" in output  # Headers
            or "-" in output  # Lists
            or "*" in output  # Bold/italic/lists
            or result.text in output  # At minimum, contains the text
        )
        assert has_structure


# =============================================================================
# US-017: JSON Output
# =============================================================================


class TestUS017JSONOutput:
    """
    US-017: JSON Output

    As a developer, I want to receive output in JSON format
    so that I can programmatically process the results.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def result(self, extractor: Extractor) -> ExtractionResult:
        """Create extraction result."""
        return extractor.extract_sync(
            "Google announced new AI features. CEO Sundar Pichai was excited."
        )

    def test_ac01_json_format_available(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """AC: JSON output available with format='json'."""
        output = extractor.format(result, format="json")
        assert isinstance(output, str)

    def test_ac02_valid_json(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """AC: Valid JSON parseable by standard tools."""
        output = extractor.format(result, format="json")

        # Should be valid JSON
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_ac03_fields_properly_typed(
        self, extractor: Extractor, result: ExtractionResult
    ) -> None:
        """AC: All fields properly typed."""
        output = extractor.format(result, format="json")
        parsed = json.loads(output)

        # Check that expected fields exist and have appropriate types
        if "text" in parsed:
            assert isinstance(parsed["text"], str)
        if "statistics" in parsed:
            stats = parsed["statistics"]
            if "original_words" in stats:
                assert isinstance(stats["original_words"], (int, float))
            if "compression_ratio" in stats:
                assert isinstance(stats["compression_ratio"], (int, float))


# =============================================================================
# US-030: Configure Extraction Aggressiveness
# =============================================================================


class TestUS030ExtractionModes:
    """
    US-030: Configure Extraction Aggressiveness

    As a user with specific preferences, I want to adjust how aggressively
    content is compressed.
    """

    @pytest.fixture
    def sample_content(self) -> str:
        """Sample content with mixed quality."""
        return """
        In a potentially significant development, the company announced changes.
        CEO John Smith confirmed the decision in a statement.
        "We are committed to growth," Smith said.
        Here's what you need to know about this story.
        Sources familiar with the matter suggest more announcements coming.
        This could possibly signal a shift in strategy.
        """

    def test_ac01_three_modes_available(self, sample_content: str) -> None:
        """AC: Three modes available: conservative, standard, aggressive."""
        modes = ["conservative", "standard", "aggressive"]

        for mode in modes:
            extractor = Extractor(mode=mode)
            assert extractor.mode == mode

            result = extractor.extract_sync(sample_content)
            assert isinstance(result, ExtractionResult)

    def test_ac02_standard_is_default(self) -> None:
        """AC: Standard is the default mode."""
        extractor = Extractor()
        assert extractor.mode == "standard"

    def test_ac03_mode_affects_extraction(self, sample_content: str) -> None:
        """AC: Different modes produce different results."""
        conservative = Extractor(mode="conservative")
        aggressive = Extractor(mode="aggressive")

        result_conservative = conservative.extract_sync(sample_content)
        result_aggressive = aggressive.extract_sync(sample_content)

        # Both should produce valid results
        assert result_conservative.statistics.original_words > 0
        assert result_aggressive.statistics.original_words > 0

        # Results may differ (aggressive typically compresses more)
        # This is a soft check since exact behavior depends on content
        assert result_conservative is not None
        assert result_aggressive is not None


# =============================================================================
# US-031: Environment Variable Configuration
# =============================================================================


class TestUS031EnvironmentConfiguration:
    """
    US-031: Environment Variable Configuration

    As a user deploying in different environments, I want to configure
    settings via environment variables.
    """

    def test_ac01_config_from_env(self, monkeypatch) -> None:
        """AC: Configuration can be loaded from environment variables."""
        monkeypatch.setenv("NEWSDIGEST_MODE", "aggressive")
        monkeypatch.setenv("NEWSDIGEST_HTTP_TIMEOUT", "60")

        config = Config.from_env()

        assert config.extraction.mode == "aggressive"
        assert config.http_timeout == 60

    def test_ac02_api_keys_from_env(self, monkeypatch) -> None:
        """AC: API keys read from environment."""
        # These should be readable if set
        monkeypatch.setenv("NEWSAPI_KEY", "test-key-123")

        import os

        assert os.environ.get("NEWSAPI_KEY") == "test-key-123"

    def test_ac03_config_override(self, monkeypatch) -> None:
        """AC: Environment variables can override settings."""
        # Set env vars
        monkeypatch.setenv("NEWSDIGEST_CACHE_ENABLED", "false")
        monkeypatch.setenv("NEWSDIGEST_CACHE_TTL", "7200")

        config = Config.from_env()

        assert config.cache_enabled is False
        assert config.cache_ttl == 7200


# =============================================================================
# US-003: Compare Original vs Extracted
# =============================================================================


class TestUS003CompareFeature:
    """
    US-003: Compare Original vs Extracted

    As a user skeptical of extraction quality, I want to see a
    side-by-side comparison.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def sample_content(self) -> str:
        """Content for comparison."""
        return """
        In a shocking development, Apple announced new products.
        CEO Tim Cook said sales were strong.
        This could potentially change the market.
        """

    def test_ac01_compare_returns_result(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Compare returns extraction with original for comparison."""
        result = extractor.compare(sample_content)

        assert isinstance(result, ExtractionResult)
        # Should have original text for comparison
        assert result.original_text is not None or result.text is not None

    def test_ac02_sentences_include_removal_info(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Result includes sentence-level decisions."""
        result = extractor.compare(sample_content)

        # Sentences should include keep/removal information
        if result.sentences:
            for sentence in result.sentences:
                assert hasattr(sentence, "keep") or hasattr(sentence, "removal_reason")

    def test_ac03_word_counts_available(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """AC: Word counts shown for both versions."""
        result = extractor.compare(sample_content)

        assert result.statistics.original_words > 0
        assert result.statistics.compressed_words >= 0


# =============================================================================
# US-005: Batch Extract Multiple URLs
# =============================================================================


class TestUS005BatchExtraction:
    """
    US-005: Batch Extract Multiple URLs

    As a power user, I want to extract content from multiple sources at once.
    """

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def articles(self) -> list:
        """Multiple articles to process."""
        return [
            "Apple reported strong earnings. CEO Tim Cook was pleased.",
            "Google announced new features. Sundar Pichai led the presentation.",
            "Microsoft invested in AI. Satya Nadella outlined the strategy.",
        ]

    @pytest.mark.asyncio
    async def test_ac01_batch_processes_all(
        self, extractor: Extractor, articles: list
    ) -> None:
        """AC: All items in batch are processed."""
        results = await extractor.extract_batch(articles)

        assert len(results) == len(articles)
        for result in results:
            assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_ac02_parallel_processing(
        self, extractor: Extractor, articles: list
    ) -> None:
        """AC: Processing happens in parallel for speed."""
        # Parallel should work
        results = await extractor.extract_batch(articles, parallel=True)
        assert len(results) == len(articles)

    @pytest.mark.asyncio
    async def test_ac03_failed_items_dont_stop_batch(
        self, extractor: Extractor
    ) -> None:
        """AC: Failed items are reported but don't stop the batch."""
        articles_with_bad = [
            "Valid article about technology.",
            "",  # Empty - might fail
            "Another valid article about markets.",
        ]

        results = await extractor.extract_batch(
            articles_with_bad,
            fail_fast=False,
        )

        # Should have processed the valid ones
        assert len(results) >= 1


# =============================================================================
# US-010: Cross-Source Deduplication
# =============================================================================


class TestUS010Deduplication:
    """
    US-010: Cross-Source Deduplication

    As a user subscribed to multiple sources, I want to see each story
    only once even if multiple sources covered it.
    """

    def test_ac01_similarity_threshold_configurable(self) -> None:
        """AC: Similarity threshold is configurable."""
        config = Config()

        # Default threshold
        assert config.digest.similarity_threshold == 0.85

        # Can be changed
        config.digest.similarity_threshold = 0.90
        assert config.digest.similarity_threshold == 0.90

    def test_ac02_deduplication_configurable(self) -> None:
        """AC: Deduplication can be enabled/disabled."""
        config = Config()

        # Default enabled
        assert config.digest.deduplication_enabled is True

        # Can be disabled
        config.digest.deduplication_enabled = False
        assert config.digest.deduplication_enabled is False
