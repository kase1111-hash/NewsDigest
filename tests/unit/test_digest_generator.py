"""Tests for DigestGenerator configuration and period handling."""

from datetime import UTC, datetime, timedelta

import pytest

from newsdigest.config.settings import Config
from newsdigest.digest.generator import Digest, DigestGenerator


class TestDigestGeneratorOptions:
    """Tests that generator options reach its components."""

    def test_defaults_from_config(self):
        """Test the configured mode and dedup threshold are used by default."""
        config = Config()
        config.extraction.mode = "aggressive"
        config.digest.similarity_threshold = 0.6

        generator = DigestGenerator(config=config)

        assert generator._extractor.mode == "aggressive"
        assert generator._deduplicator.threshold == 0.6

    def test_explicit_options(self):
        """Test mode, per-feed limit and similarity threshold are applied."""
        generator = DigestGenerator(
            config=Config(http_timeout=12),
            mode="conservative",
            max_items_per_source=5,
            similarity_threshold=0.9,
        )

        assert generator._extractor.mode == "conservative"
        assert generator._rss_parser.max_items == 5
        assert generator._rss_parser._url_fetcher.timeout == 12
        assert generator._deduplicator.threshold == 0.9


class TestDigestPeriods:
    """Tests for period parsing."""

    @pytest.mark.parametrize(
        "period,delta",
        [
            ("24h", timedelta(hours=24)),
            ("7d", timedelta(days=7)),
            ("1w", timedelta(weeks=1)),
            (" 48H ", timedelta(hours=48)),
        ],
    )
    def test_valid_periods(self, period, delta):
        """Test periods resolve to a UTC cutoff."""
        since = DigestGenerator()._parse_period(period)

        assert since.tzinfo is UTC
        assert abs((datetime.now(UTC) - since) - delta) < timedelta(seconds=5)

    @pytest.mark.parametrize("period", ["", "soon", "h", "24", "1.5d", "-3d"])
    def test_invalid_periods_raise(self, period):
        """Test invalid periods fail clearly instead of crashing or ignoring."""
        with pytest.raises(ValueError, match="Invalid period"):
            DigestGenerator()._parse_period(period)

    def test_generated_at_is_timezone_aware(self):
        """Test digests carry an aware UTC timestamp."""
        assert Digest().generated_at.tzinfo is UTC
