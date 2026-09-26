"""Tests for the core Extractor class."""

import pytest

from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor


class TestExtractorInitialization:
    """Tests for Extractor initialization."""

    def test_extractor_initialization(self, default_config: Config) -> None:
        """Test that Extractor initializes correctly."""
        extractor = Extractor(config=default_config)
        assert extractor.config == default_config
        assert extractor.mode == "standard"

    def test_extractor_default_config(self) -> None:
        """Test that Extractor uses default config when none provided."""
        extractor = Extractor()
        assert extractor.config is not None
        assert extractor.mode == "standard"

    def test_extractor_custom_mode(self) -> None:
        """Test that Extractor accepts custom mode."""
        extractor = Extractor(mode="aggressive")
        assert extractor.mode == "aggressive"

    def test_extractor_conservative_mode(self) -> None:
        """Test that Extractor accepts conservative mode."""
        extractor = Extractor(mode="conservative")
        assert extractor.mode == "conservative"


class TestExtractorURLDetection:
    """Tests for URL detection in Extractor."""

    def test_is_url_http(self) -> None:
        """Test HTTP URL detection."""
        extractor = Extractor()
        assert extractor._is_url("http://example.com") is True

    def test_is_url_https(self) -> None:
        """Test HTTPS URL detection."""
        extractor = Extractor()
        assert extractor._is_url("https://example.com/path") is True

    def test_is_url_plain_text(self) -> None:
        """Test that plain text is not detected as URL."""
        extractor = Extractor()
        assert extractor._is_url("This is just text") is False

    def test_is_url_ftp_rejected(self) -> None:
        """Test that FTP URLs are rejected."""
        extractor = Extractor()
        assert extractor._is_url("ftp://example.com") is False

    def test_is_url_empty_string(self) -> None:
        """Test empty string handling."""
        extractor = Extractor()
        assert extractor._is_url("") is False

    def test_is_url_with_query_params(self) -> None:
        """Test URL with query parameters."""
        extractor = Extractor()
        assert extractor._is_url("https://example.com/path?foo=bar&baz=1") is True


class TestExtractorRSSDetection:
    """Tests for RSS feed detection in Extractor."""

    def test_looks_like_rss_feed_path(self) -> None:
        """Test /feed path detection."""
        extractor = Extractor()
        assert extractor._looks_like_rss("https://example.com/feed") is True

    def test_looks_like_rss_rss_path(self) -> None:
        """Test /rss path detection."""
        extractor = Extractor()
        assert extractor._looks_like_rss("https://example.com/rss") is True

    def test_looks_like_rss_atom_path(self) -> None:
        """Test /atom path detection."""
        extractor = Extractor()
        assert extractor._looks_like_rss("https://example.com/atom.xml") is True

    def test_looks_like_rss_xml_extension(self) -> None:
        """Test .xml extension detection."""
        extractor = Extractor()
        assert extractor._looks_like_rss("https://example.com/news.xml") is True

    def test_looks_like_rss_regular_url(self) -> None:
        """Test regular URL is not RSS."""
        extractor = Extractor()
        assert extractor._looks_like_rss("https://example.com/article") is False


class TestExtractorFormatting:
    """Tests for Extractor formatting methods."""

    def test_format_unknown_raises(self, sample_extraction_result) -> None:
        """Test that unknown format raises ValueError."""
        extractor = Extractor()
        with pytest.raises(ValueError, match="Unknown format"):
            extractor.format(sample_extraction_result, format="unknown")

    def test_format_markdown(self, sample_extraction_result) -> None:
        """Test markdown formatting."""
        extractor = Extractor()
        result = extractor.format(sample_extraction_result, format="markdown")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_format_json(self, sample_extraction_result) -> None:
        """Test JSON formatting."""
        extractor = Extractor()
        result = extractor.format(sample_extraction_result, format="json")
        assert isinstance(result, str)
        # Should be valid JSON
        import json

        parsed = json.loads(result)
        assert parsed["extracted"]["text"] == sample_extraction_result.text

    def test_format_text(self, sample_extraction_result) -> None:
        """Test text formatting."""
        extractor = Extractor()
        result = extractor.format(sample_extraction_result, format="text")
        assert isinstance(result, str)

    def test_format_case_insensitive(self, sample_extraction_result) -> None:
        """Test that format is case-insensitive."""
        extractor = Extractor()
        result1 = extractor.format(sample_extraction_result, format="MARKDOWN")
        result2 = extractor.format(sample_extraction_result, format="markdown")
        assert result1 == result2


class TestExtractorConfigBuild:
    """Tests for Extractor configuration building."""

    def test_build_config_dict(self) -> None:
        """Test that config dict is built correctly."""
        config = Config()
        extractor = Extractor(config=config)

        config_dict = extractor._config_dict

        assert "extraction" in config_dict
        assert "output" in config_dict
        assert "spacy_model" in config_dict
        assert config_dict["extraction"]["mode"] == "standard"

    def test_build_config_dict_aggressive_mode(self) -> None:
        """Test config dict with aggressive mode."""
        config = Config()
        extractor = Extractor(config=config, mode="aggressive")

        config_dict = extractor._config_dict

        assert config_dict["extraction"]["mode"] == "aggressive"


class TestExtractorModes:
    """Tests for extraction mode handling."""

    def test_invalid_mode_raises(self) -> None:
        """Test that an unknown mode is rejected instead of silently ignored."""
        with pytest.raises(ValueError, match="Unknown extraction mode"):
            Extractor(mode="bogus")

    def test_mode_defaults_to_config(self) -> None:
        """Test that the configured mode is used when none is passed."""
        config = Config()
        config.extraction.mode = "aggressive"
        assert Extractor(config=config).mode == "aggressive"

    def test_explicit_mode_overrides_config(self) -> None:
        """Test that an explicit mode wins over the configured one."""
        config = Config()
        config.extraction.mode = "aggressive"
        assert Extractor(config=config, mode="conservative").mode == "conservative"

    def test_modes_change_extraction(self) -> None:
        """Test that modes actually tune the analyzers, not just a label."""
        text = "The dangerous storm hit the Florida coast on Monday, officials said."

        standard = Extractor(mode="standard").extract_sync(text)
        aggressive = Extractor(mode="aggressive").extract_sync(text)

        assert "dangerous" in standard.text
        assert "dangerous" not in aggressive.text
        assert "Florida" in aggressive.text


class TestExtractSync:
    """Tests for the synchronous extraction wrapper."""

    async def test_extract_sync_inside_running_loop(self) -> None:
        """Test extract_sync works when called from async code."""
        result = Extractor().extract_sync("Apple reported revenue of $90 billion.")
        assert "90 billion" in result.text

    def test_extract_text_is_sync_alias(self) -> None:
        """Test extract_text returns a result without an event loop."""
        result = Extractor().extract_text("Apple reported revenue of $90 billion.")
        assert "90 billion" in result.text


class TestExtractorStatistics:
    """Tests for extraction statistics."""

    def test_density_rises_as_filler_is_removed(self) -> None:
        """Test original density is non-zero and lower than compressed density."""
        text = (
            "Apple reported revenue of $90 billion on Tuesday. "
            "Here's what you need to know about the results. "
            "Stay tuned for more updates on this story. "
            "CEO Tim Cook said iPhone sales rose 12%."
        )
        stats = Extractor().extract_sync(text).statistics

        assert stats.original_density > 0
        assert stats.compressed_density > stats.original_density

    def test_one_claim_per_sentence(self) -> None:
        """Test an attributed statistic is not reported as two claims."""
        result = Extractor().extract_sync(
            "Apple reported revenue of $90 billion, CEO Tim Cook said."
        )
        assert len(result.claims) == 1
