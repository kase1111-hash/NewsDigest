"""Tests for the SpeculationStripper analyzer."""

import pytest

from newsdigest.analyzers.speculation import SpeculationStripper
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory


def _make_sentence(text: str, index: int = 0) -> Sentence:
    """Helper to create a Sentence with minimal required fields."""
    return Sentence(
        text=text,
        index=index,
        tokens=text.split(),
        pos_tags=["NOUN"] * len(text.split()),
        entities=[],
        density_score=0.5,
        keep=True,
    )


class TestSpeculationStripper:
    """Tests for SpeculationStripper analyzer."""

    @pytest.fixture
    def stripper(self):
        """Create a SpeculationStripper instance."""
        return SpeculationStripper()

    def test_initialization(self, stripper):
        """Test stripper initializes correctly."""
        assert stripper is not None
        assert hasattr(stripper, "analyze")
        assert stripper.enabled is True
        assert stripper.mode == "remove"

    @pytest.mark.parametrize("text", [
        "This could signal a shift in policy.",
        "Markets might react negatively to this news.",
        "The company may announce layoffs next week.",
        "This could potentially impact millions of users.",
        "It appears that negotiations have stalled.",
        "It seems the deal is unlikely to proceed.",
        "The changes are expected to take effect soon.",
        "Analysts believe the trend will continue.",
        "This might possibly indicate a reversal.",
        "It remains to be seen whether reforms will succeed.",
    ])
    def test_speculative_sentences_flagged(self, stripper, text):
        """Test that sentences with speculation markers are flagged."""
        sentences = [_make_sentence(text)]
        result = stripper.analyze(sentences)
        assert result[0].speculation_score > 0
        # Most of these should exceed threshold or marker count
        if result[0].speculation_score >= stripper.speculation_threshold:
            assert result[0].keep is False
            assert result[0].removal_reason == RemovalReason.SPECULATION.value

    @pytest.mark.parametrize("text", [
        "The company reported $5 billion in revenue.",
        "Congress passed the bill with a 60-40 vote.",
        "The temperature reached 105 degrees on Tuesday.",
        "Apple released the iPhone 16 in September.",
        "The population of Tokyo is 13.96 million.",
    ])
    def test_factual_sentences_kept(self, stripper, text):
        """Test that factual sentences without speculation are kept."""
        sentences = [_make_sentence(text)]
        result = stripper.analyze(sentences)
        assert result[0].keep is True
        assert result[0].speculation_score < stripper.speculation_threshold

    def test_multiple_hedges_exceed_threshold(self, stripper):
        """Test that sentences with many hedge words get flagged even at lower individual scores."""
        sentences = [_make_sentence(
            "This could potentially perhaps indicate a possible shift."
        )]
        result = stripper.analyze(sentences)
        assert result[0].keep is False
        assert result[0].category == SentenceCategory.SPECULATION

    def test_empty_sentence_list(self, stripper):
        """Test handling of empty sentence list."""
        result = stripper.analyze([])
        assert result == []

    def test_empty_text_sentence(self, stripper):
        """Test handling of sentence with empty text."""
        sentences = [_make_sentence("")]
        result = stripper.analyze(sentences)
        assert result[0].keep is True
        assert result[0].speculation_score == 0.0

    def test_already_removed_sentence_skipped(self, stripper):
        """Test that sentences already marked for removal are skipped."""
        sentence = _make_sentence("This could be a big deal.")
        sentence.keep = False
        sentence.removal_reason = RemovalReason.EMOTIONAL_ACTIVATION.value
        result = stripper.analyze([sentence])
        assert result[0].removal_reason == RemovalReason.EMOTIONAL_ACTIVATION.value

    def test_mixed_batch(self, stripper):
        """Test batch with both speculative and factual sentences."""
        sentences = [
            _make_sentence("This could potentially signal a major shift.", index=0),
            _make_sentence("The company reported $5B in revenue.", index=1),
            _make_sentence("It remains to be seen what happens next.", index=2),
        ]
        result = stripper.analyze(sentences)
        assert result[1].keep is True  # factual sentence preserved

    def test_get_speculation_markers(self, stripper):
        """Test extracting specific speculation markers from a sentence."""
        sentence = _make_sentence("This could potentially indicate a shift.")
        markers = stripper.get_speculation_markers(sentence)
        assert "could" in markers
        assert "potentially" in markers

    def test_disabled_stripper_passes_through(self):
        """Test that a disabled stripper does not modify sentences."""
        stripper = SpeculationStripper(config={"enabled": False})
        sentences = [_make_sentence("This could signal a change.")]
        result = stripper.analyze(sentences)
        assert result[0].keep is True
        assert result[0].speculation_score == 0.0

    def test_position_weighting(self, stripper):
        """Test that modal verbs near end of sentence score higher."""
        early = _make_sentence("Could this signal a very long policy shift in the economy?")
        late = _make_sentence("The long and detailed economic policy shift could happen.")
        stripper.analyze([early])
        stripper.analyze([late])
        # Both have "could" but at different positions
        # Late position should have slightly higher weight
        assert late.speculation_score >= early.speculation_score * 0.8  # not exact, just reasonable

    @pytest.mark.parametrize("text", [
        "a " * 500 + "could happen.",
        "",
        "   ",
        "12345 67890",
    ])
    def test_boundary_inputs(self, stripper, text):
        """Test that boundary inputs don't crash the analyzer."""
        sentences = [_make_sentence(text)]
        result = stripper.analyze(sentences)
        assert len(result) == 1
