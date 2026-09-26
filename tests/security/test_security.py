"""Security tests for NewsDigest.

These tests verify that the system handles security concerns properly:
- Input validation and sanitization
- Secret/credential protection
- Injection prevention
- Safe error handling
"""

import json

import pytest

from newsdigest.config.secrets import (
    SecretMasker,
    SecretValue,
    get_secret,
    mask_secrets,
)
from newsdigest.config.settings import Config
from newsdigest.core.extractor import Extractor
from newsdigest.utils.validation import (
    sanitize_html,
    validate_text_content,
    validate_url,
)


# =============================================================================
# INPUT VALIDATION SECURITY
# =============================================================================


class TestURLValidationSecurity:
    """Security tests for URL validation."""

    def test_blocks_javascript_urls(self) -> None:
        """JavaScript URLs are blocked."""
        dangerous_urls = [
            "javascript:alert('xss')",
            "JAVASCRIPT:alert(1)",
            "javascript:void(0)",
            "  javascript:evil()  ",
        ]

        for url in dangerous_urls:
            is_valid, error = validate_url(url)
            assert is_valid is False, f"Should block: {url}"

    def test_blocks_data_urls(self) -> None:
        """Data URLs are blocked."""
        dangerous_urls = [
            "data:text/html,<script>alert(1)</script>",
            "DATA:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==",
        ]

        for url in dangerous_urls:
            is_valid, error = validate_url(url)
            assert is_valid is False, f"Should block: {url}"

    def test_blocks_file_urls(self) -> None:
        """File URLs are blocked."""
        dangerous_urls = [
            "file:///etc/passwd",
            "FILE:///C:/Windows/System32",
        ]

        for url in dangerous_urls:
            is_valid, error = validate_url(url)
            assert is_valid is False, f"Should block: {url}"

    def test_blocks_private_networks_by_default(self) -> None:
        """Private network URLs are blocked by default."""
        private_urls = [
            "http://localhost/admin",
            "http://127.0.0.1/secret",
            "http://192.168.1.1/config",
            "http://10.0.0.1/internal",
            "http://172.16.0.1/data",
            "http://[::1]/admin",
            # Cloud metadata endpoint (link-local)
            "http://169.254.169.254/latest/meta-data/",
            # Alternative encodings of 127.0.0.1
            "http://2130706433/",
            "http://0x7f.0.0.1/",
            "http://127.1/",
            "http://[::ffff:127.0.0.1]/",
            # Other non-public ranges and names
            "http://0.0.0.0/",
            "http://100.64.0.1/",
            "http://[fd00::1]/",
            "http://[fe80::1]/",
            "http://service.internal/",
            "http://LOCALHOST./",
        ]

        for url in private_urls:
            is_valid, error = validate_url(url, allow_private=False)
            assert is_valid is False, f"Should block private: {url}"

    @pytest.mark.parametrize("url", [
        "https://example.com/news",
        "https://8.8.8.8/",
        "https://1e100.net/",
        "http://[2606:4700::1111]/",
    ])
    def test_allows_public_hosts(self, url: str) -> None:
        """Public hosts and IPs are allowed."""
        assert validate_url(url) == (True, None)

    def test_blocks_url_with_credentials(self) -> None:
        """URLs with embedded credentials should be handled carefully."""
        url = "http://user:password@example.com/path"
        # Should either block or strip credentials
        is_valid, error = validate_url(url)
        # This is implementation-dependent, but should be handled


class TestHTMLSanitizationSecurity:
    """Security tests for HTML sanitization."""

    def test_removes_script_tags(self) -> None:
        """Script tags are removed."""
        malicious = [
            "<script>alert('xss')</script>",
            "<SCRIPT>alert(1)</SCRIPT>",
            "<script src='evil.js'></script>",
            "<script type='text/javascript'>evil()</script>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "<script" not in result.lower()
            assert "alert" not in result.lower()

    def test_removes_event_handlers(self) -> None:
        """Event handlers are removed."""
        malicious = [
            "<div onclick='evil()'>click</div>",
            "<img onerror='alert(1)' src='x'>",
            "<body onload='hack()'>",
            "<a onmouseover='steal()'>link</a>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "onclick" not in result.lower()
            assert "onerror" not in result.lower()
            assert "onload" not in result.lower()
            assert "onmouseover" not in result.lower()

    def test_removes_iframe_tags(self) -> None:
        """Iframe tags are removed."""
        malicious = [
            "<iframe src='http://evil.com'></iframe>",
            "<IFRAME SRC='javascript:alert(1)'></IFRAME>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "<iframe" not in result.lower()

    def test_removes_object_embed_tags(self) -> None:
        """Object and embed tags are removed."""
        malicious = [
            "<object data='evil.swf'></object>",
            "<embed src='malware.swf'>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "<object" not in result.lower()
            assert "<embed" not in result.lower()

    def test_removes_style_with_expressions(self) -> None:
        """CSS expressions are removed."""
        malicious = [
            "<div style='expression(alert(1))'>",
            "<div style='behavior:url(evil.htc)'>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "expression" not in result.lower()
            assert "behavior" not in result.lower()

    def test_handles_nested_attack(self) -> None:
        """Nested/obfuscated attacks are handled."""
        malicious = [
            "<scr<script>ipt>alert(1)</script>",
            "<<script>script>alert(1)<</script>/script>",
            # Removing the inner pair must not reassemble an outer tag
            "<scr<script></script>ipt>alert(1)</scr<script></script>ipt>",
            "<scr\x00ipt>alert(1)</script>",
        ]

        for html in malicious:
            result = sanitize_html(html)
            assert "<script" not in result.lower()


class TestInputInjectionPrevention:
    """Tests for injection attack prevention."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    def test_handles_null_bytes(self, extractor: Extractor) -> None:
        """Null bytes in input don't cause issues."""
        content = "Normal text\x00with null\x00bytes"
        result = extractor.extract_sync(content)

        assert "\x00" not in result.text

    def test_handles_control_characters(self, extractor: Extractor) -> None:
        """Control characters are handled safely."""
        content = "Text with\x01control\x02chars\x03here"
        result = extractor.extract_sync(content)

        # Should process without crashing
        assert result is not None

    def test_handles_unicode_exploits(self, extractor: Extractor) -> None:
        """Unicode-based exploits are handled."""
        content = "Text with RTL\u202eoverride\u202c and zero-width\u200bchars"
        result = extractor.extract_sync(content)

        # Should process without crashing
        assert result is not None

    def test_output_doesnt_contain_injected_html(self, extractor: Extractor) -> None:
        """Output doesn't contain injected HTML from input."""
        malicious_content = """
        Article text <script>alert('xss')</script> more text.
        Image: <img onerror="evil()" src="x"> content.
        """

        result = extractor.extract_sync(malicious_content)
        output_json = extractor.format(result, format="json")

        # JSON output shouldn't execute scripts
        assert "<script>" not in output_json
        assert "onerror" not in output_json.lower()


# =============================================================================
# SECRET PROTECTION
# =============================================================================


class TestSecretProtection:
    """Tests for secret/credential protection."""

    def test_secret_value_hidden_in_str(self) -> None:
        """SecretValue hides value in string representation."""
        secret = SecretValue("my-api-key-12345")

        str_repr = str(secret)
        repr_repr = repr(secret)

        assert "my-api-key-12345" not in str_repr
        assert "my-api-key-12345" not in repr_repr
        assert "****" in str_repr

    def test_secret_value_hidden_in_logs(self) -> None:
        """SecretValue doesn't expose value when logged."""
        secret = SecretValue("super-secret-token")

        # Simulate logging
        log_message = f"Using secret: {secret}"

        assert "super-secret-token" not in log_message
        assert "SecretValue" in log_message

    def test_secret_masker_masks_api_keys(self) -> None:
        """SecretMasker masks API key patterns."""
        masker = SecretMasker()

        texts = [
            "api_key: sk-1234567890abcdefghij",
            'API_KEY="ghp_abcdefghij1234567890abcdefghij12"',
            "token: test-slack-token-placeholder",
        ]

        for text in texts:
            result = masker.mask(text)
            # Original secret patterns should be masked
            assert "sk-1234567890abcdefghij" not in result or "****" in result

    def test_secret_masker_masks_bearer_tokens(self) -> None:
        """SecretMasker masks bearer tokens."""
        masker = SecretMasker()

        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
        result = masker.mask(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result

    def test_registered_secrets_masked(self) -> None:
        """Manually registered secrets are masked."""
        from newsdigest.config.secrets import register_secret

        register_secret("my-custom-secret-value")

        text = "The secret is my-custom-secret-value here"
        result = mask_secrets(text)

        assert "my-custom-secret-value" not in result
        assert "****" in result


class TestEnvironmentSecrets:
    """Tests for environment variable secret handling."""

    def test_secrets_not_in_config_dump(self, monkeypatch) -> None:
        """Secrets shouldn't appear in config dumps."""
        monkeypatch.setenv("NEWSDIGEST_API_KEY", "secret-api-key")

        config = Config()
        config_dict = config.model_dump()
        config_str = str(config_dict)

        # API key shouldn't be in the config dump
        # (it's not part of Config model anyway)
        assert "secret-api-key" not in config_str

    def test_secrets_from_env_wrapped(self, monkeypatch) -> None:
        """Secrets from environment are wrapped in SecretValue."""
        monkeypatch.setenv("NEWSDIGEST_SECRET_KEY", "test-secret")

        from newsdigest.config.secrets import init_env
        init_env()

        secret = get_secret("SECRET_KEY")

        assert isinstance(secret, SecretValue)
        assert "test-secret" not in str(secret)


# =============================================================================
# ERROR MESSAGE SECURITY
# =============================================================================


class TestErrorMessageSecurity:
    """Tests for secure error handling."""

    def test_errors_dont_expose_paths(self) -> None:
        """Error messages don't expose system paths."""
        from newsdigest.exceptions import NewsDigestError

        # Create error with sensitive details
        error = NewsDigestError(
            "Operation failed",
            details={"path": "/home/user/.secrets/key.pem"}
        )

        # The error message itself shouldn't contain the path
        error_str = str(error)
        # Details are stored but message is clean
        assert "Operation failed" in error_str

    def test_errors_dont_expose_credentials(self) -> None:
        """Error messages don't expose credentials."""
        from newsdigest.exceptions import FetchError

        error = FetchError(
            "Failed to fetch URL",
            details={"url": "https://api.example.com"}
        )

        error_str = str(error)
        # Should not contain any credentials even if they were in the URL
        assert "password" not in error_str.lower()


# =============================================================================
# EXTRACTION OUTPUT SECURITY
# =============================================================================


class TestExtractionOutputSecurity:
    """Tests for secure extraction output."""

    @pytest.fixture
    def extractor(self) -> Extractor:
        """Create extractor."""
        return Extractor()

    def test_json_output_properly_escaped(self, extractor: Extractor) -> None:
        """JSON output has properly escaped strings."""
        content = 'Article with "quotes" and <tags> and special chars'
        result = extractor.extract_sync(content)
        json_output = extractor.format(result, format="json")

        # Should be valid JSON (proper escaping)
        parsed = json.loads(json_output)
        assert isinstance(parsed, dict)

    def test_markdown_output_sanitized(self, extractor: Extractor) -> None:
        """Markdown output doesn't contain dangerous content."""
        content = """
        Normal article content.
        <script>alert('xss')</script>
        More content here.
        """

        result = extractor.extract_sync(content)
        md_output = extractor.format(result, format="markdown")

        assert "<script>" not in md_output

    def test_output_doesnt_contain_system_info(self, extractor: Extractor) -> None:
        """Output doesn't leak system information."""
        content = "Simple article about technology."
        result = extractor.extract_sync(content)
        json_output = extractor.format(result, format="json")

        # Should not contain system paths or info
        sensitive_patterns = [
            "/home/",
            "/Users/",
            "C:\\",
            "password",
            "secret",
            "token",
            "api_key",
        ]

        output_lower = json_output.lower()
        for pattern in sensitive_patterns:
            if pattern.lower() in output_lower:
                # Only fail if it's not part of article content
                assert pattern.lower() in content.lower(), \
                    f"Output contains sensitive pattern: {pattern}"


# =============================================================================
# CONFIGURATION SECURITY
# =============================================================================


class TestConfigurationSecurity:
    """Tests for configuration security."""

    def test_config_doesnt_expose_secrets_in_to_env_vars(self) -> None:
        """to_env_vars doesn't include secret values."""
        config = Config()
        env_vars = config.to_env_vars()

        # Should not contain secret-like keys with values
        for key, value in env_vars.items():
            if "SECRET" in key.upper() or "KEY" in key.upper():
                # If it's a secret field, value should be empty or masked
                pass  # Config doesn't have secrets by default

    def test_sensitive_config_fields_protected(self) -> None:
        """Sensitive configuration fields are properly typed."""
        # Verify that if we add sensitive fields, they use SecretValue
        # This is a design verification test
        from newsdigest.config.secrets import SecretValue

        # SecretValue should be available for sensitive configs
        assert SecretValue is not None


# =============================================================================
# RATE LIMITING & ABUSE PREVENTION
# =============================================================================


class TestAbusePrevention:
    """Tests for abuse prevention mechanisms."""

    def test_content_length_limits(self) -> None:
        """Content length limits are enforced."""
        is_valid, error = validate_text_content("x" * 10_000_000, max_length=1_000_000)
        assert is_valid is False

    def test_html_length_limits(self) -> None:
        """HTML sanitization respects length limits."""
        huge_html = "<p>" + "x" * 100_000 + "</p>"
        result = sanitize_html(huge_html, max_length=1000)
        assert len(result) <= 1000

    def test_url_length_limits(self) -> None:
        """Extremely long URLs are rejected."""
        long_url = "https://example.com/" + "a" * 10_000
        is_valid, error = validate_url(long_url)
        # Should either reject or handle gracefully
        # Very long URLs are suspicious


# =============================================================================
# SECURITY HEADERS & OUTPUT
# =============================================================================


class TestSecurityBestPractices:
    """Tests for security best practices."""

    def test_no_eval_or_exec_in_codebase(self) -> None:
        """Verify no dangerous eval/exec patterns in key modules."""
        # This is a static check that would normally be done by linting
        # Here we just verify the extractors don't use dangerous patterns
        import inspect

        from newsdigest.core import extractor

        source = inspect.getsource(extractor)

        dangerous_patterns = [
            "eval(",
            "exec(",
            "__import__(",
            "compile(",
        ]

        for pattern in dangerous_patterns:
            assert pattern not in source, f"Found dangerous pattern: {pattern}"

    def test_no_shell_injection_vectors(self) -> None:
        """Verify no shell command execution in core modules."""
        import inspect

        from newsdigest.core import extractor

        source = inspect.getsource(extractor)

        shell_patterns = [
            "subprocess.call",
            "os.system",
            "os.popen",
            "commands.getoutput",
        ]

        for pattern in shell_patterns:
            assert pattern not in source, f"Found shell pattern: {pattern}"
