"""Integration tests for analyzer chain.

These tests verify that analyzers work correctly together on sentences
produced by the real NLP pipeline (spaCy annotations included).
"""

import pytest

from newsdigest.analyzers import (
    EmotionalDetector,
    FillerDetector,
    QuoteIsolator,
    SourceValidator,
    SpeculationStripper,
)
from newsdigest.core.pipeline import AnalysisPipeline
from newsdigest.core.result import Sentence, SentenceCategory


@pytest.fixture(scope="module")
def pipeline() -> AnalysisPipeline:
    """Pipeline used to turn text into annotated sentences."""
    return AnalysisPipeline()


@pytest.fixture
def to_sentences(pipeline: AnalysisPipeline):
    """Split text into annotated Sentence objects (no analysis applied)."""

    def _to_sentences(text: str) -> list[Sentence]:
        return pipeline.process(text)

    return _to_sentences


def _single(to_sentences, text: str) -> Sentence:
    """Process text that is expected to be exactly one sentence."""
    sentences = to_sentences(text)
    assert len(sentences) == 1, f"Expected one sentence: {text!r}"
    return sentences[0]


class TestAnalyzerChain:
    """Tests for multiple analyzers working together."""

    @pytest.fixture
    def analyzers(self):
        """Create all analyzer instances in pipeline order."""
        return {
            "sources": SourceValidator(),
            "quotes": QuoteIsolator(),
            "speculation": SpeculationStripper(),
            "emotional": EmotionalDetector(),
            "filler": FillerDetector(),
        }

    def _run_chain(self, analyzers, sentences: list[Sentence]) -> list[Sentence]:
        for analyzer in analyzers.values():
            sentences = analyzer.analyze(sentences)
        return sentences

    def test_analyzers_on_clean_factual_sentence(self, analyzers, to_sentences):
        """Test that factual sentences pass all analyzers cleanly."""
        sentence = _single(
            to_sentences, "Apple reported revenue of $90 billion for Q4 2024."
        )
        original_text = sentence.text

        self._run_chain(analyzers, [sentence])

        assert sentence.keep is True
        assert sentence.text == original_text
        assert sentence.category == SentenceCategory.FACTUAL
        assert sentence.speculation_score < analyzers["speculation"].speculation_threshold
        assert sentence.emotional_score < analyzers["emotional"].threshold

    def test_analyzers_detect_combined_issues(self, analyzers, to_sentences):
        """Test detection of content with multiple issues."""
        # Text with filler, emotional language, and speculation
        sentence = _single(
            to_sentences,
            "Here's what you need to know: in a shocking development, "
            "the company could potentially announce major changes.",
        )

        self._run_chain(analyzers, [sentence])

        assert sentence.keep is False
        assert sentence.removal_reason is not None

    def test_source_and_quote_extraction(self, analyzers, to_sentences):
        """Test source detection with quote extraction."""
        sentence = _single(
            to_sentences,
            '"The economy is strong," said Fed Chair Jerome Powell in a statement.',
        )

        self._run_chain(analyzers, [sentence])

        # Should detect the named source and classify the sentence as a quote
        assert sentence.has_named_source is True
        assert sentence.source_name is not None
        assert sentence.category == SentenceCategory.QUOTE
        assert sentence.keep is True

    def test_unnamed_source_detection(self, analyzers, to_sentences):
        """Test detection of unnamed sources."""
        sentence = _single(
            to_sentences, "Sources familiar with the matter say the deal is close."
        )

        self._run_chain(analyzers, [sentence])

        assert sentence.has_unnamed_source is True
        assert sentence.has_named_source is False


class TestAnalyzerConsistency:
    """Tests for analyzer consistency across inputs."""

    @pytest.mark.parametrize("phrase", [
        "Here's what you need to know",
        "What happened next will surprise you",
        "Stay tuned for more updates",
        "But that's not all",
    ])
    def test_filler_detection_consistency(self, to_sentences, phrase):
        """Test that filler detection is consistent."""
        sentence = _single(to_sentences, phrase)
        FillerDetector().analyze([sentence])
        assert sentence.keep is False, f"Failed to detect filler: {phrase}"
        assert sentence.category == SentenceCategory.FILLER

    @pytest.mark.parametrize("phrase", [
        "This could potentially indicate a change",
        "Experts suggest this might be significant",
        "It would appear that markets may react",
        "The decision could signal future shifts",
    ])
    def test_speculation_detection_consistency(self, to_sentences, phrase):
        """Test that speculation detection is consistent."""
        sentence = _single(to_sentences, phrase)
        SpeculationStripper().analyze([sentence])
        assert sentence.category == SentenceCategory.SPECULATION, (
            f"Failed to detect speculation: {phrase}"
        )
        assert sentence.keep is False

    @pytest.mark.parametrize("phrase", [
        "This is a shocking development",
        "The unprecedented announcement alarmed experts",
        "A stunning revelation emerged today",
        "The bombshell news sent shockwaves",
    ])
    def test_emotional_detection_consistency(self, to_sentences, phrase):
        """Test that emotional detection is consistent."""
        sentence = _single(to_sentences, phrase)
        detector = EmotionalDetector()
        detector.analyze([sentence])
        assert sentence.category == SentenceCategory.EMOTIONAL, (
            f"Failed to detect emotion: {phrase}"
        )
        assert detector.get_emotional_word_count() > 0

    @pytest.mark.parametrize("text", [
        "The company reported $5 billion in revenue.",
        "CEO John Smith confirmed the merger.",
        "Stock prices increased by 2.5% today.",
        "The Federal Reserve raised rates by 0.25%.",
        "Unemployment fell to 3.5% in January.",
    ])
    def test_false_positive_resistance(self, to_sentences, text):
        """Test that analyzers don't produce false positives on clean text."""
        sentence = _single(to_sentences, text)

        FillerDetector().analyze([sentence])
        assert sentence.keep is True, f"False filler positive: {text}"

        SpeculationStripper().analyze([sentence])
        assert sentence.keep is True, f"False speculation positive: {text}"

        EmotionalDetector().analyze([sentence])
        assert sentence.keep is True, f"False emotional positive: {text}"
        assert sentence.text == text
        assert sentence.category == SentenceCategory.FACTUAL


class TestAnalyzerEdgeCases:
    """Tests for analyzer edge cases."""

    @pytest.fixture
    def all_analyzers(self):
        """Create all analyzers."""
        return [
            FillerDetector(),
            SpeculationStripper(),
            EmotionalDetector(),
            SourceValidator(),
            QuoteIsolator(),
        ]

    def _assert_handles(self, analyzers, sentences: list[Sentence]) -> None:
        count = len(sentences)
        for analyzer in analyzers:
            result = analyzer.analyze(sentences)
            assert isinstance(result, list)
            assert len(result) == count

    def test_empty_input(self, all_analyzers, to_sentences):
        """Test that all analyzers handle empty input."""
        assert to_sentences("") == []
        self._assert_handles(all_analyzers, [])

    def test_single_word_input(self, all_analyzers, to_sentences):
        """Test that all analyzers handle single word input."""
        self._assert_handles(all_analyzers, to_sentences("Hello"))

    def test_very_long_input(self, all_analyzers, to_sentences):
        """Test that all analyzers handle very long input."""
        sentences = to_sentences("The company announced results. " * 100)
        assert len(sentences) == 100
        self._assert_handles(all_analyzers, sentences)

    def test_special_characters(self, all_analyzers, to_sentences):
        """Test that all analyzers handle special characters."""
        text = "Stock rose 15% to $123.45! CEO: 'Amazing!' #success"
        self._assert_handles(all_analyzers, to_sentences(text))

    def test_unicode_input(self, all_analyzers, to_sentences):
        """Test that all analyzers handle unicode."""
        text = "会社は利益を発表した。L'entreprise a annoncé des bénéfices."
        self._assert_handles(all_analyzers, to_sentences(text))

    def test_mixed_content(self, all_analyzers, to_sentences):
        """Test analyzers on mixed content with all patterns."""
        text = (
            "Here's what you need to know about this shocking story. "
            "The company could potentially announce changes, sources say. "
            '"This is significant," said CEO John Smith. '
            "Stay tuned for more unprecedented developments."
        )
        sentences = to_sentences(text)
        self._assert_handles(all_analyzers, sentences)

        # The attributed quote survives; the hook and speculation do not
        kept = [s.text for s in sentences if s.keep]
        assert kept == ['"This is significant," said CEO John Smith.']
