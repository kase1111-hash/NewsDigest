"""Text processing utilities for NewsDigest.

This module provides shared text processing functions used across multiple
analyzers and components. Centralizing these utilities ensures consistency
and reduces code duplication (DRY principle).
"""

import re  # noqa: I001
from collections.abc import Set as AbstractSet

# Punctuation characters to strip from words (deduplicated set)
# Includes standard ASCII and common Unicode punctuation
PUNCTUATION_CHARS = (
    ".,!?;:'\"()-[]{}\u00ab\u00bb\u201c\u201d\u2018\u2019\u2026\u2014\u2013"
)


# =============================================================================
# COMMON STOP WORDS
# =============================================================================

STOP_WORDS: frozenset[str] = frozenset(
    {
        # Articles
        "a",
        "an",
        "the",
        # Be verbs
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        # Have verbs
        "have",
        "has",
        "had",
        # Do verbs
        "do",
        "does",
        "did",
        # Modal verbs
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        # Prepositions
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "over",
        "out",
        "up",
        "down",
        "off",
        "about",
        "around",
        # Conjunctions
        "and",
        "but",
        "or",
        "nor",
        "so",
        "yet",
        "both",
        "either",
        "neither",
        # Pronouns
        "i",
        "me",
        "my",
        "mine",
        "myself",
        "you",
        "your",
        "yours",
        "yourself",
        "he",
        "him",
        "his",
        "himself",
        "she",
        "her",
        "hers",
        "herself",
        "it",
        "its",
        "itself",
        "we",
        "us",
        "our",
        "ours",
        "ourselves",
        "they",
        "them",
        "their",
        "theirs",
        "themselves",
        "this",
        "that",
        "these",
        "those",
        "who",
        "whom",
        "whose",
        "which",
        "what",
        # Adverbs/others
        "not",
        "only",
        "own",
        "same",
        "than",
        "too",
        "very",
        "just",
        "also",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "any",
        "some",
        "no",
        "other",
        # Common verbs
        "said",
        "says",
        "told",
        "asked",
        "added",
        "noted",
        "stated",
    }
)


# =============================================================================
# TEXT CLEANING UTILITIES
# =============================================================================


def strip_punctuation(word: str) -> str:
    """Remove leading/trailing punctuation from a word.

    Args:
        word: Word to clean.

    Returns:
        Word with punctuation stripped.
    """
    # Strip characters one by one from start and end
    result = word
    while result and result[0] in PUNCTUATION_CHARS:
        result = result[1:]
    while result and result[-1] in PUNCTUATION_CHARS:
        result = result[:-1]
    return result


def normalize_whitespace(text: str) -> str:
    """Normalize multiple whitespace to single spaces.

    Args:
        text: Text to normalize.

    Returns:
        Text with normalized whitespace.
    """
    return re.sub(r"\s+", " ", text).strip()


def fix_punctuation_spacing(text: str) -> str:
    """Fix spacing around punctuation after word removal.

    Args:
        text: Text to fix.

    Returns:
        Text with corrected punctuation spacing.
    """
    # Remove space before punctuation
    text = re.sub(r"\s+([.,!?;:])", r"\1", text)
    # Remove duplicate punctuation
    text = re.sub(r"([.,!?;:])\s*([.,!?;:])", r"\1", text)
    return text


def get_content_words(
    text: str, stop_words: AbstractSet[str] | None = None
) -> list[str]:
    """Extract content words (non-stop words) from text.

    Args:
        text: Text to process.
        stop_words: Custom stop words set. Uses default if None.

    Returns:
        List of content words.
    """
    if stop_words is None:
        stop_words = STOP_WORDS

    words = text.lower().split()
    return [
        strip_punctuation(w)
        for w in words
        if strip_punctuation(w) not in stop_words and len(strip_punctuation(w)) > 2
    ]


def word_count(text: str) -> int:
    """Count words in text.

    Args:
        text: Text to count words in.

    Returns:
        Number of words.
    """
    return len(text.split())


# =============================================================================
# PATTERN MATCHING UTILITIES
# =============================================================================


def compile_patterns(
    patterns: list[str], flags: int = re.IGNORECASE
) -> list[re.Pattern[str]]:
    """Compile a list of regex patterns.

    Args:
        patterns: List of regex pattern strings.
        flags: Regex flags to apply.

    Returns:
        List of compiled Pattern objects.
    """
    return [re.compile(p, flags) for p in patterns]


def match_any_pattern(text: str, patterns: list[re.Pattern[str]]) -> bool:
    """Check if text matches any of the patterns.

    Args:
        text: Text to search.
        patterns: List of compiled patterns.

    Returns:
        True if any pattern matches.
    """
    return any(pattern.search(text) for pattern in patterns)


def find_all_matches(text: str, patterns: list[re.Pattern[str]]) -> list[str]:
    """Find all pattern matches in text.

    Args:
        text: Text to search.
        patterns: List of compiled patterns.

    Returns:
        List of matched strings.
    """
    matches: list[str] = []
    for pattern in patterns:
        matches.extend(match.group() for match in pattern.finditer(text))
    return matches


def word_in_set(word: str, word_set: set[str]) -> bool:
    """Check if word (cleaned) is in a set.

    Args:
        word: Word to check.
        word_set: Set of words to check against.

    Returns:
        True if word is in set.
    """
    return strip_punctuation(word).lower() in word_set


# =============================================================================
# SENTENCE ANALYSIS UTILITIES
# =============================================================================


def has_meaningful_content(text: str, min_content_words: int = 2) -> bool:
    """Check if text has meaningful content (non-stop words).

    Args:
        text: Text to check.
        min_content_words: Minimum content words required.

    Returns:
        True if sufficient content words exist.
    """
    content_words = get_content_words(text)
    return len(content_words) >= min_content_words


def calculate_word_overlap(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity between two texts.

    Args:
        text1: First text.
        text2: Second text.

    Returns:
        Jaccard similarity score (0.0-1.0).
    """
    words1 = set(get_content_words(text1))
    words2 = set(get_content_words(text2))

    if not words1 or not words2:
        return 0.0

    intersection = words1 & words2
    union = words1 | words2

    return len(intersection) / len(union) if union else 0.0


def has_quote(text: str) -> bool:
    """Check if text contains a quote.

    Args:
        text: Text to check.

    Returns:
        True if quote markers found.
    """
    quote_chars = ('"', "\u201c", "\u201d", "'", "\u2018", "\u2019")
    return any(c in text for c in quote_chars)


def has_numbers(text: str) -> bool:
    """Check if text contains numbers.

    Args:
        text: Text to check.

    Returns:
        True if digits found.
    """
    return any(c.isdigit() for c in text)


def is_all_caps(text: str, threshold: float = 0.3) -> bool:
    """Check if text has excessive all-caps words.

    Args:
        text: Text to check.
        threshold: Ratio of caps words to trigger (0.0-1.0).

    Returns:
        True if caps ratio exceeds threshold.
    """
    words = text.split()
    if not words:
        return False

    caps_words = [w for w in words if w.isupper() and len(w) > 2]
    return len(caps_words) / len(words) > threshold


def has_excessive_punctuation(text: str) -> bool:
    """Check for excessive punctuation (!!!, ???).

    Args:
        text: Text to check.

    Returns:
        True if excessive punctuation found.
    """
    return bool(re.search(r"[!?]{2,}", text))


# =============================================================================
# TEXT EXTRACTION UTILITIES
# =============================================================================


def extract_quoted_content(text: str) -> list[str]:
    """Extract all quoted content from text.

    Args:
        text: Text to process.

    Returns:
        List of quoted strings.
    """
    quotes = []

    # Double quotes (straight and curly)
    quotes.extend(re.findall(r'"([^"]+)"', text))
    quotes.extend(re.findall("\u201c([^\u201d]+)\u201d", text))

    # Single quotes (only if substantial content)
    single_quotes = re.findall(r"'([^']{10,})'", text)
    quotes.extend(single_quotes)

    return quotes


def remove_words(text: str, words: list[str]) -> str:
    """Remove specific words from text.

    Args:
        text: Original text.
        words: Words to remove.

    Returns:
        Text with words removed.
    """
    result = text
    for word in words:
        pattern = rf"\b{re.escape(word)}\b"
        result = re.sub(pattern, "", result, flags=re.IGNORECASE)

    result = normalize_whitespace(result)
    result = fix_punctuation_spacing(result)

    return result
