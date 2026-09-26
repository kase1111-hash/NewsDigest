"""Pytest configuration and fixtures for NewsDigest tests."""

import pytest

from newsdigest.config.settings import Config
from newsdigest.core.article import Article, SourceType
from newsdigest.core.result import (
    Claim,
    ClaimType,
    ExtractionResult,
    ExtractionStatistics,
    Sentence,
    SentenceCategory,
)


@pytest.fixture
def default_config() -> Config:
    """Provide default configuration for tests."""
    return Config()


@pytest.fixture
def sample_article() -> Article:
    """Provide a sample article for testing."""
    return Article(
        id="test-article-001",
        content=(
            "In a stunning development that has shocked experts, "
            "the Federal Reserve held interest rates at 5.25%. "
            "Chair Powell said the decision was unanimous. "
            "Sources familiar with the matter suggest more cuts may come. "
            "This is what you need to know about the decision."
        ),
        url="https://example.com/article",
        title="Fed Holds Rates Steady",
        source_name="Example News",
        source_type=SourceType.URL,
    )


@pytest.fixture
def sample_sentence() -> Sentence:
    """Provide a sample sentence for testing."""
    return Sentence(
        text="The Federal Reserve held interest rates at 5.25%.",
        index=0,
        tokens=[
            "The",
            "Federal",
            "Reserve",
            "held",
            "interest",
            "rates",
            "at",
            "5.25",
            "%",
            ".",
        ],
        pos_tags=[
            "DET",
            "PROPN",
            "PROPN",
            "VERB",
            "NOUN",
            "NOUN",
            "ADP",
            "NUM",
            "NOUN",
            "PUNCT",
        ],
        entities=[{"text": "Federal Reserve", "label": "ORG"}],
        density_score=0.8,
        novelty_score=0.9,
        category=SentenceCategory.FACTUAL,
        keep=True,
    )


@pytest.fixture
def sample_claim() -> Claim:
    """Provide a sample claim for testing."""
    return Claim(
        text="Federal Reserve held interest rates at 5.25%",
        claim_type=ClaimType.FACTUAL,
        source="Federal Reserve",
        source_type="official",
        confidence=0.95,
        sentence_index=0,
    )


@pytest.fixture
def sample_extraction_result(sample_claim: Claim) -> ExtractionResult:
    """Provide a sample extraction result for testing."""
    return ExtractionResult(
        id="ext-001",
        url="https://example.com/article",
        title="Fed Holds Rates Steady",
        source="Example News",
        text="Federal Reserve held rates at 5.25%. Powell: decision unanimous.",
        claims=[sample_claim],
        sources_named=["Federal Reserve", "Jerome Powell"],
        statistics=ExtractionStatistics(
            original_words=50,
            compressed_words=10,
            compression_ratio=0.80,
            original_density=0.12,
            compressed_density=0.85,
            novel_claims=2,
            named_sources=2,
            unnamed_sources=1,
            emotional_words_removed=2,
            speculation_removed=1,
        ),
    )


@pytest.fixture
def emotional_text() -> str:
    """Provide text with emotional language for testing."""
    return (
        "In a shocking and unprecedented development that has left experts alarmed, "
        "the stunning announcement sent shockwaves through the market. "
        "This bombshell revelation is nothing short of extraordinary."
    )


@pytest.fixture
def speculative_text() -> str:
    """Provide text with speculation for testing."""
    return (
        "The decision could potentially signal a shift in policy. "
        "Analysts say this might indicate future changes. "
        "It would appear that markets may react positively."
    )


@pytest.fixture
def filler_text() -> str:
    """Provide text with filler content for testing."""
    return (
        "Here's what you need to know. "
        "But that's not the whole story. "
        "What happened next will surprise you. "
        "Stay tuned for more updates."
    )
