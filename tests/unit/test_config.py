"""Tests for configuration settings."""

import os
from pathlib import Path

import pytest

from newsdigest.config.settings import (
    Config,
    DigestConfig,
    ExtractionConfig,
    OutputConfig,
    QuotesConfig,
)


class TestQuotesConfig:
    """Tests for QuotesConfig."""

    def test_default_values(self):
        """Test default QuotesConfig values."""
        config = QuotesConfig()
        assert config.keep_attributed is True
        assert config.keep_unattributed is False
        assert config.flag_circular is True

    def test_custom_values(self):
        """Test custom QuotesConfig values."""
        config = QuotesConfig(
            keep_attributed=False,
            keep_unattributed=True,
            flag_circular=False,
        )
        assert config.keep_attributed is False
        assert config.keep_unattributed is True
        assert config.flag_circular is False


class TestExtractionConfig:
    """Tests for ExtractionConfig."""

    def test_default_values(self):
        """Test default ExtractionConfig values."""
        config = ExtractionConfig()
        assert config.mode == "standard"
        assert config.min_sentence_density == 0.3
        assert config.unnamed_sources == "flag"
        assert config.speculation == "remove"
        assert config.max_hedges_per_sentence == 2
        assert config.emotional_language == "remove"

    def test_quotes_nested_config(self):
        """Test that quotes config is properly nested."""
        config = ExtractionConfig()
        assert isinstance(config.quotes, QuotesConfig)
        assert config.quotes.keep_attributed is True

    def test_aggressive_mode(self):
        """Test aggressive extraction mode."""
        config = ExtractionConfig(mode="aggressive")
        assert config.mode == "aggressive"


class TestDigestConfig:
    """Tests for DigestConfig."""

    def test_default_values(self):
        """Test default DigestConfig values."""
        config = DigestConfig()
        assert config.period == "24h"
        assert config.max_items == 100
        assert config.clustering_enabled is True
        assert config.deduplication_enabled is True
        assert config.similarity_threshold == 0.85
        assert config.min_novelty_score == 0.3

    def test_custom_values(self):
        """Test custom DigestConfig values."""
        config = DigestConfig(
            period="1h",
            max_items=50,
            similarity_threshold=0.9,
        )
        assert config.period == "1h"
        assert config.max_items == 50
        assert config.similarity_threshold == 0.9


class TestOutputConfig:
    """Tests for OutputConfig."""

    def test_default_values(self):
        """Test default OutputConfig values."""
        config = OutputConfig()
        assert config.format == "markdown"
        assert config.show_stats is True
        assert config.include_links is True
        assert config.show_warnings is True

    def test_json_format(self):
        """Test JSON output format."""
        config = OutputConfig(format="json")
        assert config.format == "json"


class TestConfig:
    """Tests for main Config class."""

    def test_default_values(self):
        """Test default Config values."""
        config = Config()
        assert config.spacy_model == "en_core_web_sm"
        assert config.http_timeout == 30
        assert config.http_retries == 3
        assert config.requests_per_second == 1.0
        assert config.cache_enabled is True
        assert config.cache_ttl == 3600
        assert config.cache_max_size == 1000

    def test_nested_configs(self):
        """Test that nested configs are properly initialized."""
        config = Config()
        assert isinstance(config.extraction, ExtractionConfig)
        assert isinstance(config.digest, DigestConfig)
        assert isinstance(config.output, OutputConfig)

    def test_config_dir_default(self):
        """Test default config directory."""
        config = Config()
        assert config.config_dir == Path.home() / ".newsdigest"

    def test_sources_default_empty(self):
        """Test that sources defaults to empty list."""
        config = Config()
        assert config.sources == []


class TestConfigFromEnv:
    """Tests for Config.from_env()."""

    def test_from_env_defaults(self):
        """Test from_env with no environment variables set."""
        config = Config.from_env()
        assert config.extraction.mode == "standard"
        assert config.spacy_model == "en_core_web_sm"

    def test_from_env_custom_mode(self, monkeypatch):
        """Test from_env with custom mode."""
        monkeypatch.setenv("NEWSDIGEST_MODE", "aggressive")
        config = Config.from_env()
        assert config.extraction.mode == "aggressive"

    def test_from_env_custom_spacy_model(self, monkeypatch):
        """Test from_env with custom spaCy model."""
        monkeypatch.setenv("NEWSDIGEST_SPACY_MODEL", "en_core_web_lg")
        config = Config.from_env()
        assert config.spacy_model == "en_core_web_lg"

    def test_from_env_http_settings(self, monkeypatch):
        """Test from_env with HTTP settings."""
        monkeypatch.setenv("NEWSDIGEST_HTTP_TIMEOUT", "60")
        monkeypatch.setenv("NEWSDIGEST_HTTP_RETRIES", "5")
        config = Config.from_env()
        assert config.http_timeout == 60
        assert config.http_retries == 5

    def test_from_env_boolean_true(self, monkeypatch):
        """Test from_env with boolean true values."""
        monkeypatch.setenv("NEWSDIGEST_CACHE_ENABLED", "true")
        config = Config.from_env()
        assert config.cache_enabled is True

    def test_from_env_boolean_false(self, monkeypatch):
        """Test from_env with boolean false values."""
        monkeypatch.setenv("NEWSDIGEST_CACHE_ENABLED", "false")
        config = Config.from_env()
        assert config.cache_enabled is False

    def test_from_env_float_settings(self, monkeypatch):
        """Test from_env with float settings."""
        monkeypatch.setenv("NEWSDIGEST_SIMILARITY_THRESHOLD", "0.95")
        monkeypatch.setenv("NEWSDIGEST_REQUESTS_PER_SECOND", "2.5")
        config = Config.from_env()
        assert config.digest.similarity_threshold == 0.95
        assert config.requests_per_second == 2.5

    def test_from_env_quotes_settings(self, monkeypatch):
        """Test from_env with quotes settings."""
        monkeypatch.setenv("NEWSDIGEST_QUOTES_KEEP_ATTRIBUTED", "false")
        monkeypatch.setenv("NEWSDIGEST_QUOTES_KEEP_UNATTRIBUTED", "true")
        config = Config.from_env()
        assert config.extraction.quotes.keep_attributed is False
        assert config.extraction.quotes.keep_unattributed is True

    def test_from_env_invalid_int_uses_default(self, monkeypatch):
        """Test from_env with invalid int uses default."""
        monkeypatch.setenv("NEWSDIGEST_HTTP_TIMEOUT", "not-a-number")
        config = Config.from_env()
        assert config.http_timeout == 30  # default


class TestConfigToEnvVars:
    """Tests for Config.to_env_vars()."""

    def test_to_env_vars(self):
        """Test conversion to environment variables."""
        config = Config()
        env_vars = config.to_env_vars()

        assert "NEWSDIGEST_MODE" in env_vars
        assert env_vars["NEWSDIGEST_MODE"] == "standard"
        assert "NEWSDIGEST_SPACY_MODEL" in env_vars
        assert "NEWSDIGEST_HTTP_TIMEOUT" in env_vars

    def test_to_env_vars_custom_prefix(self):
        """Test conversion with custom prefix."""
        config = Config()
        env_vars = config.to_env_vars(prefix="ND_")

        assert "ND_MODE" in env_vars
        assert "NEWSDIGEST_MODE" not in env_vars


class TestConfigLoad:
    """Tests for Config.load() (config file plus environment overrides)."""

    @pytest.fixture(autouse=True)
    def _clean_env(self, monkeypatch, tmp_path):
        """Isolate from the real home directory and NEWSDIGEST_* variables."""
        monkeypatch.setenv("HOME", str(tmp_path))
        for name in list(os.environ):
            if name.startswith("NEWSDIGEST_"):
                monkeypatch.delenv(name)

    def _write(self, path: Path, text: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_defaults_without_file(self):
        """Test a missing config file means default settings."""
        assert Config.load() == Config()

    def test_reads_default_location(self, tmp_path):
        """Test ~/.newsdigest/config.yml is read."""
        self._write(
            tmp_path / ".newsdigest" / "config.yml",
            "extraction:\n  mode: aggressive\nhttp_timeout: 45\n",
        )
        config = Config.load()
        assert config.extraction.mode == "aggressive"
        assert config.http_timeout == 45
        # Unspecified nested values keep their defaults
        assert config.extraction.speculation == "remove"

    def test_env_overrides_file(self, tmp_path, monkeypatch):
        """Test set environment variables win over the file."""
        path = self._write(tmp_path / "c.yml", "extraction:\n  mode: aggressive\n")
        monkeypatch.setenv("NEWSDIGEST_MODE", "conservative")
        monkeypatch.setenv("NEWSDIGEST_CACHE_TTL", "7200")

        config = Config.load(path)
        assert config.extraction.mode == "conservative"
        assert config.cache_ttl == 7200

    def test_config_path_from_env(self, tmp_path, monkeypatch):
        """Test NEWSDIGEST_CONFIG selects the file."""
        path = self._write(tmp_path / "custom.yml", "spacy_model: en_core_web_md\n")
        monkeypatch.setenv("NEWSDIGEST_CONFIG", str(path))
        assert Config.load().spacy_model == "en_core_web_md"

    def test_unprefixed_variables_ignored(self, monkeypatch):
        """Test generic names like MODE (set by other tools) are not read."""
        monkeypatch.setenv("MODE", "production")
        monkeypatch.setenv("CACHE_TTL", "5")
        config = Config.load()
        assert config.extraction.mode == "standard"
        assert config.cache_ttl == 3600

    def test_cors_origins_from_env(self, monkeypatch):
        """Test CORS origins can be configured as a comma-separated list."""
        monkeypatch.setenv("NEWSDIGEST_CORS_ORIGINS", "https://a.com, https://b.com")
        assert Config.load().cors_origins == ["https://a.com", "https://b.com"]

    def test_save_roundtrip(self, tmp_path):
        """Test a saved config can be loaded back."""
        config = Config()
        config.extraction.mode = "aggressive"
        path = tmp_path / "saved.yml"
        config.save(path)

        loaded = Config.from_file(path)
        assert loaded.extraction.mode == "aggressive"
        assert loaded.config_dir == config.config_dir

    def test_from_file_expands_home(self, tmp_path):
        """Test "~" in the path is expanded."""
        self._write(tmp_path / "cfg.yml", "http_retries: 7\n")
        assert Config.from_file("~/cfg.yml").http_retries == 7
