"""API regression tests.

These tests ensure the public API remains stable and backwards compatible.
"""

import json
from typing import Any

import pytest

from newsdigest.config.settings import (
    Config,
    DigestConfig,
    ExtractionConfig,
    OutputConfig,
)
from newsdigest.core.article import Article, SourceType
from newsdigest.core.extractor import Extractor
from newsdigest.core.result import (
    ExtractionResult,
    ExtractionStatistics,
)


class TestExtractorAPIRegression:
    """Tests for Extractor public API stability."""

    def test_extractor_init_signature(self) -> None:
        """Extractor.__init__ accepts expected parameters."""
        # Default initialization
        e1 = Extractor()
        assert e1 is not None

        # With config
        e2 = Extractor(config=Config())
        assert e2 is not None

        # With mode
        e3 = Extractor(mode="aggressive")
        assert e3.mode == "aggressive"

        # With both
        e4 = Extractor(config=Config(), mode="conservative")
        assert e4.mode == "conservative"

    def test_extractor_has_required_methods(self) -> None:
        """Extractor has all required public methods."""
        extractor = Extractor()

        required_methods = [
            "extract",
            "extract_sync",
            "extract_batch",
            "compare",
            "format",
            "format_stats",
            "format_comparison",
        ]

        for method in required_methods:
            assert hasattr(extractor, method), f"Missing method: {method}"
            assert callable(getattr(extractor, method)), f"Not callable: {method}"

    def test_extractor_has_required_attributes(self) -> None:
        """Extractor has all required public attributes."""
        extractor = Extractor()

        required_attrs = ["config", "mode"]

        for attr in required_attrs:
            assert hasattr(extractor, attr), f"Missing attribute: {attr}"

    def test_extract_sync_return_type(self) -> None:
        """extract_sync returns ExtractionResult."""
        extractor = Extractor()
        result = extractor.extract_sync("Test content.")

        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extract_return_type(self) -> None:
        """extract returns ExtractionResult."""
        extractor = Extractor()
        result = await extractor.extract("Test content.")

        assert isinstance(result, ExtractionResult)

    @pytest.mark.asyncio
    async def test_extract_batch_return_type(self) -> None:
        """extract_batch returns list of ExtractionResult."""
        extractor = Extractor()
        results = await extractor.extract_batch(["Test 1.", "Test 2."])

        assert isinstance(results, list)
        for result in results:
            assert isinstance(result, ExtractionResult)

    def test_format_return_type(self) -> None:
        """format returns string."""
        extractor = Extractor()
        result = extractor.extract_sync("Test content.")

        for fmt in ["markdown", "json", "text"]:
            output = extractor.format(result, format=fmt)
            assert isinstance(output, str)


class TestExtractionResultAPIRegression:
    """Tests for ExtractionResult structure stability."""

    @pytest.fixture
    def result(self) -> ExtractionResult:
        """Create a standard extraction result."""
        return Extractor().extract_sync(
            "Apple reported $90 billion revenue. CEO Tim Cook announced results."
        )

    def test_result_has_required_fields(self, result: ExtractionResult) -> None:
        """ExtractionResult has all required fields."""
        required_fields = [
            "id",
            "text",
            "claims",
            "statistics",
            "sources_named",
        ]

        for field in required_fields:
            assert hasattr(result, field), f"Missing field: {field}"

    def test_result_optional_fields(self, result: ExtractionResult) -> None:
        """ExtractionResult has expected optional fields."""
        optional_fields = [
            "url",
            "title",
            "source",
            "published_at",
            "warnings",
            "removed",
            "original_text",
            "sentences",
        ]

        # These should exist (even if None)
        for field in optional_fields:
            assert hasattr(result, field), f"Missing optional field: {field}"

    def test_statistics_structure(self, result: ExtractionResult) -> None:
        """Statistics have required fields."""
        stats = result.statistics

        assert isinstance(stats, ExtractionStatistics)

        required_stats = [
            "original_words",
            "compressed_words",
            "compression_ratio",
            "original_density",
            "compressed_density",
            "novel_claims",
            "named_sources",
            "unnamed_sources",
            "emotional_words_removed",
            "speculation_removed",
        ]

        for stat in required_stats:
            assert hasattr(stats, stat), f"Missing statistic: {stat}"


class TestConfigAPIRegression:
    """Tests for Config structure stability."""

    def test_config_has_required_fields(self) -> None:
        """Config has all required fields."""
        config = Config()

        required_fields = [
            "extraction",
            "digest",
            "output",
            "spacy_model",
            "http_timeout",
            "http_retries",
            "requests_per_second",
            "cache_enabled",
            "cache_ttl",
        ]

        for field in required_fields:
            assert hasattr(config, field), f"Missing field: {field}"

    def test_extraction_config_structure(self) -> None:
        """ExtractionConfig has required fields."""
        config = ExtractionConfig()

        required_fields = [
            "mode",
            "min_sentence_density",
            "unnamed_sources",
            "speculation",
            "max_hedges_per_sentence",
            "emotional_language",
            "quotes",
        ]

        for field in required_fields:
            assert hasattr(config, field), f"Missing field: {field}"

    def test_digest_config_structure(self) -> None:
        """DigestConfig has required fields."""
        config = DigestConfig()

        required_fields = [
            "period",
            "max_items",
            "clustering_enabled",
            "deduplication_enabled",
            "similarity_threshold",
            "min_novelty_score",
        ]

        for field in required_fields:
            assert hasattr(config, field), f"Missing field: {field}"

    def test_output_config_structure(self) -> None:
        """OutputConfig has required fields."""
        config = OutputConfig()

        required_fields = [
            "format",
            "show_stats",
            "include_links",
            "show_warnings",
        ]

        for field in required_fields:
            assert hasattr(config, field), f"Missing field: {field}"

    def test_config_class_methods(self) -> None:
        """Config has required class methods."""
        assert hasattr(Config, "from_file")
        assert hasattr(Config, "from_env")
        assert callable(Config.from_file)
        assert callable(Config.from_env)

    def test_config_instance_methods(self) -> None:
        """Config has required instance methods."""
        config = Config()

        assert hasattr(config, "save")
        assert hasattr(config, "to_env_vars")
        assert callable(config.save)
        assert callable(config.to_env_vars)


class TestArticleAPIRegression:
    """Tests for Article structure stability."""

    def test_article_has_required_fields(self) -> None:
        """Article has required fields."""
        article = Article(
            id="test-001",
            content="Test content",
            source_type=SourceType.TEXT,
        )

        required_fields = [
            "id",
            "content",
            "source_type",
        ]

        for field in required_fields:
            assert hasattr(article, field), f"Missing field: {field}"

    def test_article_optional_fields(self) -> None:
        """Article has expected optional fields."""
        article = Article(
            id="test-001",
            content="Test content",
            source_type=SourceType.TEXT,
        )

        optional_fields = [
            "url",
            "title",
            "source_name",
            "published_at",
            "author",
        ]

        for field in optional_fields:
            assert hasattr(article, field), f"Missing optional field: {field}"

    def test_source_type_values(self) -> None:
        """SourceType has expected values."""
        expected_types = ["URL", "RSS", "TEXT", "NEWSAPI"]

        for type_name in expected_types:
            assert hasattr(SourceType, type_name), f"Missing SourceType: {type_name}"


class TestJSONOutputRegression:
    """Tests for JSON output schema stability."""

    @pytest.fixture
    def json_output(self) -> dict[str, Any]:
        """Get JSON output."""
        extractor = Extractor()
        result = extractor.extract_sync(
            "Apple reported $90 billion. CEO Tim Cook was pleased."
        )
        return json.loads(extractor.format(result, format="json"))

    def test_json_top_level_structure(self, json_output: dict[str, Any]) -> None:
        """JSON has expected top-level structure."""
        # These fields should always be present
        assert "text" in json_output["extracted"]
        assert "statistics" in json_output

    def test_json_statistics_structure(self, json_output: dict[str, Any]) -> None:
        """JSON statistics have expected structure."""
        stats = json_output.get("statistics", {})

        expected_stats = [
            "original_words",
            "compressed_words",
            "compression_ratio",
        ]

        for stat in expected_stats:
            assert stat in stats, f"Missing stat in JSON: {stat}"

    def test_json_types_correct(self, json_output: dict[str, Any]) -> None:
        """JSON field types are correct."""
        assert isinstance(json_output["extracted"]["text"], str)

        stats = json_output["statistics"]
        assert isinstance(stats["original_words"], (int, float))
        assert isinstance(stats["compressed_words"], (int, float))
        assert isinstance(stats["compression_ratio"], (int, float))


class TestExceptionAPIRegression:
    """Tests for exception hierarchy stability."""

    def test_base_exception_exists(self) -> None:
        """NewsDigestError base exception exists."""
        from newsdigest.exceptions import NewsDigestError

        assert issubclass(NewsDigestError, Exception)

    def test_exception_hierarchy(self) -> None:
        """Exception hierarchy is correct."""
        from newsdigest.exceptions import (
            ConfigurationError,
            ExtractionError,
            FetchError,
            FormatterError,
            IngestError,
            NewsDigestError,
            ParseError,
            PipelineError,
        )

        # All should inherit from NewsDigestError
        exceptions = [
            ConfigurationError,
            ExtractionError,
            IngestError,
            FetchError,
            ParseError,
            PipelineError,
            FormatterError,
        ]

        for exc in exceptions:
            assert issubclass(exc, NewsDigestError), \
                f"{exc.__name__} should inherit from NewsDigestError"

    def test_exception_attributes(self) -> None:
        """Exceptions have expected attributes."""
        from newsdigest.exceptions import NewsDigestError

        exc = NewsDigestError("Test error", cause=ValueError("cause"), details={"key": "value"})

        assert hasattr(exc, "message")
        assert hasattr(exc, "cause")
        assert hasattr(exc, "details")
        assert exc.message == "Test error"
        assert isinstance(exc.cause, ValueError)
        assert exc.details == {"key": "value"}


class TestUtilsAPIRegression:
    """Tests for utility function stability."""

    def test_logging_functions_exist(self) -> None:
        """Logging utility functions exist."""
        from newsdigest.utils import (
            get_logger,
            init_logging,
            log_performance,
            setup_logging,
        )

        assert callable(setup_logging)
        assert callable(get_logger)
        assert callable(init_logging)
        assert callable(log_performance)

    def test_validation_functions_exist(self) -> None:
        """Validation utility functions exist."""
        from newsdigest.utils import (
            is_valid_url,
            sanitize_html,
            sanitize_text,
            validate_text_content,
            validate_url,
            validate_url_strict,
        )

        assert callable(validate_url)
        assert callable(validate_url_strict)
        assert callable(is_valid_url)
        assert callable(sanitize_html)
        assert callable(sanitize_text)
        assert callable(validate_text_content)

    def test_error_reporting_functions_exist(self) -> None:
        """Error reporting utility functions exist."""
        from newsdigest.utils import (
            add_breadcrumb,
            capture_errors,
            capture_exception,
            capture_message,
            configure_error_reporting,
        )

        assert callable(configure_error_reporting)
        assert callable(capture_exception)
        assert callable(capture_message)
        assert callable(add_breadcrumb)
        assert callable(capture_errors)
