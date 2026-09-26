"""Tests for HTML cleaning and article extraction."""

from newsdigest.parsers.article import ArticleExtractor
from newsdigest.parsers.html import HTMLCleaner


class TestHTMLCleaner:
    """Tests for HTMLCleaner text extraction."""

    def test_inline_markup_not_duplicated(self) -> None:
        """Test text inside <b>/<a> appears once, within its paragraph."""
        html = (
            "<article><p>Revenue rose <b>12%</b> to <a href='/x'>$4 billion</a>."
            "</p><p>Costs fell.</p></article>"
        )
        assert HTMLCleaner().clean(html) == (
            "Revenue rose 12% to $4 billion.\n\nCosts fell."
        )

    def test_blocks_and_loose_text(self) -> None:
        """Test headings, list items, line breaks and loose div text."""
        html = (
            "<main><h1>Title</h1><div>Loose <em>inline</em> text.</div>"
            "<p>Line one<br>line two</p><ul><li>First</li><li>Second</li></ul></main>"
        )
        assert HTMLCleaner().clean(html) == (
            "Title\n\nLoose inline text.\n\nLine one line two\n\nFirst\n\nSecond"
        )

    def test_ad_pattern_matches_whole_words_only(self) -> None:
        """Test "ad" in class names like headline/lead doesn't remove content."""
        html = (
            "<article><h2 class='headline'>Headline</h2>"
            "<div class='article-lead'>Lead paragraph.</div>"
            "<div class='ad-slot'>Buy now</div><div class='ads'>Sponsored</div>"
            "</article>"
        )
        assert HTMLCleaner().clean(html) == "Headline\n\nLead paragraph."

    def test_content_containers_never_removed(self) -> None:
        """Test class heuristics can't delete the page or article itself."""
        html = (
            "<html><body class='has-ads'><article class='post has-comments'>"
            "<p>The actual story.</p></article></body></html>"
        )
        assert HTMLCleaner().clean(html) == "The actual story."


class TestArticleExtractor:
    """Tests for ArticleExtractor."""

    def test_headline_not_repeated_in_content(self) -> None:
        """Test the page headline is the title, not the first sentence."""
        html = (
            "<html><head><title>Acme posts record revenue</title></head><body>"
            "<article><h1>Acme posts record revenue</h1>"
            "<p>Acme Corp reported revenue of $4.2 billion on Friday.</p>"
            "<p>Chief executive Maria Lopez said growth was broad.</p>"
            "</article></body></html>"
        )
        article = ArticleExtractor().extract(html, "https://example.com/a")

        assert article.title == "Acme posts record revenue"
        assert article.content.startswith("Acme Corp reported revenue")
