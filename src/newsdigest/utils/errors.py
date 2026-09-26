"""Error reporting and tracking for NewsDigest.

This module provides centralized error reporting with support for:
- Sentry integration (optional)
- Structured error context
- Error sampling and filtering
- Breadcrumb tracking for debugging
"""

import importlib.util
import os
import sys
import traceback
from collections.abc import Callable, Generator
from contextlib import contextmanager, suppress
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

from newsdigest.utils.logging import get_logger


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])

# Module logger
logger = get_logger(__name__)


# =============================================================================
# ERROR SEVERITY
# =============================================================================


class ErrorSeverity(Enum):
    """Error severity levels for reporting."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


# =============================================================================
# ERROR CONTEXT
# =============================================================================


class ErrorContext:
    """Stores contextual information for error reports."""

    def __init__(self) -> None:
        """Initialize error context."""
        self._breadcrumbs: list[dict[str, Any]] = []
        self._tags: dict[str, str] = {}
        self._extra: dict[str, Any] = {}
        self._user: dict[str, Any] | None = None
        self._max_breadcrumbs: int = 100

    def add_breadcrumb(
        self,
        message: str,
        category: str = "default",
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Add a breadcrumb for debugging context.

        Args:
            message: Breadcrumb message.
            category: Category (e.g., 'http', 'extraction', 'pipeline').
            level: Severity level.
            data: Additional data.
        """
        breadcrumb: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "message": message,
            "category": category,
            "level": level,
        }
        if data:
            breadcrumb["data"] = data

        self._breadcrumbs.append(breadcrumb)

        # Trim old breadcrumbs
        if len(self._breadcrumbs) > self._max_breadcrumbs:
            self._breadcrumbs = self._breadcrumbs[-self._max_breadcrumbs :]

    def set_tag(self, key: str, value: str) -> None:
        """Set a tag for filtering/grouping errors.

        Args:
            key: Tag key.
            value: Tag value.
        """
        self._tags[key] = str(value)

    def set_extra(self, key: str, value: Any) -> None:
        """Set extra context data.

        Args:
            key: Context key.
            value: Context value.
        """
        self._extra[key] = value

    def set_user(
        self,
        user_id: str | None = None,
        email: str | None = None,
        username: str | None = None,
    ) -> None:
        """Set user context.

        Args:
            user_id: User identifier.
            email: User email.
            username: Username.
        """
        self._user = {}
        if user_id:
            self._user["id"] = user_id
        if email:
            self._user["email"] = email
        if username:
            self._user["username"] = username

    def clear(self) -> None:
        """Clear all context."""
        self._breadcrumbs.clear()
        self._tags.clear()
        self._extra.clear()
        self._user = None

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary.

        Returns:
            Context dictionary.
        """
        result: dict[str, Any] = {
            "breadcrumbs": self._breadcrumbs.copy(),
        }
        if self._tags:
            result["tags"] = self._tags.copy()
        if self._extra:
            result["extra"] = self._extra.copy()
        if self._user:
            result["user"] = self._user.copy()
        return result


# Global error context
_error_context = ErrorContext()


def get_error_context() -> ErrorContext:
    """Get the global error context.

    Returns:
        ErrorContext instance.
    """
    return _error_context


# =============================================================================
# ERROR REPORTER
# =============================================================================


class ErrorReporter:
    """Centralized error reporting with optional Sentry integration.

    Usage:
        reporter = ErrorReporter()
        reporter.configure(dsn="https://...@sentry.io/...")

        try:
            # code
        except Exception as e:
            reporter.capture_exception(e)
    """

    def __init__(self) -> None:
        """Initialize error reporter."""
        self._initialized = False
        self._sentry_available = False
        self._dsn: str | None = None
        self._environment: str = "development"
        self._release: str | None = None
        self._sample_rate: float = 1.0
        self._error_handlers: list[Callable[[BaseException, dict[str, Any]], None]] = []

        # Check for sentry-sdk
        self._sentry_available = importlib.util.find_spec("sentry_sdk") is not None

    def configure(
        self,
        dsn: str | None = None,
        environment: str | None = None,
        release: str | None = None,
        sample_rate: float = 1.0,
        attach_stacktrace: bool = True,
        send_default_pii: bool = False,
    ) -> bool:
        """Configure error reporting.

        Args:
            dsn: Sentry DSN. If not provided, checks SENTRY_DSN env var.
            environment: Environment name (production, staging, development).
            release: Release/version string.
            sample_rate: Error sampling rate (0.0 to 1.0).
            attach_stacktrace: Whether to attach stack traces.
            send_default_pii: Whether to send PII data.

        Returns:
            True if Sentry was initialized, False otherwise.
        """
        # Get DSN from parameter or environment
        self._dsn = dsn or os.environ.get("SENTRY_DSN")
        self._environment = environment or os.environ.get(
            "NEWSDIGEST_ENV", "development"
        )
        self._release = release or os.environ.get("NEWSDIGEST_VERSION")
        self._sample_rate = max(0.0, min(1.0, sample_rate))

        if not self._dsn:
            logger.debug("No Sentry DSN configured, error reporting disabled")
            self._initialized = True
            return False

        if not self._sentry_available:
            logger.warning(
                "sentry-sdk not installed. Install with: pip install sentry-sdk"
            )
            self._initialized = True
            return False

        try:
            import sentry_sdk
            from sentry_sdk.integrations.logging import LoggingIntegration

            # Configure Sentry
            sentry_sdk.init(
                dsn=self._dsn,
                environment=self._environment,
                release=self._release,
                sample_rate=self._sample_rate,
                attach_stacktrace=attach_stacktrace,
                send_default_pii=send_default_pii,
                integrations=[
                    LoggingIntegration(
                        level=None,  # Capture all as breadcrumbs
                        event_level=None,  # Don't auto-capture logs as events
                    ),
                ],
            )

            self._initialized = True
            logger.info(f"Sentry initialized for environment: {self._environment}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize Sentry: {e}")
            self._initialized = True
            return False

    def add_error_handler(
        self,
        handler: Callable[[BaseException, dict[str, Any]], None],
    ) -> None:
        """Add a custom error handler.

        Args:
            handler: Callable that receives (exception, context_dict).
        """
        self._error_handlers.append(handler)

    def capture_exception(
        self,
        exception: BaseException | None = None,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        extra: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> str | None:
        """Capture and report an exception.

        Args:
            exception: Exception to capture. If None, captures current exception.
            severity: Error severity level.
            extra: Additional context data.
            tags: Additional tags.

        Returns:
            Event ID if captured, None otherwise.
        """
        if exception is None:
            exception = sys.exc_info()[1]

        if exception is None:
            return None

        # Build context
        context = _error_context.to_dict()
        if extra:
            context.setdefault("extra", {}).update(extra)
        if tags:
            context.setdefault("tags", {}).update(tags)

        context["severity"] = severity.value

        # Log the error locally
        logger.error(
            f"Captured exception: {type(exception).__name__}: {exception}",
            exc_info=True,
        )

        # Call custom handlers
        for handler in self._error_handlers:
            try:
                handler(exception, context)
            except Exception as handler_error:
                logger.warning(f"Error handler failed: {handler_error}")

        # Send to Sentry if available
        if self._sentry_available and self._dsn:
            try:
                import sentry_sdk

                with sentry_sdk.push_scope() as scope:
                    # Apply context
                    for key, value in context.get("tags", {}).items():
                        scope.set_tag(key, value)
                    for key, value in context.get("extra", {}).items():
                        scope.set_extra(key, value)
                    if context.get("user"):
                        scope.set_user(context["user"])

                    # Add breadcrumbs
                    for crumb in context.get("breadcrumbs", []):
                        sentry_sdk.add_breadcrumb(
                            message=crumb.get("message"),
                            category=crumb.get("category"),
                            level=crumb.get("level"),
                            data=crumb.get("data"),
                        )

                    scope.level = severity.value
                    event_id: str | None = sentry_sdk.capture_exception(exception)
                    return event_id

            except Exception as sentry_error:
                logger.warning(f"Failed to send to Sentry: {sentry_error}")

        return None

    def capture_message(
        self,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.INFO,
        extra: dict[str, Any] | None = None,
        tags: dict[str, str] | None = None,
    ) -> str | None:
        """Capture and report a message.

        Args:
            message: Message to capture.
            severity: Severity level.
            extra: Additional context data.
            tags: Additional tags.

        Returns:
            Event ID if captured, None otherwise.
        """
        # Log locally
        log_method = getattr(logger, severity.value, logger.info)
        log_method(f"Captured message: {message}")

        # Send to Sentry if available
        if self._sentry_available and self._dsn:
            try:
                import sentry_sdk

                with sentry_sdk.push_scope() as scope:
                    if tags:
                        for key, value in tags.items():
                            scope.set_tag(key, value)
                    if extra:
                        for key, value in extra.items():
                            scope.set_extra(key, value)

                    scope.level = severity.value
                    event_id: str | None = sentry_sdk.capture_message(message)
                    return event_id

            except Exception as sentry_error:
                logger.warning(f"Failed to send to Sentry: {sentry_error}")

        return None

    def add_breadcrumb(
        self,
        message: str,
        category: str = "default",
        level: str = "info",
        data: dict[str, Any] | None = None,
    ) -> None:
        """Add a breadcrumb to global context.

        Args:
            message: Breadcrumb message.
            category: Category.
            level: Level.
            data: Additional data.
        """
        _error_context.add_breadcrumb(message, category, level, data)

        # Also add to Sentry directly if available
        if self._sentry_available and self._dsn:
            try:
                import sentry_sdk

                sentry_sdk.add_breadcrumb(
                    message=message,
                    category=category,
                    level=level,
                    data=data,
                )
            except Exception as e:
                # Error reporting must never raise into the caller
                logger.debug(f"Sentry call failed: {e}")

    def set_tag(self, key: str, value: str) -> None:
        """Set a global tag.

        Args:
            key: Tag key.
            value: Tag value.
        """
        _error_context.set_tag(key, value)

        if self._sentry_available and self._dsn:
            try:
                import sentry_sdk

                sentry_sdk.set_tag(key, value)
            except Exception as e:
                # Error reporting must never raise into the caller
                logger.debug(f"Sentry call failed: {e}")

    def set_user(
        self,
        user_id: str | None = None,
        email: str | None = None,
        username: str | None = None,
    ) -> None:
        """Set user context.

        Args:
            user_id: User identifier.
            email: User email.
            username: Username.
        """
        _error_context.set_user(user_id, email, username)

        if self._sentry_available and self._dsn:
            try:
                import sentry_sdk

                user_data = {}
                if user_id:
                    user_data["id"] = user_id
                if email:
                    user_data["email"] = email
                if username:
                    user_data["username"] = username
                sentry_sdk.set_user(user_data)
            except Exception as e:
                # Error reporting must never raise into the caller
                logger.debug(f"Sentry call failed: {e}")

    @property
    def is_configured(self) -> bool:
        """Check if error reporting is configured."""
        return self._initialized

    @property
    def has_sentry(self) -> bool:
        """Check if Sentry is available and configured."""
        return self._sentry_available and self._dsn is not None


# Global error reporter instance
_reporter = ErrorReporter()


def get_error_reporter() -> ErrorReporter:
    """Get the global error reporter.

    Returns:
        ErrorReporter instance.
    """
    return _reporter


def configure_error_reporting(
    dsn: str | None = None,
    environment: str | None = None,
    release: str | None = None,
    sample_rate: float = 1.0,
) -> bool:
    """Configure global error reporting.

    Args:
        dsn: Sentry DSN.
        environment: Environment name.
        release: Release version.
        sample_rate: Sample rate.

    Returns:
        True if Sentry initialized.
    """
    return _reporter.configure(
        dsn=dsn,
        environment=environment,
        release=release,
        sample_rate=sample_rate,
    )


def capture_exception(
    exception: BaseException | None = None,
    **kwargs: Any,
) -> str | None:
    """Capture an exception using global reporter.

    Args:
        exception: Exception to capture.
        **kwargs: Additional arguments.

    Returns:
        Event ID if captured.
    """
    return _reporter.capture_exception(exception, **kwargs)


def capture_message(
    message: str,
    severity: ErrorSeverity = ErrorSeverity.INFO,
    **kwargs: Any,
) -> str | None:
    """Capture a message using global reporter.

    Args:
        message: Message to capture.
        severity: Severity level.
        **kwargs: Additional arguments.

    Returns:
        Event ID if captured.
    """
    return _reporter.capture_message(message, severity=severity, **kwargs)


def add_breadcrumb(
    message: str,
    category: str = "default",
    level: str = "info",
    data: dict[str, Any] | None = None,
) -> None:
    """Add a breadcrumb using global reporter.

    Args:
        message: Breadcrumb message.
        category: Category.
        level: Level.
        data: Additional data.
    """
    _reporter.add_breadcrumb(message, category, level, data)


# =============================================================================
# DECORATORS
# =============================================================================


def capture_errors(
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    reraise: bool = True,
    extra_context: Callable[..., dict[str, Any]] | None = None,
) -> Callable[[F], F]:
    """Decorator to capture exceptions from functions.

    Args:
        severity: Error severity level.
        reraise: Whether to reraise the exception after capturing.
        extra_context: Optional function to generate extra context from args.

    Returns:
        Decorated function.

    Usage:
        @capture_errors(severity=ErrorSeverity.ERROR)
        def my_function():
            pass
    """

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return func(*args, **kwargs)
            except Exception as e:
                extra = {"function": func.__name__}
                if extra_context:
                    with suppress(Exception):
                        extra.update(extra_context(*args, **kwargs))

                capture_exception(e, severity=severity, extra=extra)

                if reraise:
                    raise

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                extra = {"function": func.__name__}
                if extra_context:
                    with suppress(Exception):
                        extra.update(extra_context(*args, **kwargs))

                capture_exception(e, severity=severity, extra=extra)

                if reraise:
                    raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return wrapper  # type: ignore

    return decorator


@contextmanager
def error_boundary(
    operation: str,
    severity: ErrorSeverity = ErrorSeverity.ERROR,
    reraise: bool = True,
    extra: dict[str, Any] | None = None,
) -> Generator[None, None, None]:
    """Context manager for capturing errors within a scope.

    Args:
        operation: Operation description.
        severity: Error severity.
        reraise: Whether to reraise exceptions.
        extra: Extra context data.

    Usage:
        with error_boundary("processing article", extra={"url": url}):
            # code that might fail
    """
    add_breadcrumb(f"Starting: {operation}", category="operation", level="info")

    try:
        yield
        add_breadcrumb(f"Completed: {operation}", category="operation", level="info")
    except Exception as e:
        context = {"operation": operation}
        if extra:
            context.update(extra)

        capture_exception(e, severity=severity, extra=context)

        add_breadcrumb(
            f"Failed: {operation}",
            category="operation",
            level="error",
            data={"error": str(e)},
        )

        if reraise:
            raise


# =============================================================================
# ERROR FORMATTING
# =============================================================================


def format_exception(
    exception: Exception,
    include_traceback: bool = True,
) -> str:
    """Format an exception for logging/display.

    Args:
        exception: Exception to format.
        include_traceback: Whether to include traceback.

    Returns:
        Formatted exception string.
    """
    parts = [f"{type(exception).__name__}: {exception}"]

    # Check for NewsDigest exceptions with cause
    if hasattr(exception, "cause") and exception.cause:
        parts.append(
            f"  Caused by: {type(exception.cause).__name__}: {exception.cause}"
        )

    # Check for details
    if hasattr(exception, "details") and exception.details:
        for key, value in exception.details.items():
            parts.append(f"  {key}: {value}")

    # Add traceback if requested
    if include_traceback:
        tb = "".join(
            traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )
        )
        parts.append(f"\nTraceback:\n{tb}")

    return "\n".join(parts)


def get_exception_chain(exception: BaseException) -> list[BaseException]:
    """Get the chain of exceptions (cause chain).

    Args:
        exception: Root exception.

    Returns:
        List of exceptions in the chain.
    """
    chain = [exception]

    # Check for explicit cause
    if hasattr(exception, "cause") and exception.cause:
        chain.extend(get_exception_chain(exception.cause))
    # Check for __cause__ (from `raise ... from ...`)
    elif exception.__cause__:
        chain.extend(get_exception_chain(exception.__cause__))
    # Check for __context__ (implicit chaining)
    elif exception.__context__ and not exception.__suppress_context__:
        chain.extend(get_exception_chain(exception.__context__))

    return chain
