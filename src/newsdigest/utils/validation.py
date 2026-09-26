"""Input validation and sanitation utilities for NewsDigest.

This module provides comprehensive input validation to ensure:
- URLs are valid and safe
- Text content is properly sanitized
- Configuration values are within expected ranges
- User inputs don't contain malicious content
"""

import html
import ipaddress
import re
import socket
from typing import Any
from urllib.parse import urlparse


# =============================================================================
# CONSTANTS
# =============================================================================

# Maximum lengths for various inputs
MAX_URL_LENGTH = 2048
MAX_TEXT_LENGTH = 1_000_000  # 1MB of text
MAX_TITLE_LENGTH = 500
MAX_FEED_ITEMS = 100

# Allowed URL schemes
ALLOWED_SCHEMES = {"http", "https"}

# Hostnames that always refer to the local machine or internal services
BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
}
BLOCKED_HOST_SUFFIXES = (".localhost", ".local", ".internal", ".onion")

# Elements whose content is executable or never article text
DANGEROUS_TAGS = (
    "script",
    "style",
    "iframe",
    "frame",
    "frameset",
    "object",
    "embed",
    "applet",
)
_DANGEROUS_TAG_ALT = "|".join(DANGEROUS_TAGS)

# Dangerous HTML patterns to remove. They are applied repeatedly until the
# input stops changing, so fragments reassembled by one pass (e.g.
# "<scr<script></script>ipt>") are caught by the next.
DANGEROUS_HTML_PATTERNS = [
    # Dangerous elements together with their content
    rf"<({_DANGEROUS_TAG_ALT})\b[^>]*>.*?</\1\s*>",
    # Unclosed, void (<embed>) or stray dangerous tags
    rf"</?({_DANGEROUS_TAG_ALT})\b[^>]*>",
    # Event handler attributes like onclick="..."
    r"""[\s"'/]on\w+\s*=\s*("[^"]*"|'[^']*'|[^\s>]*)""",
    # Inline styles, which can run code via expression() or behavior:
    r"""[\s"'/]style\s*=\s*("[^"]*"|'[^']*'|[^\s>]*)""",
    r"javascript:",
    r"vbscript:",
    r"data:text/html",
]
_DANGEROUS_HTML_REGEXES = [
    re.compile(p, re.IGNORECASE | re.DOTALL) for p in DANGEROUS_HTML_PATTERNS
]

# Tags (but not bare "<" / ">" used as comparison operators in prose)
_HTML_TAG_PATTERN = re.compile(r"</?[a-zA-Z!][^<>]*>")


# =============================================================================
# CUSTOM EXCEPTIONS
# =============================================================================


class ValidationError(ValueError):
    """Raised when input validation fails."""

    def __init__(self, message: str, field: str | None = None) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            field: Optional field name that failed validation.
        """
        super().__init__(message)
        self.field = field
        self.message = message


class SanitizationError(ValueError):
    """Raised when content cannot be safely sanitized."""

    pass


# =============================================================================
# URL VALIDATION
# =============================================================================


def _parse_ip(host: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    """Parse a host as an IP address, including legacy IPv4 notations.

    Resolvers accept forms such as "2130706433", "0x7f.1" or "127.1" for
    127.0.0.1, so those must be recognised to stop them bypassing checks.
    """
    try:
        return ipaddress.ip_address(host)
    except ValueError:
        pass
    if re.fullmatch(r"[0-9a-fx.]+", host):
        try:
            return ipaddress.IPv4Address(socket.inet_aton(host))
        except OSError:
            return None
    return None


def is_private_host(hostname: str) -> bool:
    """Check whether a hostname points at a local or non-public network.

    Covers loopback, private, link-local (including cloud metadata
    endpoints), carrier-grade NAT, reserved, multicast and unspecified
    addresses for both IPv4 and IPv6, plus well-known local hostnames.
    Hostnames are not resolved, so a public name whose DNS points at a
    private address is not detected here.

    Args:
        hostname: Hostname or IP literal (without brackets or port).

    Returns:
        True if the host must not be fetched.
    """
    host = hostname.strip().strip("[]").rstrip(".").lower()
    if not host:
        return True
    if host in BLOCKED_HOSTNAMES or host.endswith(BLOCKED_HOST_SUFFIXES):
        return True

    ip = _parse_ip(host)
    if ip is None:
        return False
    if isinstance(ip, ipaddress.IPv6Address):
        ip = _embedded_ipv4(ip) or ip
    return not ip.is_global or ip.is_multicast


# IPv6 ranges that carry an IPv4 address in their low 32 bits
_IPV4_EMBEDDING_NETWORKS = (
    ipaddress.IPv6Network("::/96"),  # IPv4-compatible (deprecated)
    ipaddress.IPv6Network("64:ff9b::/96"),  # NAT64 well-known prefix
)


def _embedded_ipv4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """Return the IPv4 address an IPv6 address stands for, if any."""
    if ip.ipv4_mapped:
        return ip.ipv4_mapped
    if ip.sixtofour:
        return ip.sixtofour
    if any(ip in network for network in _IPV4_EMBEDDING_NETWORKS):
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def validate_url(url: str, allow_private: bool = False) -> tuple[bool, str | None]:
    """Validate a URL for safety and correctness.

    Args:
        url: URL to validate.
        allow_private: Whether to allow private/local network URLs.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if not url or not isinstance(url, str):
        return False, "URL must be a non-empty string"

    url = url.strip()

    # Check length
    if len(url) > MAX_URL_LENGTH:
        return False, f"URL exceeds maximum length of {MAX_URL_LENGTH}"

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    # Check scheme
    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        return False, f"URL scheme must be one of: {', '.join(ALLOWED_SCHEMES)}"

    # Check for host
    if not parsed.netloc:
        return False, "URL must have a valid host"

    # Check for blocked hosts (unless allow_private)
    if not allow_private and is_private_host(parsed.hostname or ""):
        return False, "URL host is not allowed (private/local network)"

    # Check for suspicious patterns
    if ".." in url or "\\" in url:
        return False, "URL contains suspicious path patterns"

    return True, None


def validate_url_strict(url: str) -> str:
    """Validate URL and raise exception if invalid.

    Args:
        url: URL to validate.

    Returns:
        Validated URL.

    Raises:
        ValidationError: If URL is invalid.
    """
    is_valid, error = validate_url(url)
    if not is_valid:
        raise ValidationError(error or "Invalid URL", field="url")
    return url.strip()


def is_valid_url(url: str) -> bool:
    """Quick check if URL is valid.

    Args:
        url: URL to check.

    Returns:
        True if valid.
    """
    is_valid, _ = validate_url(url)
    return is_valid


# =============================================================================
# TEXT VALIDATION & SANITATION
# =============================================================================


def sanitize_text(
    text: str,
    max_length: int | None = None,
    strip_html: bool = True,
    normalize_whitespace: bool = True,
) -> str:
    """Sanitize text content for safe processing.

    Args:
        text: Text to sanitize.
        max_length: Maximum allowed length (truncates if exceeded).
        strip_html: Whether to remove HTML tags.
        normalize_whitespace: Whether to normalize whitespace.

    Returns:
        Sanitized text.
    """
    if not text:
        return ""

    if not isinstance(text, str):
        text = str(text)

    # Apply max length
    if max_length and len(text) > max_length:
        text = text[:max_length]

    if strip_html:
        # Decode entities first so encoded markup ("&lt;script&gt;") is
        # stripped too instead of being turned back into live tags
        text = html.unescape(text)
        text = _remove_dangerous_html(text)
        text = _HTML_TAG_PATTERN.sub("", text)

    # Remove null bytes and other control characters (except newlines/tabs)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)

    # Normalize whitespace if requested
    if normalize_whitespace:
        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        # Collapse multiple spaces (but preserve newlines)
        text = re.sub(r"[^\S\n]+", " ", text)
        # Collapse multiple newlines to max 2
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = text.strip()

    return text


def sanitize_html(html_content: str, max_length: int | None = None) -> str:
    """Sanitize HTML content by removing dangerous elements.

    Args:
        html_content: HTML to sanitize.
        max_length: Maximum allowed length.

    Returns:
        Sanitized HTML.
    """
    if not html_content:
        return ""

    if max_length and len(html_content) > max_length:
        html_content = html_content[:max_length]

    # Remove null bytes first so they cannot split tag names
    html_content = html_content.replace("\x00", "")

    return _remove_dangerous_html(html_content)


def _remove_dangerous_html(content: str) -> str:
    """Strip dangerous elements and attributes until none remain.

    Args:
        content: HTML or text that may contain markup.

    Returns:
        Content with dangerous markup removed.
    """
    previous = None
    while previous != content:
        previous = content
        for regex in _DANGEROUS_HTML_REGEXES:
            content = regex.sub(" ", content)
    return content


def validate_text_content(
    text: str,
    min_length: int = 0,
    max_length: int = MAX_TEXT_LENGTH,
    require_content: bool = True,
) -> tuple[bool, str | None]:
    """Validate text content.

    Args:
        text: Text to validate.
        min_length: Minimum required length.
        max_length: Maximum allowed length.
        require_content: Whether to require non-whitespace content.

    Returns:
        Tuple of (is_valid, error_message).
    """
    if text is None:
        return False, "Text cannot be None"

    if not isinstance(text, str):
        return False, "Text must be a string"

    if len(text) < min_length:
        return False, f"Text must be at least {min_length} characters"

    if len(text) > max_length:
        return False, f"Text exceeds maximum length of {max_length}"

    if require_content and not text.strip():
        return False, "Text must contain non-whitespace content"

    return True, None


# =============================================================================
# CONFIGURATION VALIDATION
# =============================================================================


def validate_range(
    value: Any,
    min_val: float | None = None,
    max_val: float | None = None,
    name: str = "value",
) -> float:
    """Validate a numeric value is within range.

    Args:
        value: Value to validate.
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.
        name: Name for error messages.

    Returns:
        Validated value as float.

    Raises:
        ValidationError: If validation fails.
    """
    try:
        num_value = float(value)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"{name} must be a number: {e}", field=name) from e

    if min_val is not None and num_value < min_val:
        raise ValidationError(f"{name} must be at least {min_val}", field=name)

    if max_val is not None and num_value > max_val:
        raise ValidationError(f"{name} must be at most {max_val}", field=name)

    return num_value


def validate_positive_int(
    value: Any, name: str = "value", allow_zero: bool = False
) -> int:
    """Validate value is a positive integer.

    Args:
        value: Value to validate.
        name: Name for error messages.
        allow_zero: If True, zero is allowed. Default is False.

    Returns:
        Validated value as int.

    Raises:
        ValidationError: If validation fails.
    """
    try:
        int_value = int(value)
    except (TypeError, ValueError) as e:
        raise ValidationError(f"{name} must be an integer: {e}", field=name) from e

    if allow_zero:
        if int_value < 0:
            raise ValidationError(f"{name} must be non-negative", field=name)
    elif int_value <= 0:
        raise ValidationError(f"{name} must be positive", field=name)

    return int_value


def validate_enum(value: Any, allowed: list[Any], name: str = "value") -> Any:
    """Validate value is one of allowed values.

    Args:
        value: Value to validate.
        allowed: List of allowed values.
        name: Name for error messages.

    Returns:
        Validated value.

    Raises:
        ValidationError: If validation fails.
    """
    if value not in allowed:
        raise ValidationError(
            f"{name} must be one of: {', '.join(str(v) for v in allowed)}",
            field=name,
        )
    return value


def validate_extraction_mode(mode: str) -> str:
    """Validate extraction mode (how aggressively content is compressed).

    Args:
        mode: Mode to validate.

    Returns:
        Validated mode.

    Raises:
        ValidationError: If mode is invalid.
    """
    allowed = ["conservative", "standard", "aggressive"]
    validated: str = validate_enum(mode, allowed, "extraction mode")
    return validated


def validate_handling_mode(mode: str, name: str = "handling mode") -> str:
    """Validate how a content category is handled (keep, flag or remove).

    Args:
        mode: Mode to validate.
        name: Setting name for error messages.

    Returns:
        Validated mode.

    Raises:
        ValidationError: If mode is invalid.
    """
    allowed = ["keep", "flag", "remove"]
    validated: str = validate_enum(mode, allowed, name)
    return validated


# =============================================================================
# RSS/FEED VALIDATION
# =============================================================================


def validate_feed_url(url: str) -> str:
    """Validate an RSS/Atom feed URL.

    Args:
        url: Feed URL to validate.

    Returns:
        Validated URL.

    Raises:
        ValidationError: If URL is invalid.
    """
    url = validate_url_strict(url)

    # Additional feed-specific checks could go here
    # (e.g., checking Content-Type header)

    return url


def validate_feed_item_count(count: int) -> int:
    """Validate feed item count.

    Args:
        count: Number of items.

    Returns:
        Validated count.

    Raises:
        ValidationError: If count is invalid.
    """
    count = validate_positive_int(count, "item_count")

    if count > MAX_FEED_ITEMS:
        raise ValidationError(
            f"Item count cannot exceed {MAX_FEED_ITEMS}",
            field="item_count",
        )

    return count


# =============================================================================
# ARTICLE VALIDATION
# =============================================================================


def validate_article_content(content: str) -> str:
    """Validate and sanitize article content.

    Args:
        content: Article content to validate.

    Returns:
        Validated and sanitized content.

    Raises:
        ValidationError: If content is invalid.
    """
    is_valid, error = validate_text_content(
        content,
        min_length=10,
        max_length=MAX_TEXT_LENGTH,
        require_content=True,
    )

    if not is_valid:
        raise ValidationError(error or "Invalid content", field="content")

    return sanitize_text(content, strip_html=False)


def validate_article_title(title: str) -> str:
    """Validate and sanitize article title.

    Args:
        title: Title to validate.

    Returns:
        Validated and sanitized title.

    Raises:
        ValidationError: If title is invalid.
    """
    if not title:
        return ""

    is_valid, error = validate_text_content(
        title,
        max_length=MAX_TITLE_LENGTH,
        require_content=False,
    )

    if not is_valid:
        raise ValidationError(error or "Invalid title", field="title")

    return sanitize_text(title, max_length=MAX_TITLE_LENGTH)
