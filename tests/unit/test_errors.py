"""Tests for error reporting utilities."""

import pytest

from newsdigest.exceptions import ExtractionError
from newsdigest.utils.errors import (
    ErrorContext,
    ErrorReporter,
    ErrorSeverity,
    add_breadcrumb,
    capture_errors,
    capture_exception,
    capture_message,
    error_boundary,
    format_exception,
    get_error_context,
    get_error_reporter,
    get_exception_chain,
)


class TestErrorSeverity:
    """Tests for ErrorSeverity enum."""

    def test_severity_values(self):
        """Test that all severity levels exist."""
        assert ErrorSeverity.DEBUG.value == "debug"
        assert ErrorSeverity.INFO.value == "info"
        assert ErrorSeverity.WARNING.value == "warning"
        assert ErrorSeverity.ERROR.value == "error"
        assert ErrorSeverity.FATAL.value == "fatal"


class TestErrorContext:
    """Tests for ErrorContext class."""

    def test_add_breadcrumb(self):
        """Test adding breadcrumbs."""
        context = ErrorContext()
        context.add_breadcrumb("Test message", category="test")

        data = context.to_dict()
        assert len(data["breadcrumbs"]) == 1
        assert data["breadcrumbs"][0]["message"] == "Test message"
        assert data["breadcrumbs"][0]["category"] == "test"

    def test_add_breadcrumb_with_data(self):
        """Test adding breadcrumb with extra data."""
        context = ErrorContext()
        context.add_breadcrumb("Message", data={"key": "value"})

        data = context.to_dict()
        assert data["breadcrumbs"][0]["data"]["key"] == "value"

    def test_breadcrumb_limit(self):
        """Test that breadcrumbs are limited."""
        context = ErrorContext()
        context._max_breadcrumbs = 5

        for i in range(10):
            context.add_breadcrumb(f"Message {i}")

        data = context.to_dict()
        assert len(data["breadcrumbs"]) == 5

    def test_set_tag(self):
        """Test setting tags."""
        context = ErrorContext()
        context.set_tag("environment", "production")

        data = context.to_dict()
        assert data["tags"]["environment"] == "production"

    def test_set_extra(self):
        """Test setting extra context."""
        context = ErrorContext()
        context.set_extra("user_id", 123)

        data = context.to_dict()
        assert data["extra"]["user_id"] == 123

    def test_set_user(self):
        """Test setting user context."""
        context = ErrorContext()
        context.set_user(user_id="123", email="test@example.com")

        data = context.to_dict()
        assert data["user"]["id"] == "123"
        assert data["user"]["email"] == "test@example.com"

    def test_clear(self):
        """Test clearing context."""
        context = ErrorContext()
        context.add_breadcrumb("Message")
        context.set_tag("key", "value")
        context.set_extra("data", "value")

        context.clear()
        data = context.to_dict()

        assert len(data["breadcrumbs"]) == 0
        assert "tags" not in data or len(data.get("tags", {})) == 0


class TestErrorReporter:
    """Tests for ErrorReporter class."""

    def test_initialization(self):
        """Test reporter initialization."""
        reporter = ErrorReporter()
        assert reporter._initialized is False
        assert reporter._dsn is None

    def test_configure_without_dsn(self):
        """Test configuration without DSN."""
        reporter = ErrorReporter()
        result = reporter.configure()

        assert result is False
        assert reporter.is_configured is True
        assert reporter.has_sentry is False

    def test_add_error_handler(self):
        """Test adding custom error handler."""
        reporter = ErrorReporter()
        handler_called = []

        def handler(exc, context):
            handler_called.append((exc, context))

        reporter.add_error_handler(handler)
        reporter.configure()

        try:
            raise ValueError("Test error")
        except Exception as e:
            reporter.capture_exception(e)

        assert len(handler_called) == 1
        assert isinstance(handler_called[0][0], ValueError)

    def test_capture_exception_logs_locally(self):
        """Test that capture_exception logs locally."""
        reporter = ErrorReporter()
        reporter.configure()

        try:
            raise ValueError("Test error")
        except Exception as e:
            result = reporter.capture_exception(e)

        # Without Sentry, should return None but still log
        assert result is None

    def test_capture_message(self):
        """Test capturing a message."""
        reporter = ErrorReporter()
        reporter.configure()

        result = reporter.capture_message("Test message", severity=ErrorSeverity.INFO)
        # Without Sentry, returns None
        assert result is None

    def test_add_breadcrumb_via_reporter(self):
        """Test adding breadcrumb via reporter."""
        reporter = ErrorReporter()
        reporter.configure()

        # Should not raise
        reporter.add_breadcrumb("Test", category="test")

    def test_set_tag_via_reporter(self):
        """Test setting tag via reporter."""
        reporter = ErrorReporter()
        reporter.configure()

        # Should not raise
        reporter.set_tag("key", "value")

    def test_set_user_via_reporter(self):
        """Test setting user via reporter."""
        reporter = ErrorReporter()
        reporter.configure()

        # Should not raise
        reporter.set_user(user_id="123")


class TestCaptureErrorsDecorator:
    """Tests for @capture_errors decorator."""

    def test_decorator_reraises_by_default(self):
        """Test that decorator re-raises exceptions by default."""

        @capture_errors()
        def failing_function():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            failing_function()

    def test_decorator_no_reraise(self):
        """Test decorator with reraise=False."""

        @capture_errors(reraise=False)
        def failing_function():
            raise ValueError("Test error")

        # Should not raise
        result = failing_function()
        assert result is None

    def test_decorator_on_success(self):
        """Test decorator on successful function."""

        @capture_errors()
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_decorator_async_function(self):
        """Test decorator on async function."""

        @capture_errors()
        async def async_failing():
            raise ValueError("Async error")

        with pytest.raises(ValueError):
            await async_failing()

    @pytest.mark.asyncio
    async def test_decorator_async_success(self):
        """Test decorator on successful async function."""

        @capture_errors()
        async def async_success():
            return "async success"

        result = await async_success()
        assert result == "async success"


class TestErrorBoundary:
    """Tests for error_boundary context manager."""

    def test_boundary_reraises_by_default(self):
        """Test that error boundary re-raises by default."""
        with pytest.raises(ValueError), error_boundary("test operation"):
            raise ValueError("Test")

    def test_boundary_no_reraise(self):
        """Test error boundary with reraise=False."""
        with error_boundary("test operation", reraise=False):
            raise ValueError("Test")
        # Should not raise

    def test_boundary_on_success(self):
        """Test error boundary on success."""
        result = None
        with error_boundary("test operation"):
            result = "success"

        assert result == "success"


class TestFormatException:
    """Tests for format_exception function."""

    def test_format_simple_exception(self):
        """Test formatting simple exception."""
        try:
            raise ValueError("Test error message")
        except Exception as e:
            result = format_exception(e)

        assert "ValueError" in result
        assert "Test error message" in result

    def test_format_with_traceback(self):
        """Test formatting with traceback."""
        try:
            raise ValueError("Test")
        except Exception as e:
            result = format_exception(e, include_traceback=True)

        assert "Traceback" in result

    def test_format_without_traceback(self):
        """Test formatting without traceback."""
        try:
            raise ValueError("Test")
        except Exception as e:
            result = format_exception(e, include_traceback=False)

        assert "Traceback" not in result

    def test_format_newsdigest_error_with_cause(self):
        """Test formatting NewsDigest error with cause."""
        cause = ValueError("Original error")
        error = ExtractionError("Extraction failed", cause=cause)

        result = format_exception(error)

        assert "ExtractionError" in result
        assert "Extraction failed" in result
        assert "Caused by" in result
        assert "ValueError" in result


class TestGetExceptionChain:
    """Tests for get_exception_chain function."""

    def test_single_exception(self):
        """Test chain with single exception."""
        e = ValueError("Test")
        chain = get_exception_chain(e)

        assert len(chain) == 1
        assert chain[0] is e

    def test_chained_exceptions(self):
        """Test chain with chained exceptions."""
        try:
            try:
                raise ValueError("Original")
            except ValueError as e:
                raise RuntimeError("Wrapper") from e
        except RuntimeError as e:
            chain = get_exception_chain(e)

        assert len(chain) == 2
        assert isinstance(chain[0], RuntimeError)
        assert isinstance(chain[1], ValueError)

    def test_newsdigest_cause_chain(self):
        """Test chain with NewsDigest cause."""
        cause = ValueError("Original")
        error = ExtractionError("Failed", cause=cause)

        chain = get_exception_chain(error)

        assert len(chain) == 2
        assert isinstance(chain[0], ExtractionError)
        assert isinstance(chain[1], ValueError)


class TestGlobalFunctions:
    """Tests for module-level functions."""

    def test_get_error_context(self):
        """Test getting global error context."""
        context = get_error_context()
        assert isinstance(context, ErrorContext)

    def test_get_error_reporter(self):
        """Test getting global error reporter."""
        reporter = get_error_reporter()
        assert isinstance(reporter, ErrorReporter)

    def test_capture_exception_global(self):
        """Test global capture_exception."""
        try:
            raise ValueError("Test")
        except Exception as e:
            # Should not raise
            capture_exception(e)

    def test_capture_message_global(self):
        """Test global capture_message."""
        # Should not raise
        capture_message("Test message")

    def test_add_breadcrumb_global(self):
        """Test global add_breadcrumb."""
        # Should not raise
        add_breadcrumb("Test breadcrumb")
