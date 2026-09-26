"""Tests for validation utilities."""

import pytest

from newsdigest.utils.validation import (
    ValidationError,
    is_valid_url,
    sanitize_html,
    sanitize_text,
    validate_enum,
    validate_extraction_mode,
    validate_positive_int,
    validate_range,
    validate_text_content,
    validate_url,
    validate_url_strict,
)


class TestURLValidation:
    """Tests for URL validation functions."""

    def test_valid_http_url(self):
        """Test validation of valid HTTP URL."""
        is_valid, error = validate_url("http://example.com")
        assert is_valid is True
        assert error is None

    def test_valid_https_url(self):
        """Test validation of valid HTTPS URL."""
        is_valid, error = validate_url("https://example.com/path")
        assert is_valid is True
        assert error is None

    def test_invalid_url_no_scheme(self):
        """Test validation of URL without scheme."""
        is_valid, error = validate_url("example.com")
        assert is_valid is False
        assert error is not None

    def test_invalid_url_empty(self):
        """Test validation of empty URL."""
        is_valid, _error = validate_url("")
        assert is_valid is False

    def test_invalid_url_ftp(self):
        """Test validation of FTP URL (not allowed)."""
        is_valid, _error = validate_url("ftp://example.com")
        assert is_valid is False

    def test_url_with_port(self):
        """Test validation of URL with port."""
        is_valid, _error = validate_url("https://example.com:8080/path")
        assert is_valid is True

    def test_url_with_query_params(self):
        """Test validation of URL with query parameters."""
        is_valid, _error = validate_url("https://example.com?foo=bar&baz=1")
        assert is_valid is True

    def test_private_network_blocked_by_default(self):
        """Test that private network URLs are blocked by default."""
        is_valid, error = validate_url("http://192.168.1.1/admin")
        assert is_valid is False
        assert "private" in error.lower() if error else False

    def test_localhost_blocked_by_default(self):
        """Test that localhost is blocked by default."""
        is_valid, _error = validate_url("http://localhost/admin")
        assert is_valid is False

    def test_private_network_allowed_when_enabled(self):
        """Test that private network URLs are allowed when enabled."""
        is_valid, _error = validate_url("http://192.168.1.1/admin", allow_private=True)
        assert is_valid is True


class TestURLStrictValidation:
    """Tests for strict URL validation."""

    def test_strict_valid_url(self):
        """Test strict validation of valid URL."""
        result = validate_url_strict("https://example.com")
        assert result == "https://example.com"

    def test_strict_invalid_raises(self):
        """Test that strict validation raises on invalid URL."""
        with pytest.raises(ValidationError):
            validate_url_strict("not-a-url")


class TestIsValidURL:
    """Tests for is_valid_url convenience function."""

    def test_is_valid_url_true(self):
        """Test is_valid_url returns True for valid URL."""
        assert is_valid_url("https://example.com") is True

    def test_is_valid_url_false(self):
        """Test is_valid_url returns False for invalid URL."""
        assert is_valid_url("not-a-url") is False


class TestHTMLSanitization:
    """Tests for HTML sanitization."""

    def test_remove_script_tags(self):
        """Test removal of script tags."""
        html = "<p>Hello</p><script>alert('xss')</script>"
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "alert" not in result

    def test_remove_style_tags(self):
        """Test removal of style tags."""
        html = "<p>Hello</p><style>body { display: none; }</style>"
        result = sanitize_html(html)
        assert "<style>" not in result

    def test_remove_event_handlers(self):
        """Test removal of event handlers."""
        html = '<div onclick="alert(1)">Click me</div>'
        result = sanitize_html(html)
        assert "onclick" not in result

    def test_remove_iframe(self):
        """Test removal of iframe tags."""
        html = '<p>Hello</p><iframe src="http://evil.com"></iframe>'
        result = sanitize_html(html)
        assert "<iframe>" not in result

    def test_preserve_text_content(self):
        """Test that text content is preserved."""
        html = "<p>This is important news content.</p>"
        result = sanitize_html(html)
        assert "This is important news content" in result

    def test_max_length_truncation(self):
        """Test max length truncation."""
        html = "<p>A" * 1000 + "</p>"
        result = sanitize_html(html, max_length=100)
        assert len(result) <= 100

    def test_empty_string(self):
        """Test handling of empty string."""
        result = sanitize_html("")
        assert result == ""


class TestTextSanitization:
    """Tests for text sanitization."""

    def test_normalize_whitespace(self):
        """Test normalization of whitespace."""
        text = "Hello   world\n\n\n  test"
        result = sanitize_text(text)
        assert "   " not in result

    def test_remove_null_bytes(self):
        """Test removal of null bytes."""
        text = "Hello\x00World"
        result = sanitize_text(text)
        assert "\x00" not in result

    def test_empty_string(self):
        """Test handling of empty string."""
        result = sanitize_text("")
        assert result == ""


class TestTextContentValidation:
    """Tests for text content validation."""

    def test_valid_text(self):
        """Test validation of valid text."""
        text = "This is a valid news article with sufficient content."
        is_valid, _error = validate_text_content(text)
        assert is_valid is True

    def test_empty_text(self):
        """Test validation of empty text."""
        is_valid, _error = validate_text_content("")
        assert is_valid is False

    def test_too_short_text(self):
        """Test validation of text that's too short."""
        is_valid, _error = validate_text_content("Hi", min_length=10)
        assert is_valid is False

    def test_too_long_text(self):
        """Test validation of text that's too long."""
        text = "A" * 1000
        is_valid, _error = validate_text_content(text, max_length=100)
        assert is_valid is False


class TestRangeValidation:
    """Tests for range validation."""

    def test_value_in_range(self):
        """Test value within range."""
        result = validate_range(5, 0, 10, "test")
        assert result == 5

    def test_value_below_range(self):
        """Test value below range raises."""
        with pytest.raises(ValidationError):
            validate_range(-1, 0, 10, "test")

    def test_value_above_range(self):
        """Test value above range raises."""
        with pytest.raises(ValidationError):
            validate_range(11, 0, 10, "test")

    def test_value_at_boundary(self):
        """Test value at range boundary."""
        result = validate_range(0, 0, 10, "test")
        assert result == 0
        result = validate_range(10, 0, 10, "test")
        assert result == 10


class TestPositiveIntValidation:
    """Tests for positive integer validation."""

    def test_positive_int(self):
        """Test validation of positive integer."""
        result = validate_positive_int(5, "count")
        assert result == 5

    def test_zero_rejected(self):
        """Test that zero is rejected."""
        with pytest.raises(ValidationError):
            validate_positive_int(0, "count")

    def test_negative_rejected(self):
        """Test that negative numbers are rejected."""
        with pytest.raises(ValidationError):
            validate_positive_int(-1, "count")

    def test_zero_allowed_when_specified(self):
        """Test that zero can be allowed."""
        result = validate_positive_int(0, "count", allow_zero=True)
        assert result == 0


class TestEnumValidation:
    """Tests for enum validation."""

    def test_valid_enum_value(self):
        """Test validation of valid enum value."""
        result = validate_enum("apple", ["apple", "banana", "cherry"], "fruit")
        assert result == "apple"

    def test_invalid_enum_value(self):
        """Test validation of invalid enum value raises."""
        with pytest.raises(ValidationError):
            validate_enum("orange", ["apple", "banana", "cherry"], "fruit")

    def test_case_sensitivity(self):
        """Test that enum validation is case-sensitive."""
        with pytest.raises(ValidationError):
            validate_enum("APPLE", ["apple", "banana"], "fruit")


class TestExtractionModeValidation:
    """Tests for extraction mode validation."""

    def test_standard_mode(self):
        """Test validation of standard mode."""
        result = validate_extraction_mode("standard")
        assert result == "standard"

    def test_aggressive_mode(self):
        """Test validation of aggressive mode."""
        result = validate_extraction_mode("aggressive")
        assert result == "aggressive"

    def test_conservative_mode(self):
        """Test validation of conservative mode."""
        result = validate_extraction_mode("conservative")
        assert result == "conservative"

    def test_invalid_mode(self):
        """Test validation of invalid mode raises."""
        with pytest.raises(ValidationError):
            validate_extraction_mode("invalid")
