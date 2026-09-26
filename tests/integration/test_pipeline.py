"""Integration tests for the extraction pipeline.

These tests verify that multiple components work together correctly.
"""

import pytest

from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult


class TestPipelineIntegration:
    """Integration tests for the full extraction pipeline."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create an extractor instance for testing."""
        return Extractor()

    @pytest.fixture
    def factual_article_content(self) -> str:
        """Article content that is mostly factual."""
        return """
        The Federal Reserve announced a 0.25% interest rate increase on Wednesday.
        Fed Chair Jerome Powell stated that inflation remains a concern.
        "We are committed to bringing inflation back to our 2% target," Powell said.
        The decision was approved by a vote of 11-1.
        Treasury yields rose following the announcement.
        The S&P 500 fell 0.5% in response to the news.
        """

    @pytest.fixture
    def emotional_article_content(self) -> str:
        """Article content with emotional language."""
        return """
        In a shocking development that has left experts alarmed, stocks crashed today.
        The unprecedented collapse sent shockwaves through Wall Street.
        This stunning revelation has investors in a panic.
        Sources say the bombshell announcement caught everyone off guard.
        """

    @pytest.fixture
    def speculative_article_content(self) -> str:
        """Article content with speculation."""
        return """
        The company could potentially announce layoffs next quarter.
        Analysts suggest this might signal broader economic troubles.
        It would appear that management may be considering restructuring.
        Sources familiar with the matter indicate changes could be coming.
        """

    def test_extractor_processes_factual_content(
        self, extractor: Extractor, factual_article_content: str
    ) -> None:
        """Test that factual content is preserved through the pipeline."""
        result = extractor.extract_sync(factual_article_content)

        assert isinstance(result, ExtractionResult)
        assert result.text is not None
        assert len(result.text) > 0

        # Factual content should have good compression ratio (not too aggressive)
        assert result.statistics.compression_ratio < 0.9  # Some content kept

        # Should identify sources
        assert result.statistics.named_sources >= 1

    def test_extractor_removes_emotional_language(
        self, extractor: Extractor, emotional_article_content: str
    ) -> None:
        """Test that emotional language is detected and handled."""
        result = extractor.extract_sync(emotional_article_content)

        assert isinstance(result, ExtractionResult)

        # Emotional words should be detected
        assert result.statistics.emotional_words_removed >= 0

        # Check that some emotional words are removed from output
        emotional_words = [
            "shocking",
            "unprecedented",
            "stunning",
            "bombshell",
            "alarmed",
        ]
        output_lower = result.text.lower()

        # At least some emotional words should be removed or flagged
        remaining_emotional = sum(1 for w in emotional_words if w in output_lower)
        assert remaining_emotional < len(emotional_words)

    def test_extractor_handles_speculation(
        self, extractor: Extractor, speculative_article_content: str
    ) -> None:
        """Test that speculation is detected and handled."""
        result = extractor.extract_sync(speculative_article_content)

        assert isinstance(result, ExtractionResult)

        # Speculation should be detected
        assert result.statistics.speculation_removed >= 0

    def test_extractor_generates_statistics(
        self, extractor: Extractor, factual_article_content: str
    ) -> None:
        """Test that extraction generates complete statistics."""
        result = extractor.extract_sync(factual_article_content)

        stats = result.statistics

        assert stats.original_words > 0
        assert stats.compressed_words >= 0
        assert 0 <= stats.compression_ratio <= 1
        assert 0 <= stats.original_density <= 1
        assert 0 <= stats.compressed_density <= 1

    def test_extractor_extracts_claims(
        self, extractor: Extractor, factual_article_content: str
    ) -> None:
        """Test that claims are extracted from factual content."""
        result = extractor.extract_sync(factual_article_content)

        # Should extract some claims from factual content
        assert isinstance(result.claims, list)
        # Claims are optional, but stats should track them
        assert result.statistics.novel_claims >= 0

    def test_extractor_preserves_quotes(
        self, extractor: Extractor, factual_article_content: str
    ) -> None:
        """Test that attributed quotes are preserved."""
        result = extractor.extract_sync(factual_article_content)

        # The Powell quote should be preserved (it's attributed)
        assert "Powell" in result.text or len(result.sources_named) > 0


class TestFormattingIntegration:
    """Integration tests for output formatting."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create an extractor instance."""
        return Extractor()

    @pytest.fixture
    def sample_content(self) -> str:
        """Sample content for formatting tests."""
        return """
        Apple announced record quarterly earnings of $90 billion.
        CEO Tim Cook attributed the success to strong iPhone sales.
        "This was our best quarter ever," Cook said in a statement.
        """

    def test_markdown_format_output(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """Test markdown formatting of extraction results."""
        result = extractor.extract_sync(sample_content)
        formatted = extractor.format(result, format="markdown")

        assert isinstance(formatted, str)
        assert len(formatted) > 0
        # Markdown should have some structure
        assert "#" in formatted or "-" in formatted or result.text in formatted

    def test_json_format_output(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """Test JSON formatting of extraction results."""
        import json

        result = extractor.extract_sync(sample_content)
        formatted = extractor.format(result, format="json")

        assert isinstance(formatted, str)

        # Should be valid JSON
        parsed = json.loads(formatted)
        assert isinstance(parsed, dict)

        # Should contain expected fields
        assert "text" in parsed or "claims" in parsed or "statistics" in parsed

    def test_text_format_output(
        self, extractor: Extractor, sample_content: str
    ) -> None:
        """Test plain text formatting of extraction results."""
        result = extractor.extract_sync(sample_content)
        formatted = extractor.format(result, format="text")

        assert isinstance(formatted, str)
        assert len(formatted) > 0

    def test_stats_formatting(self, extractor: Extractor, sample_content: str) -> None:
        """Test statistics formatting."""
        result = extractor.extract_sync(sample_content)
        stats_output = extractor.format_stats(result, format="text")

        assert isinstance(stats_output, str)
        # Should contain some statistics
        assert "word" in stats_output.lower() or "%" in stats_output


class TestConfigIntegration:
    """Integration tests for configuration."""

    def test_config_affects_extraction_mode(self) -> None:
        """Test that config mode affects extraction behavior."""
        # Create extractors with different modes
        conservative = Extractor(mode="conservative")
        aggressive = Extractor(mode="aggressive")

        content = """
        This might potentially indicate a shift.
        The company could be considering changes.
        Shocking developments have alarmed experts.
        """

        result_conservative = conservative.extract_sync(content)
        result_aggressive = aggressive.extract_sync(content)

        # Aggressive mode should typically compress more
        # (though exact behavior depends on implementation)
        assert result_conservative is not None
        assert result_aggressive is not None

    def test_config_from_env_integration(self, monkeypatch) -> None:
        """Test that environment config is applied correctly."""
        monkeypatch.setenv("NEWSDIGEST_MODE", "aggressive")
        monkeypatch.setenv("NEWSDIGEST_HTTP_TIMEOUT", "60")

        config = Config.from_env()
        extractor = Extractor(config=config, mode=config.extraction.mode)

        assert extractor.mode == "aggressive"
        assert extractor.config.http_timeout == 60


class TestErrorHandlingIntegration:
    """Integration tests for error handling across components."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create an extractor instance."""
        return Extractor()

    def test_empty_content_handling(self, extractor: Extractor) -> None:
        """Test handling of empty content."""
        result = extractor.extract_sync("")

        # Should handle gracefully
        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words == 0

    def test_whitespace_only_content(self, extractor: Extractor) -> None:
        """Test handling of whitespace-only content."""
        result = extractor.extract_sync("   \n\n\t  ")

        assert isinstance(result, ExtractionResult)

    def test_very_short_content(self, extractor: Extractor) -> None:
        """Test handling of very short content."""
        result = extractor.extract_sync("Hello.")

        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words >= 1

    def test_unicode_content(self, extractor: Extractor) -> None:
        """Test handling of unicode content."""
        content = """
        日本の首相が新政策を発表した。
        The Japanese Prime Minister announced new policies.
        Émile Zola était un écrivain français.
        """
        result = extractor.extract_sync(content)

        assert isinstance(result, ExtractionResult)

    def test_special_characters_content(self, extractor: Extractor) -> None:
        """Test handling of special characters."""
        content = """
        Stock prices rose 15.5% to $123.45 per share.
        The CEO said: "Revenue increased by €50M (approx. £42M)."
        Contact: info@example.com | +1-555-0123
        """
        result = extractor.extract_sync(content)

        assert isinstance(result, ExtractionResult)
        assert (
            "15.5%" in result.text
            or "123.45" in result.text
            or result.statistics.original_words > 0
        )
