"""Configuration settings for NewsDigest."""

import os
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class QuotesConfig(BaseModel):
    """Quote handling settings."""

    keep_attributed: bool = True
    keep_unattributed: bool = False
    flag_circular: bool = True


class ExtractionConfig(BaseModel):
    """Extraction-related settings."""

    mode: str = "standard"  # conservative, standard, aggressive
    min_sentence_density: float = 0.3
    unnamed_sources: str = "flag"  # keep, flag, remove
    speculation: str = "remove"  # keep, flag, remove
    max_hedges_per_sentence: int = 2
    emotional_language: str = "remove"  # keep, flag, remove
    quotes: QuotesConfig = Field(default_factory=QuotesConfig)


class DigestConfig(BaseModel):
    """Digest-related settings."""

    period: str = "24h"
    max_items: int = 100
    clustering_enabled: bool = True
    deduplication_enabled: bool = True
    similarity_threshold: float = 0.85
    min_novelty_score: float = 0.3


class OutputConfig(BaseModel):
    """Output-related settings."""

    format: str = "markdown"  # markdown, html, json, text
    show_stats: bool = True
    include_links: bool = True
    show_warnings: bool = True


# Environment variables (after the prefix) and the setting each one sets
_ENV_SETTINGS: list[tuple[str, tuple[str, ...], type]] = [
    ("MODE", ("extraction", "mode"), str),
    ("MIN_SENTENCE_DENSITY", ("extraction", "min_sentence_density"), float),
    ("UNNAMED_SOURCES", ("extraction", "unnamed_sources"), str),
    ("SPECULATION", ("extraction", "speculation"), str),
    ("MAX_HEDGES_PER_SENTENCE", ("extraction", "max_hedges_per_sentence"), int),
    ("EMOTIONAL_LANGUAGE", ("extraction", "emotional_language"), str),
    ("QUOTES_KEEP_ATTRIBUTED", ("extraction", "quotes", "keep_attributed"), bool),
    ("QUOTES_KEEP_UNATTRIBUTED", ("extraction", "quotes", "keep_unattributed"), bool),
    ("QUOTES_FLAG_CIRCULAR", ("extraction", "quotes", "flag_circular"), bool),
    ("DIGEST_PERIOD", ("digest", "period"), str),
    ("DIGEST_MAX_ITEMS", ("digest", "max_items"), int),
    ("DIGEST_CLUSTERING", ("digest", "clustering_enabled"), bool),
    ("DIGEST_DEDUP", ("digest", "deduplication_enabled"), bool),
    ("SIMILARITY_THRESHOLD", ("digest", "similarity_threshold"), float),
    ("MIN_NOVELTY_SCORE", ("digest", "min_novelty_score"), float),
    ("OUTPUT_FORMAT", ("output", "format"), str),
    ("OUTPUT_SHOW_STATS", ("output", "show_stats"), bool),
    ("OUTPUT_INCLUDE_LINKS", ("output", "include_links"), bool),
    ("OUTPUT_SHOW_WARNINGS", ("output", "show_warnings"), bool),
    ("SPACY_MODEL", ("spacy_model",), str),
    ("HTTP_TIMEOUT", ("http_timeout",), int),
    ("HTTP_RETRIES", ("http_retries",), int),
    ("REQUESTS_PER_SECOND", ("requests_per_second",), float),
    ("CACHE_ENABLED", ("cache_enabled",), bool),
    ("CACHE_TTL", ("cache_ttl",), int),
    ("CACHE_MAX_SIZE", ("cache_max_size",), int),
    ("CORS_ORIGINS", ("cors_origins",), list),
]


def _parse_env_value(raw: str, kind: type) -> Any:
    """Convert an environment variable string to a setting value.

    Raises:
        ValueError: If the value cannot be converted.
    """
    if kind is bool:
        return raw.strip().lower() in ("true", "1", "yes", "on")
    if kind is list:
        return [item.strip() for item in raw.split(",") if item.strip()]
    return kind(raw)


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overrides into base (in place) and return base."""
    for key, value in overrides.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


class Config(BaseModel):
    """Main configuration for NewsDigest."""

    # Paths
    config_dir: Path = Field(default_factory=lambda: Path.home() / ".newsdigest")

    # Component configs
    extraction: ExtractionConfig = Field(default_factory=ExtractionConfig)
    digest: DigestConfig = Field(default_factory=DigestConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)

    # Sources
    sources: list[dict[str, Any]] = Field(default_factory=list)

    # NLP settings
    spacy_model: str = "en_core_web_sm"

    # HTTP settings with bounds checking
    http_timeout: int = Field(default=30, ge=1, le=300)
    http_retries: int = Field(default=3, ge=0, le=10)
    requests_per_second: float = Field(default=1.0, gt=0, le=100)

    # Cache settings with bounds checking
    cache_enabled: bool = True
    cache_ttl: int = Field(default=3600, ge=0, le=86400)  # Max 24 hours
    cache_max_size: int = Field(default=1000, ge=1, le=100000)

    # CORS settings for API
    cors_origins: list[str] = Field(default_factory=list)

    @classmethod
    def from_file(cls, path: str | Path) -> "Config":
        """Load configuration from YAML file.

        Args:
            path: Path to YAML configuration file.

        Returns:
            Config instance.
        """
        return cls(**cls._read_file(path))

    @classmethod
    def load(
        cls, path: str | Path | None = None, prefix: str = "NEWSDIGEST_"
    ) -> "Config":
        """Load user configuration: the config file, then environment overrides.

        The file is `path`, else ``$NEWSDIGEST_CONFIG``, else
        ``~/.newsdigest/config.yml``; a missing file means defaults.
        Environment variables that are set override values from the file.

        Args:
            path: Optional path to a YAML configuration file.
            prefix: Environment variable prefix.

        Returns:
            Config instance.
        """
        if path is None:
            path = os.environ.get(f"{prefix}CONFIG") or (
                Path.home() / ".newsdigest" / "config.yml"
            )
        data = _deep_merge(cls._read_file(path), cls._env_overrides(prefix))
        return cls(**data)

    @staticmethod
    def _read_file(path: str | Path) -> dict[str, Any]:
        """Read a YAML configuration file.

        Args:
            path: Path to the file ("~" is expanded).

        Returns:
            Configuration mapping, or an empty dict if the file is missing.
        """
        import yaml

        path = Path(path).expanduser()
        if not path.exists():
            return {}

        with path.open(encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        if not isinstance(data, dict):
            raise ValueError(f"Configuration file must contain a mapping: {path}")
        return data

    @staticmethod
    def _env_overrides(prefix: str) -> dict[str, Any]:
        """Collect settings from environment variables that are set.

        Values that cannot be converted to the setting's type are ignored.

        Args:
            prefix: Environment variable prefix.

        Returns:
            Nested mapping of settings to override.
        """
        overrides: dict[str, Any] = {}
        for name, setting_path, kind in _ENV_SETTINGS:
            raw = os.environ.get(f"{prefix}{name}")
            if raw is None:
                continue
            try:
                value = _parse_env_value(raw, kind)
            except ValueError:
                continue
            target = overrides
            for key in setting_path[:-1]:
                target = target.setdefault(key, {})
            target[setting_path[-1]] = value
        return overrides

    @classmethod
    def from_env(cls, prefix: str = "NEWSDIGEST_") -> "Config":
        """Load configuration from environment variables.

        Supports the following environment variables:
        - NEWSDIGEST_MODE: Extraction mode (conservative, standard, aggressive)
        - NEWSDIGEST_SPACY_MODEL: spaCy model name
        - NEWSDIGEST_HTTP_TIMEOUT: HTTP timeout in seconds
        - NEWSDIGEST_HTTP_RETRIES: Number of HTTP retries
        - NEWSDIGEST_REQUESTS_PER_SECOND: Rate limit
        - NEWSDIGEST_CACHE_ENABLED: Enable caching (true/false)
        - NEWSDIGEST_CACHE_TTL: Cache TTL in seconds
        - NEWSDIGEST_OUTPUT_FORMAT: Output format (markdown, json, text)
        - NEWSDIGEST_SIMILARITY_THRESHOLD: Similarity threshold for dedup
        - NEWSDIGEST_CORS_ORIGINS: Comma-separated allowed API origins

        See _ENV_SETTINGS for the full list. Unset variables use defaults.

        Args:
            prefix: Environment variable prefix.

        Returns:
            Config instance.
        """
        return cls(**cls._env_overrides(prefix))

    def save(self, path: str | Path | None = None) -> None:
        """Save configuration to YAML file.

        Args:
            path: Path to save to. Defaults to config_dir/config.yml.
        """
        import yaml

        path = Path(path) if path else self.config_dir / "config.yml"
        path.parent.mkdir(parents=True, exist_ok=True)

        with path.open("w", encoding="utf-8") as f:
            # JSON mode turns Path values into plain strings that safe_load reads
            yaml.dump(self.model_dump(mode="json"), f, default_flow_style=False)

    def to_env_vars(self, prefix: str = "NEWSDIGEST_") -> dict[str, str]:
        """Export configuration as environment variables.

        Args:
            prefix: Environment variable prefix.

        Returns:
            Dictionary of environment variable names to values.
        """
        return {
            f"{prefix}MODE": self.extraction.mode,
            f"{prefix}SPACY_MODEL": self.spacy_model,
            f"{prefix}HTTP_TIMEOUT": str(self.http_timeout),
            f"{prefix}HTTP_RETRIES": str(self.http_retries),
            f"{prefix}REQUESTS_PER_SECOND": str(self.requests_per_second),
            f"{prefix}CACHE_ENABLED": str(self.cache_enabled).lower(),
            f"{prefix}CACHE_TTL": str(self.cache_ttl),
            f"{prefix}OUTPUT_FORMAT": self.output.format,
            f"{prefix}SIMILARITY_THRESHOLD": str(self.digest.similarity_threshold),
        }
