"""Tests for the FillerDetector analyzer."""

import pytest

from newsdigest.analyzers.filler import FillerDetector
from newsdigest.core.result import RemovalReason, Sentence, SentenceCategory


def _make_sentence(text: str, index: int = 0, entities: list | None = None,
                   density_score: float = 0.5) -> Sentence:
    """Helper to create a Sentence with minimal required fields."""
    return Sentence(
        text=text,
        index=index,
        tokens=text.split(),
        pos_tags=["NOUN"] * len(text.split()),
        entities=entities or [],
        density_score=density_score,
        keep=True,
    )


class TestFillerDetector:
    """Tests for FillerDetector analyzer."""

    @pytest.fixture
    def detector(self):
        """Create a FillerDetector instance."""
        return FillerDetector()

    def test_initialization(self, detector):
        """Test detector initializes correctly."""
        assert detector is not None
        assert hasattr(detector, "analyze")
        assert detector.enabled is True

    @pytest.mark.parametrize("text", [
        "Here's what you need to know about this story.",
        "What happened next will surprise you.",
        "Stay tuned for more updates on this developing story.",
        "But that's not the whole story here.",
        "You won't believe what happened at the summit.",
        "Everything you need to know about the vote.",
        "Here's why that matters for the economy.",
        "Read on to find out the real story.",
        "Don't miss this critical update on the situation.",
        "This is a breaking development in the case.",
    ])
    def test_engagement_hooks_detected(self, detector, text):
        """Test that engagement hook patterns are flagged as filler."""
        sentences = [_make_sentence(text)]
        result = detector.analyze(sentences)
        assert result[0].keep is False
        assert result[0].removal_reason == RemovalReason.ENGAGEMENT_HOOK.value

    @pytest.mark.parametrize("text,entities", [
        ("The Federal Reserve raised interest rates by 0.25%.",
         [{"text": "Federal Reserve", "label": "ORG"}]),
        ("Revenue increased 15% year over year to $10 billion.",
         [{"text": "$10 billion", "label": "MONEY"}]),
        ('"The economy is strong," said Chair Powell.',
         [{"text": "Powell", "label": "PERSON"}]),
        ("Apple Inc. reported earnings of $3.89 per share.",
         [{"text": "Apple Inc.", "label": "ORG"}]),
    ])
    def test_factual_sentences_kept(self, detector, text, entities):
        """Test that factual sentences with entities are not flagged."""
        sentences = [_make_sentence(text, entities=entities)]
        result = detector.analyze(sentences)
        assert result[0].keep is True

    def test_empty_sentence_list(self, detector):
        """Test handling of empty sentence list."""
        result = detector.analyze([])
        assert result == []

    def test_already_removed_sentence_skipped(self, detector):
        """Test that sentences already marked for removal are not re-analyzed."""
        sentence = _make_sentence("Here's what you need to know.")
        sentence.keep = False
        sentence.removal_reason = RemovalReason.SPECULATION.value
        result = detector.analyze([sentence])
        # Should keep original removal reason, not overwrite
        assert result[0].removal_reason == RemovalReason.SPECULATION.value

    def test_multiple_sentences_mixed(self, detector):
        """Test batch with both filler and factual sentences."""
        sentences = [
            _make_sentence("Here's what you need to know.", index=0),
            _make_sentence(
                "The Federal Reserve held rates at 5.25%.", index=1,
                entities=[{"text": "Federal Reserve", "label": "ORG"}],
            ),
            _make_sentence("Stay tuned for more updates.", index=2),
        ]
        result = detector.analyze(sentences)
        assert result[0].keep is False  # filler
        assert result[1].keep is True   # factual
        assert result[2].keep is False  # filler

    def test_short_sentence_without_entities_removed(self, detector):
        """Test that very short sentences with no entities are flagged."""
        sentences = [_make_sentence("So yes.", entities=[], density_score=0.0)]
        result = detector.analyze(sentences)
        assert result[0].keep is False

    def test_short_sentence_with_quote_preserved(self, detector):
        """Test that short sentences containing quotes are preserved."""
        sentences = [_make_sentence('"Yes."', entities=[])]
        result = detector.analyze(sentences)
        assert result[0].keep is True

    def test_engagement_hook_count(self, detector):
        """Test counting engagement hooks across multiple sentences."""
        sentences = [
            _make_sentence("Here's what you need to know.", index=0),
            _make_sentence("The GDP grew 3%.", index=1,
                           entities=[{"text": "GDP", "label": "ORG"}]),
            _make_sentence("Stay tuned for more.", index=2),
        ]
        count = detector.get_engagement_hook_count(sentences)
        assert count == 2

    def test_disabled_detector_passes_through(self):
        """Test that a disabled detector does not modify sentences."""
        detector = FillerDetector(config={"enabled": False})
        sentences = [_make_sentence("Here's what you need to know.")]
        result = detector.analyze(sentences)
        assert result[0].keep is True

    def test_category_set_to_filler(self, detector):
        """Test that flagged sentences get FILLER category."""
        sentences = [_make_sentence("What happened next will surprise you.")]
        result = detector.analyze(sentences)
        assert result[0].category == SentenceCategory.FILLER
