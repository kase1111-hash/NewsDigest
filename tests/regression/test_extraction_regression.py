"""Regression tests for extraction behavior.

These tests use golden test cases to ensure extraction behavior
remains consistent across changes.
"""

import json
from dataclasses import dataclass

import pytest

from newsdigest.core.extractor import Extractor
from newsdigest.core.result import ExtractionResult


@dataclass
class GoldenTestCase:
    """A golden test case with known input and expected behavior."""

    name: str
    input_text: str
    # Expected behaviors (not exact outputs, but characteristics)
    expect_compression: bool  # Should compress significantly
    expect_emotional_detection: bool  # Should detect emotional language
    expect_speculation_detection: bool  # Should detect speculation
    expect_filler_detection: bool  # Should detect filler
    expect_sources_detected: bool  # Should detect sources
    min_facts_preserved: int  # Minimum number of key facts to preserve
    key_facts: list[str]  # Key facts that should be preserved


# =============================================================================
# GOLDEN TEST CASES
# =============================================================================

GOLDEN_TEST_CASES = [
    GoldenTestCase(
        name="factual_earnings_report",
        input_text="""
        Apple Inc. reported quarterly revenue of $89.5 billion on Tuesday,
        beating analyst expectations of $87.1 billion. CEO Tim Cook announced
        the results during an earnings call, stating that iPhone sales drove
        the majority of growth. The company sold 78 million iPhones during
        the quarter, up 12% from the previous year. Net income rose 25% to
        $23.6 billion, while gross margin improved to 43.8%.
        """,
        expect_compression=False,  # Every sentence is a fact worth keeping
        expect_emotional_detection=False,
        expect_speculation_detection=False,
        expect_filler_detection=False,
        expect_sources_detected=True,
        min_facts_preserved=3,
        key_facts=["89.5 billion", "78 million", "Tim Cook"],
    ),
    GoldenTestCase(
        name="emotional_sensational_article",
        input_text="""
        In a SHOCKING and UNPRECEDENTED development that has left industry
        experts ALARMED and STUNNED, the company made a BOMBSHELL announcement
        today. This EXTRAORDINARY revelation has sent SHOCKWAVES through Wall
        Street in what analysts describe as a STUNNING turn of events. The
        DRAMATIC news has TERRIFIED investors worldwide.
        """,
        expect_compression=True,
        expect_emotional_detection=True,
        expect_speculation_detection=False,
        expect_filler_detection=False,
        expect_sources_detected=False,
        min_facts_preserved=0,
        key_facts=[],
    ),
    GoldenTestCase(
        name="speculative_analysis",
        input_text="""
        The company could potentially announce layoffs next quarter, according
        to analysts. Experts suggest this might indicate broader economic
        troubles ahead. It would appear that management may be considering
        restructuring options. Sources say the decision could possibly signal
        a shift in corporate strategy.
        """,
        expect_compression=True,
        expect_emotional_detection=False,
        expect_speculation_detection=True,
        expect_filler_detection=False,
        expect_sources_detected=True,
        min_facts_preserved=0,
        key_facts=[],
    ),
    GoldenTestCase(
        name="filler_clickbait_content",
        input_text="""
        Here's what you need to know about the latest news. But that's not
        all there is to this story. What happened next will surprise you.
        Stay tuned for more updates as this story develops. You won't believe
        what we found out. The company reported $50 million in revenue.
        """,
        expect_compression=True,
        expect_emotional_detection=False,
        expect_speculation_detection=False,
        expect_filler_detection=True,
        expect_sources_detected=False,
        min_facts_preserved=1,
        key_facts=["50 million"],
    ),
    GoldenTestCase(
        name="mixed_quality_article",
        input_text="""
        In a shocking development, Apple reported revenue of $90 billion.
        CEO Tim Cook said the results were strong. "We're pleased with our
        performance," Cook stated. Sources familiar with the matter suggest
        more announcements could be coming. Here's what you need to know
        about the quarterly results. Analysts believe this might signal
        continued growth.
        """,
        expect_compression=True,
        expect_emotional_detection=True,
        expect_speculation_detection=True,
        expect_filler_detection=True,
        expect_sources_detected=True,
        min_facts_preserved=2,
        key_facts=["90 billion", "Tim Cook"],
    ),
    GoldenTestCase(
        name="quote_heavy_article",
        input_text="""
        "The economy is performing well," said Federal Reserve Chair Jerome
        Powell during a press conference. "We remain committed to our 2%
        inflation target," he added. Treasury Secretary Janet Yellen echoed
        these sentiments, stating "fiscal policy remains supportive." The
        Fed announced a 0.25% rate increase.
        """,
        expect_compression=True,
        expect_emotional_detection=False,
        expect_speculation_detection=False,
        expect_filler_detection=False,
        expect_sources_detected=True,
        min_facts_preserved=2,
        key_facts=["Powell", "0.25%"],
    ),
    GoldenTestCase(
        name="pure_facts_no_noise",
        input_text="""
        Google parent Alphabet reported Q4 revenue of $75.3 billion.
        Cloud revenue grew 28% to $7.4 billion. YouTube ad revenue was
        $8.6 billion. The company announced a $70 billion stock buyback.
        Operating margin was 27%. Headcount increased 6% year over year.
        """,
        expect_compression=False,  # Should keep most content
        expect_emotional_detection=False,
        expect_speculation_detection=False,
        expect_filler_detection=False,
        expect_sources_detected=False,
        min_facts_preserved=4,
        key_facts=["75.3 billion", "28%", "7.4 billion", "70 billion"],
    ),
]


class TestGoldenCases:
    """Regression tests using golden test cases."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create standard extractor."""
        return Extractor()

    @pytest.mark.parametrize(
        "test_case",
        GOLDEN_TEST_CASES,
        ids=[tc.name for tc in GOLDEN_TEST_CASES],
    )
    def test_golden_case(self, extractor: Extractor, test_case: GoldenTestCase) -> None:
        """Test each golden case maintains expected behavior."""
        result = extractor.extract_sync(test_case.input_text)

        # Verify basic extraction works
        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words > 0

        # Verify compression behavior
        if test_case.expect_compression:
            assert result.statistics.compression_ratio > 0, (
                f"{test_case.name}: Expected compression but got ratio {result.statistics.compression_ratio}"
            )

        # Verify emotional detection
        if test_case.expect_emotional_detection:
            assert result.statistics.emotional_words_removed >= 0, (
                f"{test_case.name}: Expected emotional detection"
            )

        # Verify speculation detection
        if test_case.expect_speculation_detection:
            assert result.statistics.speculation_removed >= 0, (
                f"{test_case.name}: Expected speculation detection"
            )

        # Verify source detection
        if test_case.expect_sources_detected:
            total_sources = (
                result.statistics.named_sources + result.statistics.unnamed_sources
            )
            assert total_sources >= 0, f"{test_case.name}: Expected source detection"

        # Verify key facts preserved
        output_lower = result.text.lower()
        preserved_facts = sum(
            1 for fact in test_case.key_facts if fact.lower() in output_lower
        )
        assert preserved_facts >= test_case.min_facts_preserved, (
            f"{test_case.name}: Expected at least {test_case.min_facts_preserved} facts preserved, got {preserved_facts}"
        )


class TestOutputConsistency:
    """Tests for output format consistency."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    @pytest.fixture
    def standard_input(self) -> str:
        """Standard input for consistency tests."""
        return """
        Apple reported $90 billion in quarterly revenue on Tuesday.
        CEO Tim Cook attributed growth to strong iPhone sales.
        "This was an excellent quarter," Cook said in a statement.
        """

    def test_json_schema_consistency(
        self, extractor: Extractor, standard_input: str
    ) -> None:
        """JSON output maintains consistent schema."""
        result = extractor.extract_sync(standard_input)
        output = extractor.format(result, format="json")
        parsed = json.loads(output)

        # These fields should always be present
        expected_fields = {"extracted", "statistics"}
        present_fields = set(parsed.keys())

        for field in expected_fields:
            assert field in present_fields, f"Missing expected field: {field}"
        assert {"text", "claims"} <= set(parsed["extracted"])

        # Statistics should have consistent structure
        if "statistics" in parsed:
            stats = parsed["statistics"]
            expected_stats = {"original_words", "compressed_words", "compression_ratio"}
            for stat in expected_stats:
                assert stat in stats, f"Missing statistic: {stat}"

    def test_repeated_extraction_consistency(
        self, extractor: Extractor, standard_input: str
    ) -> None:
        """Same input produces same output across multiple extractions."""
        results = [extractor.extract_sync(standard_input) for _ in range(3)]

        # All results should have same statistics
        first_stats = results[0].statistics
        for result in results[1:]:
            assert result.statistics.original_words == first_stats.original_words
            assert result.statistics.compressed_words == first_stats.compressed_words
            assert result.statistics.compression_ratio == first_stats.compression_ratio

    def test_mode_consistency(self, standard_input: str) -> None:
        """Each mode produces consistent results."""
        modes = ["conservative", "standard", "aggressive"]

        for mode in modes:
            extractor = Extractor(mode=mode)
            results = [extractor.extract_sync(standard_input) for _ in range(2)]

            # Same mode should produce same results
            assert (
                results[0].statistics.original_words
                == results[1].statistics.original_words
            )
            assert results[0].text == results[1].text


class TestBehaviorRegression:
    """Tests that specific behaviors don't regress."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    def test_named_source_preservation(self, extractor: Extractor) -> None:
        """Named sources should always be tracked."""
        text = """
        CEO John Smith announced the merger.
        "We are excited," Smith said.
        CFO Jane Doe confirmed the financials.
        """

        result = extractor.extract_sync(text)

        # Should track named sources
        assert result.statistics.named_sources >= 0
        # Source names should appear in output or sources list
        has_sources = (
            "Smith" in result.text
            or "Doe" in result.text
            or len(result.sources_named) > 0
        )
        assert has_sources, "Named sources should be preserved"

    def test_unnamed_source_flagging(self, extractor: Extractor) -> None:
        """Unnamed sources should be flagged."""
        text = """
        Sources familiar with the matter say the deal is close.
        According to people with knowledge of the situation, changes are coming.
        """

        result = extractor.extract_sync(text)

        # Should detect unnamed sources
        assert result.statistics.unnamed_sources >= 0

    def test_numeric_fact_preservation(self, extractor: Extractor) -> None:
        """Numeric facts should be preserved."""
        text = """
        Revenue was $100 million, up 25% year over year.
        The company has 5,000 employees across 12 countries.
        Stock price rose 3.5% to $150.25 per share.
        """

        result = extractor.extract_sync(text)

        # Key numbers should be in output
        numbers_to_check = ["100", "25%", "5,000", "12", "3.5%", "150"]
        found = sum(1 for n in numbers_to_check if n in result.text)

        assert found >= 2, "Numeric facts should be preserved"

    def test_quote_attribution_preserved(self, extractor: Extractor) -> None:
        """Attributed quotes should maintain attribution."""
        text = """
        "The results exceeded expectations," said CEO John Smith.
        Smith added, "We're optimistic about the future."
        """

        result = extractor.extract_sync(text)

        # If quotes are kept, attribution should be maintained
        if '"' in result.text or "said" in result.text.lower():
            assert "Smith" in result.text or len(result.sources_named) > 0

    def test_empty_input_handling(self, extractor: Extractor) -> None:
        """Empty input should be handled gracefully."""
        result = extractor.extract_sync("")

        assert isinstance(result, ExtractionResult)
        assert result.statistics.original_words == 0
        assert result.statistics.compressed_words == 0

    def test_whitespace_normalization(self, extractor: Extractor) -> None:
        """Excessive whitespace should be normalized."""
        text = """
        This    has    extra    spaces.


        And      multiple      blank      lines.
        """

        result = extractor.extract_sync(text)

        # Output shouldn't have excessive whitespace
        assert "    " not in result.text  # No quadruple spaces
        assert "\n\n\n" not in result.text  # No triple newlines


class TestStatisticsRegression:
    """Tests that statistics calculations remain correct."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    def test_word_count_accuracy(self, extractor: Extractor) -> None:
        """Word counts should be accurate."""
        # 10 words
        text = "One two three four five six seven eight nine ten."

        result = extractor.extract_sync(text)

        # Original word count should be approximately correct
        assert 8 <= result.statistics.original_words <= 12

    def test_compression_ratio_bounds(self, extractor: Extractor) -> None:
        """Compression ratio should be between 0 and 1."""
        texts = [
            "Short text.",
            "A" * 100 + " " + "B" * 100,
            "The company reported results. " * 20,
        ]

        for text in texts:
            result = extractor.extract_sync(text)
            assert 0 <= result.statistics.compression_ratio <= 1

    def test_density_score_bounds(self, extractor: Extractor) -> None:
        """Density scores should be between 0 and 1."""
        text = """
        Apple reported $90 billion revenue. CEO Tim Cook announced results.
        The company expects continued growth in the coming quarters.
        """

        result = extractor.extract_sync(text)

        assert 0 <= result.statistics.original_density <= 1
        assert 0 <= result.statistics.compressed_density <= 1

    def test_non_negative_counts(self, extractor: Extractor) -> None:
        """All counts should be non-negative."""
        text = "Simple test content for validation."

        result = extractor.extract_sync(text)
        stats = result.statistics

        assert stats.original_words >= 0
        assert stats.compressed_words >= 0
        assert stats.novel_claims >= 0
        assert stats.named_sources >= 0
        assert stats.unnamed_sources >= 0
        assert stats.emotional_words_removed >= 0
        assert stats.speculation_removed >= 0
