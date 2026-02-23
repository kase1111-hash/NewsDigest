"""Tests for the EmotionalDetector analyzer."""

import pytest

from newsdigest.analyzers.emotional import EmotionalDetector
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


class TestEmotionalDetector:
    """Tests for EmotionalDetector analyzer."""

    @pytest.fixture
    def detector(self):
        """Create an EmotionalDetector instance."""
        return EmotionalDetector()

    def test_initialization(self, detector):
        """Test detector initializes correctly."""
        assert detector is not None
        assert hasattr(detector, "analyze")
        assert detector.enabled is True
        assert detector.mode == "remove"

    @pytest.mark.parametrize("text", [
        "In a shocking development, the CEO resigned.",
        "The stunning announcement caught investors off guard.",
        "This unprecedented move signals a major shift.",
        "The bombshell revelation rocked the industry.",
        "This extraordinary development changes everything.",
        "The devastating impact was felt across markets.",
        "In a dramatic reversal, the board voted no.",
        "The sensational claims were widely reported.",
        "A staggering loss of $50 billion was reported.",
        # Note: "alarmed" (past tense) is NOT in the word lists — only "alarming" is.
    ])
    def test_emotional_language_detected(self, detector, text):
        """Test that sentences with emotional activation words score above threshold."""
        sentences = [_make_sentence(text)]
        result = detector.analyze(sentences)
        assert result[0].emotional_score >= detector.threshold
        assert result[0].category == SentenceCategory.EMOTIONAL

    @pytest.mark.parametrize("text", [
        "The Federal Reserve announced a rate increase.",
        "Revenue increased 15% year over year to $10 billion.",
        "The company reported quarterly earnings on Tuesday.",
        "Congress passed the bill with a 60-40 vote.",
        "The population grew by 2.3% according to census data.",
    ])
    def test_neutral_sentences_kept(self, detector, text):
        """Test that neutral factual sentences are not flagged as emotional."""
        sentences = [_make_sentence(text)]
        result = detector.analyze(sentences)
        assert result[0].keep is True
        assert result[0].emotional_score < detector.threshold

    def test_multiple_emotional_words_detected(self, detector):
        """Test that sentences with multiple emotional words all get flagged."""
        sentences = [_make_sentence(
            "The shocking unprecedented scandal was devastating."
        )]
        detector.analyze(sentences)
        # 3 emotional words out of 6 total -> high score
        assert sentences[0].emotional_score >= detector.threshold
        assert sentences[0].category == SentenceCategory.EMOTIONAL

    def test_empty_sentence_list(self, detector):
        """Test handling of empty sentence list."""
        result = detector.analyze([])
        assert result == []

    def test_empty_text_sentence(self, detector):
        """Test handling of sentence with empty text."""
        sentences = [_make_sentence("")]
        result = detector.analyze(sentences)
        assert result[0].keep is True
        assert result[0].emotional_score == 0.0

    def test_already_removed_sentence_skipped(self, detector):
        """Test that sentences already marked for removal are skipped."""
        sentence = _make_sentence("In a shocking turn, everything changed.")
        sentence.keep = False
        sentence.removal_reason = RemovalReason.SPECULATION.value
        result = detector.analyze([sentence])
        assert result[0].removal_reason == RemovalReason.SPECULATION.value

    def test_sentence_with_only_emotional_words_stays_when_removal_fails(self, detector):
        """Test behavior when emotional words have trailing punctuation.

        remove_words uses \\b regex anchors which don't match after punctuation
        like '!', so words like 'Shocking!' are not removed from the text. The
        sentence keeps its content and stays.
        """
        sentences = [_make_sentence("Shocking! Devastating! Unprecedented!")]
        result = detector.analyze(sentences)
        assert result[0].category == SentenceCategory.EMOTIONAL
        # The words fail to strip due to punctuation in the token, so text remains
        assert result[0].keep is True

    def test_emotional_word_stripped_from_clean_sentence(self, detector):
        """Test that emotional words without punctuation are stripped from text."""
        sentences = [_make_sentence(
            "The shocking scandal rocked the technology industry."
        )]
        result = detector.analyze(sentences)
        assert result[0].category == SentenceCategory.EMOTIONAL
        # "shocking" should be removed, factual content remains
        assert "shocking" not in result[0].text.lower()
        assert result[0].keep is True

    def test_words_removed_counter(self, detector):
        """Test that the removed word counter increments correctly."""
        sentences = [
            _make_sentence("The shocking scandal was unprecedented.", index=0),
            _make_sentence("GDP grew 3%.", index=1),
        ]
        detector.analyze(sentences)
        assert detector.get_emotional_word_count() >= 1

    def test_disabled_detector_passes_through(self):
        """Test that a disabled detector does not modify sentences."""
        detector = EmotionalDetector(config={"enabled": False})
        sentences = [_make_sentence("The shocking news was unprecedented.")]
        result = detector.analyze(sentences)
        assert result[0].keep is True
        assert result[0].emotional_score == 0.0

    def test_flag_mode_does_not_remove(self):
        """Test that flag mode marks category but keeps the sentence."""
        detector = EmotionalDetector(config={"mode": "flag"})
        sentences = [_make_sentence("The shocking development was unprecedented.")]
        result = detector.analyze(sentences)
        assert result[0].category == SentenceCategory.EMOTIONAL
        # In flag mode, text should not be modified
        assert "shocking" in result[0].text.lower()

    @pytest.mark.parametrize("text", [
        "a " * 500 + "shocking event occurred.",
        "",
        "   ",
        "12345 67890",
    ])
    def test_boundary_inputs(self, detector, text):
        """Test that boundary inputs don't crash the analyzer."""
        sentences = [_make_sentence(text)]
        result = detector.analyze(sentences)
        assert len(result) == 1
