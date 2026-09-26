"""Tests for the TextIngestor."""

import pytest

from newsdigest.ingestors.text import TextIngestor


@pytest.fixture
def ingestor() -> TextIngestor:
    """Create a text ingestor."""
    return TextIngestor()


class TestTitleDetection:
    """Tests for splitting a headline off pasted text."""

    def test_standalone_headline_becomes_title(self, ingestor) -> None:
        """Test a short first line followed by a blank line is the title."""
        article = ingestor.from_text("Fed Holds Rates Steady\n\nThe Fed held rates.")
        assert article.title == "Fed Holds Rates Steady"
        assert article.content == "The Fed held rates."

    @pytest.mark.parametrize("text", [
        # Hard-wrapped first sentence
        "In a surprise move, the Federal\nReserve held rates.\n\nMore text.",
        # First paragraph is a sentence, not a headline
        "Google reported revenue of $75.3 billion.\n\nCloud grew 28%.",
        # Single paragraph
        "Apple reported revenue of $90 billion. Cook was pleased.",
    ])
    def test_body_text_is_never_taken_as_title(self, ingestor, text) -> None:
        """Test that no part of the body is lost to title detection."""
        article = ingestor.from_text(text)
        assert article.title is None
        assert article.content == text

    def test_explicit_title_kept(self, ingestor) -> None:
        """Test a provided title is used and the content is untouched."""
        article = ingestor.from_text("Headline\n\nBody.", title="Given")
        assert article.title == "Given"
        assert article.content == "Headline\n\nBody."


class TestSanitization:
    """Tests for cleaning pasted content."""

    def test_markup_and_scripts_removed(self, ingestor) -> None:
        """Test pasted HTML is reduced to its text."""
        article = ingestor.from_text(
            "Revenue <b>rose</b> 5%.<script>alert('x')</script> "
            '<img src=x onerror="evil()">Costs < $3M.'
        )
        assert article.content == "Revenue rose 5%. Costs < $3M."

    def test_entity_encoded_markup_removed(self, ingestor) -> None:
        """Test encoded tags are not decoded back into live markup."""
        article = ingestor.from_text("AT&amp;T said &lt;script&gt;x&lt;/script&gt; ok.")
        assert article.content == "AT&T said ok."
