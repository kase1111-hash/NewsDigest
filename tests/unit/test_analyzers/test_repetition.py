"""Tests for the RepetitionCollapser analyzer."""

from newsdigest.analyzers.repetition import RepetitionCollapser
from newsdigest.core.result import RemovalReason, Sentence


def _make_sentence(text: str, index: int) -> Sentence:
    """Helper to create a Sentence with minimal required fields."""
    return Sentence(text=text, index=index)


class TestRepetitionCollapser:
    """Tests for RepetitionCollapser."""

    def test_repeated_sentence_collapsed(self) -> None:
        """Test that a restated sentence is removed, keeping the first."""
        sentences = [
            _make_sentence("The central bank held interest rates steady today.", 0),
            _make_sentence("Unemployment fell to a record low in March.", 1),
            _make_sentence("The central bank held interest rates steady today.", 2),
        ]
        RepetitionCollapser().analyze(sentences)

        assert [s.keep for s in sentences] == [True, True, False]
        assert sentences[2].removal_reason == RemovalReason.BACKGROUND_REPEAT.value

    def test_long_chain_of_repeats_does_not_recurse(self) -> None:
        """Test thousands of identical sentences don't overflow the stack."""
        sentences = [
            _make_sentence("The company reported strong quarterly results today.", i)
            for i in range(2000)
        ]
        collapser = RepetitionCollapser()
        collapser.analyze(sentences)

        assert sentences[0].keep is True
        assert collapser.get_collapsed_count() == 1999
