"""HTML cleaner for NewsDigest."""

import re
from typing import Any

from bs4 import BeautifulSoup, Comment, Tag
from bs4.element import NavigableString, PreformattedString


# Elements to completely remove
REMOVE_ELEMENTS: set[str] = {
    "script",
    "style",
    "noscript",
    "iframe",
    "embed",
    "object",
    "svg",
    "canvas",
    "video",
    "audio",
    "map",
    "form",
    "input",
    "button",
    "select",
    "textarea",
}

# Elements typically containing non-content
NON_CONTENT_ELEMENTS: set[str] = {
    "nav",
    "header",
    "footer",
    "aside",
    "menu",
    "menuitem",
}

# Classes/IDs that typically indicate non-content
NON_CONTENT_PATTERNS: list[str] = [
    r"nav",
    r"menu",
    r"sidebar",
    r"widget",
    # "ad"/"ads" only as a whole word: bare "ad" is inside headline, lead...
    r"(?<![a-z])ads?(?![a-z])",
    r"advert",
    r"sponsor",
    r"promo",
    r"banner",
    r"social",
    r"share",
    r"comment",
    r"footer",
    r"header",
    r"masthead",
    r"breadcrumb",
    r"pagination",
    r"related",
    r"recommend",
    r"popular",
    r"trending",
    r"subscribe",
    r"newsletter",
    r"signup",
    r"login",
    r"modal",
    r"popup",
    r"overlay",
    r"cookie",
    r"consent",
    r"gdpr",
]


# Elements whose text forms one paragraph of output
BLOCK_ELEMENTS: set[str] = {
    "p",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "blockquote",
    "pre",
    "figcaption",
    "dt",
    "dd",
    "td",
    "th",
}

# Elements whose text continues the surrounding paragraph
INLINE_ELEMENTS: set[str] = {
    "a",
    "abbr",
    "b",
    "bdi",
    "bdo",
    "cite",
    "code",
    "data",
    "del",
    "dfn",
    "em",
    "i",
    "ins",
    "kbd",
    "mark",
    "q",
    "s",
    "samp",
    "small",
    "span",
    "strong",
    "sub",
    "sup",
    "time",
    "u",
    "var",
    "wbr",
}

# Content containers never removed by class/id heuristics: a page's
# <body class="has-ads"> or <article class="post has-comments"> is the content
PROTECTED_ELEMENTS: set[str] = {"html", "body", "main", "article"}


class HTMLCleaner:
    """Cleans HTML and extracts text content.

    Removes:
    - Scripts, styles, iframes
    - Navigation, headers, footers
    - Ads, sidebars
    - Comments
    - Non-content elements based on class/id patterns
    """

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        """Initialize HTML cleaner.

        Args:
            config: Configuration dictionary.
        """
        self.config = config or {}
        self._non_content_pattern = re.compile(
            "|".join(NON_CONTENT_PATTERNS), re.IGNORECASE
        )
        self.preserve_links = self.config.get("preserve_links", False)
        self.preserve_images = self.config.get("preserve_images", False)

    def clean(self, html: str) -> str:
        """Remove non-content elements and extract clean text.

        Args:
            html: Raw HTML content.

        Returns:
            Cleaned text content.
        """
        if not html:
            return ""

        # Parse HTML
        soup = BeautifulSoup(html, "lxml")

        # Remove comments
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

        # Remove script, style, and other non-content elements
        for element in soup.find_all(REMOVE_ELEMENTS):
            element.decompose()

        # Remove non-content structural elements
        for element in soup.find_all(NON_CONTENT_ELEMENTS):
            element.decompose()

        # Remove elements with non-content class/id patterns
        self._remove_by_attribute(soup)

        # Get text
        text = self._extract_text(soup)

        # Clean up whitespace
        text = self._clean_whitespace(text)

        return text

    def _remove_by_attribute(self, soup: BeautifulSoup) -> None:
        """Remove elements based on class/id attributes.

        Args:
            soup: BeautifulSoup object to modify in place.
        """
        for element in soup.find_all(True):  # True matches all tags
            if not isinstance(element, Tag) or element.name in PROTECTED_ELEMENTS:
                continue

            # Check class attribute
            classes = element.get("class", "")
            class_str = " ".join(classes) if isinstance(classes, list) else str(classes)

            # Check id attribute
            elem_id = element.get("id", "") or ""

            # Check role attribute
            role = element.get("role", "") or ""

            # Remove if matches non-content pattern
            combined = f"{class_str} {elem_id} {role}"
            if self._non_content_pattern.search(combined):
                element.decompose()

    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract text from cleaned soup.

        Args:
            soup: Cleaned BeautifulSoup object.

        Returns:
            Extracted text.
        """
        # Get main content area if identifiable
        main = (
            soup.find("main")
            or soup.find("article")
            or soup.find(None, attrs={"role": "main"})
            or soup.find(class_=re.compile(r"content|article|post|entry"))
        )

        target = main if main else soup

        # Line breaks separate text within a block; keep them as whitespace
        for br in target.find_all("br"):
            br.replace_with("\n")

        # Extract text with paragraph preservation
        paragraphs: list[str] = []
        self._collect_paragraphs(target, paragraphs)

        # Deduplicate adjacent identical paragraphs
        unique_paragraphs: list[str] = []
        for p in paragraphs:
            if not unique_paragraphs or p != unique_paragraphs[-1]:
                unique_paragraphs.append(p)

        return "\n\n".join(unique_paragraphs)

    def _collect_paragraphs(self, node: Tag, paragraphs: list[str]) -> None:
        """Collect each block of text once, in document order.

        Block elements become one paragraph each; inline elements and loose
        text are joined with their neighbours; other containers are walked.

        Args:
            node: Element to walk.
            paragraphs: List that paragraphs are appended to.
        """
        inline_parts: list[str] = []

        def flush() -> None:
            text = " ".join("".join(inline_parts).split())
            if text:
                paragraphs.append(text)
            inline_parts.clear()

        for child in node.children:
            if isinstance(child, PreformattedString):
                # Comments, doctypes, CDATA and the like are not content
                continue
            if isinstance(child, NavigableString):
                inline_parts.append(str(child))
            elif isinstance(child, Tag):
                if child.name in INLINE_ELEMENTS:
                    inline_parts.append(child.get_text())
                elif child.name in BLOCK_ELEMENTS:
                    flush()
                    text = " ".join(child.get_text().split())
                    if text:
                        paragraphs.append(text)
                else:
                    flush()
                    self._collect_paragraphs(child, paragraphs)
        flush()

    def _clean_whitespace(self, text: str) -> str:
        """Clean up whitespace in text.

        Args:
            text: Text to clean.

        Returns:
            Cleaned text.
        """
        # Replace multiple spaces with single space
        text = re.sub(r"[ \t]+", " ", text)

        # Replace multiple newlines with double newline (paragraph break)
        text = re.sub(r"\n\s*\n+", "\n\n", text)

        # Strip leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]
        text = "\n".join(lines)

        return text.strip()

    def get_links(self, html: str) -> list[dict[str, Any]]:
        """Extract links from HTML.

        Args:
            html: HTML content.

        Returns:
            List of link dictionaries with href and text.
        """
        soup = BeautifulSoup(html, "lxml")
        links = []

        for a in soup.find_all("a", href=True):
            href = a["href"]
            text = a.get_text(strip=True)
            if href and text:
                links.append({"href": href, "text": text})

        return links

    def get_images(self, html: str) -> list[dict[str, Any]]:
        """Extract images from HTML.

        Args:
            html: HTML content.

        Returns:
            List of image dictionaries with src and alt.
        """
        soup = BeautifulSoup(html, "lxml")
        images = []

        for img in soup.find_all("img", src=True):
            src = img["src"]
            alt = img.get("alt", "")
            if src:
                images.append({"src": src, "alt": alt})

        return images
