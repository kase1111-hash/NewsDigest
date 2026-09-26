"""Custom exceptions for NewsDigest.

This module defines a comprehensive exception hierarchy for the NewsDigest
application, enabling precise error handling and meaningful error messages.

Exception Hierarchy:
    NewsDigestError (base)
    ├── ConfigurationError
    │   └── InvalidConfigError
    ├── ExtractionError
    │   ├── ContentExtractionError
    │   ├── AnalysisError
    │   └── PipelineError
    ├── IngestError
    │   ├── FetchError
    │   ├── ParseError
    │   └── RateLimitError
    ├── ValidationError (re-exported from utils)
    └── FormatterError
"""

from typing import Any


class NewsDigestError(Exception):
    """Base exception for all NewsDigest errors.

    All custom exceptions inherit from this class, allowing for
    catch-all exception handling when needed.
    """

    def __init__(
        self,
        message: str,
        *args: Any,
        cause: Exception | None = None,
        details: dict | None = None,
    ) -> None:
        """Initialize exception.

        Args:
            message: Human-readable error message.
            *args: Additional positional arguments.
            cause: Original exception that caused this error.
            details: Additional error context as dictionary.
        """
        super().__init__(message, *args)
        self.message = message
        self.cause = cause
        self.details = details or {}

    def __str__(self) -> str:
        """Return string representation."""
        result = self.message
        if self.cause:
            result += f" (caused by: {self.cause})"
        return result

    def to_dict(self) -> dict:
        """Convert exception to dictionary for JSON serialization.

        Returns:
            Dictionary with error details.
        """
        return {
            "error": self.__class__.__name__,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None,
        }


# =============================================================================
# CONFIGURATION ERRORS
# =============================================================================


class ConfigurationError(NewsDigestError):
    """Error in configuration settings."""

    pass


class InvalidConfigError(ConfigurationError):
    """Invalid configuration value.

    Raised when a configuration value is invalid or out of range.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize invalid config error.

        Args:
            message: Error message.
            field: Configuration field name.
            value: Invalid value.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        self.details["field"] = field
        self.details["value"] = repr(value)


# =============================================================================
# EXTRACTION ERRORS
# =============================================================================


class ExtractionError(NewsDigestError):
    """Error during content extraction."""

    pass


class ContentExtractionError(ExtractionError):
    """Failed to extract content from source.

    Raised when article content cannot be extracted from HTML or text.
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize content extraction error.

        Args:
            message: Error message.
            url: Source URL if applicable.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.url = url
        if url:
            self.details["url"] = url


class AnalysisError(ExtractionError):
    """Error during semantic analysis.

    Raised when an analyzer fails to process content.
    """

    def __init__(
        self,
        message: str,
        analyzer: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize analysis error.

        Args:
            message: Error message.
            analyzer: Name of the failing analyzer.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.analyzer = analyzer
        if analyzer:
            self.details["analyzer"] = analyzer


class PipelineError(ExtractionError):
    """Error in the NLP pipeline.

    Raised when the spaCy pipeline fails or is misconfigured.
    """

    def __init__(
        self,
        message: str,
        stage: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize pipeline error.

        Args:
            message: Error message.
            stage: Pipeline stage that failed.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.stage = stage
        if stage:
            self.details["stage"] = stage


# =============================================================================
# INGESTION ERRORS
# =============================================================================


class IngestError(NewsDigestError):
    """Error during content ingestion."""

    pass


class FetchError(IngestError):
    """Failed to fetch content from URL.

    Raised when HTTP request fails after retries.
    """

    def __init__(
        self,
        message: str,
        url: str | None = None,
        status_code: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize fetch error.

        Args:
            message: Error message.
            url: URL that failed to fetch.
            status_code: HTTP status code if applicable.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.url = url
        self.status_code = status_code
        if url:
            self.details["url"] = url
        if status_code:
            self.details["status_code"] = status_code


class ParseError(IngestError):
    """Failed to parse content.

    Raised when HTML/RSS/JSON parsing fails.
    """

    def __init__(
        self,
        message: str,
        content_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize parse error.

        Args:
            message: Error message.
            content_type: Type of content that failed to parse.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.content_type = content_type
        if content_type:
            self.details["content_type"] = content_type


class RateLimitError(IngestError):
    """Rate limit exceeded.

    Raised when a source returns 429 Too Many Requests.
    """

    def __init__(
        self,
        message: str,
        retry_after: int | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize rate limit error.

        Args:
            message: Error message.
            retry_after: Seconds to wait before retrying.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.retry_after = retry_after
        if retry_after:
            self.details["retry_after"] = retry_after


# =============================================================================
# VALIDATION ERRORS
# =============================================================================


class ValidationError(NewsDigestError):
    """Validation error for input data.

    Raised when input data fails validation.
    """

    def __init__(
        self,
        message: str,
        field: str | None = None,
        value: Any = None,
        **kwargs: Any,
    ) -> None:
        """Initialize validation error.

        Args:
            message: Error message.
            field: Field name that failed validation.
            value: Invalid value.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.field = field
        self.value = value
        if field:
            self.details["field"] = field
        if value is not None:
            self.details["value"] = repr(value)


# =============================================================================
# FORMATTER ERRORS
# =============================================================================


class FormatterError(NewsDigestError):
    """Error during output formatting.

    Raised when formatting results fails.
    """

    def __init__(
        self,
        message: str,
        format_type: str | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize formatter error.

        Args:
            message: Error message.
            format_type: Output format that failed.
            **kwargs: Additional arguments for parent.
        """
        super().__init__(message, **kwargs)
        self.format_type = format_type
        if format_type:
            self.details["format_type"] = format_type


# =============================================================================
# DIGEST ERRORS
# =============================================================================


class DigestError(NewsDigestError):
    """Error during digest generation."""

    pass


class ClusteringError(DigestError):
    """Error during topic clustering.

    Raised when article clustering fails.
    """

    pass


class DeduplicationError(DigestError):
    """Error during deduplication.

    Raised when duplicate detection fails.
    """

    pass


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================


def wrap_exception(
    exc: Exception,
    wrapper_class: type,
    message: str | None = None,
) -> NewsDigestError:
    """Wrap an exception in a NewsDigest exception.

    Args:
        exc: Original exception.
        wrapper_class: NewsDigestError subclass to wrap with.
        message: Optional custom message (uses original if not provided).

    Returns:
        Wrapped exception.
    """
    msg = message or str(exc)
    return wrapper_class(msg, cause=exc)


def is_retryable(exc: Exception) -> bool:
    """Check if an exception is retryable.

    Args:
        exc: Exception to check.

    Returns:
        True if operation should be retried.
    """
    # Rate limit errors are retryable
    if isinstance(exc, RateLimitError):
        return True

    # Fetch errors with 5xx status codes are retryable
    if isinstance(exc, FetchError) and exc.status_code:
        return exc.status_code >= 500

    # Network errors from httpx are retryable
    try:
        import httpx

        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            return True
    except ImportError:
        pass

    return False
