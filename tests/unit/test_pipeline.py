"""Tests for the NLP analysis pipeline."""

import pytest

from newsdigest.core.pipeline import AnalysisPipeline, normalize_text


@pytest.fixture(scope="module")
def pipeline() -> AnalysisPipeline:
    """Create a pipeline (the spaCy model is shared across instances)."""
    return AnalysisPipeline()


class TestNormalizeText:
    """Tests for text normalization before NLP."""

    def test_unwraps_hard_wrapped_lines(self) -> None:
        """Test lines inside a paragraph are joined with single spaces."""
        text = "The Federal\n    Reserve held\n  rates steady."
        assert normalize_text(text) == "The Federal Reserve held rates steady."

    def test_keeps_paragraph_breaks(self) -> None:
        """Test blank lines still separate paragraphs."""
        text = "  First paragraph.\n\n\n   Second\n paragraph.  "
        assert normalize_text(text) == "First paragraph.\n\nSecond paragraph."

    def test_empty(self) -> None:
        """Test whitespace-only text normalizes to nothing."""
        assert normalize_text(" \n\n \t ") == ""


class TestPipelineProcess:
    """Tests for sentence splitting and annotation."""

    def test_sentence_text_has_no_layout_whitespace(self, pipeline) -> None:
        """Test indentation and line breaks don't leak into sentence text."""
        sentences = pipeline.process(
            "Here's what you need\n        to know about the decision."
        )
        assert [s.text for s in sentences] == [
            "Here's what you need to know about the decision."
        ]

    def test_heading_not_merged_into_next_sentence(self, pipeline) -> None:
        """Test a paragraph without end punctuation stays its own sentence."""
        sentences = pipeline.process("Acme Corp results\n\nAcme reported $4 billion.")
        assert [s.text for s in sentences] == [
            "Acme Corp results",
            "Acme reported $4 billion.",
        ]

    def test_closing_quote_stays_with_quote(self, pipeline) -> None:
        """Test a multi-sentence quote keeps its closing mark."""
        text = (
            'Powell said, "The decision was unanimous. We believe rates are '
            'appropriate."\n\nSources said more cuts could come.'
        )
        sentences = pipeline.process(text)

        assert sentences[1].text.endswith('appropriate."')
        assert sentences[2].text.startswith("Sources")
        assert [s.index for s in sentences] == list(range(len(sentences)))

    def test_spacy_model_shared(self) -> None:
        """Test pipelines reuse one loaded model instead of reloading it."""
        assert AnalysisPipeline().nlp is AnalysisPipeline().nlp
