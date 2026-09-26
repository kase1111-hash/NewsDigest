"""Logging configuration for NewsDigest.

This module provides a centralized logging configuration with:
- Structured logging with JSON output option
- Log level configuration via environment variables
- Context-aware logging with request IDs
- Performance logging utilities
- File and console handlers
"""

import logging
import os
import sys
import time
from collections.abc import Callable, Generator
from contextlib import contextmanager
from datetime import datetime
from functools import wraps
from typing import Any, ClassVar, TypeVar


# Type variable for decorator
F = TypeVar("F", bound=Callable[..., Any])

# =============================================================================
# CONSTANTS
# =============================================================================

# Default log format
DEFAULT_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# Detailed format with more context
DETAILED_FORMAT = (
    "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(funcName)s | %(message)s"
)

# JSON format template
JSON_FORMAT = (
    '{{"timestamp": "%(asctime)s", "level": "%(levelname)s", '
    '"logger": "%(name)s", "message": "%(message)s"}}'
)

# Log levels mapping
LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

# Package logger name
LOGGER_NAME = "newsdigest"


# =============================================================================
# CUSTOM FORMATTERS
# =============================================================================


class ColoredFormatter(logging.Formatter):
    """Formatter that adds colors to log levels for terminal output."""

    COLORS: ClassVar[dict[str, str]] = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[35m",  # Magenta
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with colors."""
        # Add color to levelname
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"

        result = super().format(record)

        # Restore original levelname
        record.levelname = levelname

        return result


class StructuredFormatter(logging.Formatter):
    """Formatter for structured (JSON-like) log output."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured data."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add extra fields if present
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Add location info for errors
        if record.levelno >= logging.ERROR:
            log_data["location"] = {
                "file": record.filename,
                "line": record.lineno,
                "function": record.funcName,
            }

        # Simple JSON-like output (for actual JSON, use proper json.dumps)
        parts = [f"{k}={v!r}" for k, v in log_data.items()]
        return " | ".join(parts)


# =============================================================================
# LOGGER SETUP
# =============================================================================


def setup_logging(
    level: str | None = None,
    format_type: str = "default",
    log_file: str | None = None,
    colored: bool = True,
) -> logging.Logger:
    """Configure logging for NewsDigest.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
               Defaults to NEWSDIGEST_LOG_LEVEL env var or INFO.
        format_type: Format type ('default', 'detailed', 'json', 'structured').
        log_file: Optional file path for file logging.
        colored: Whether to use colored output for console.

    Returns:
        Configured logger instance.
    """
    # Get log level from env or parameter
    if level is None:
        level = os.environ.get("NEWSDIGEST_LOG_LEVEL", "INFO")

    log_level = LOG_LEVELS.get(level.upper(), logging.INFO)

    # Get root package logger
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(log_level)

    # Remove existing handlers
    logger.handlers.clear()

    # Select format
    if format_type == "detailed":
        fmt = DETAILED_FORMAT
    elif format_type == "json":
        fmt = JSON_FORMAT
    else:
        fmt = DEFAULT_FORMAT

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)

    if format_type == "structured":
        console_handler.setFormatter(StructuredFormatter())
    elif colored and sys.stdout.isatty():
        console_handler.setFormatter(ColoredFormatter(fmt))
    else:
        console_handler.setFormatter(logging.Formatter(fmt))

    logger.addHandler(console_handler)

    # File handler (if specified)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(log_level)
        file_handler.setFormatter(logging.Formatter(DETAILED_FORMAT))
        logger.addHandler(file_handler)

    # Don't propagate to root logger
    logger.propagate = False

    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a logger for the specified module.

    Args:
        name: Module name. If None, returns the package logger.

    Returns:
        Logger instance.
    """
    if name is None:
        return logging.getLogger(LOGGER_NAME)

    # Create child logger under package namespace
    if name.startswith(LOGGER_NAME):
        return logging.getLogger(name)

    return logging.getLogger(f"{LOGGER_NAME}.{name}")


# =============================================================================
# LOGGING UTILITIES
# =============================================================================


@contextmanager
def log_context(**kwargs: Any) -> Generator[None, None, None]:
    """Context manager to add extra fields to log records.

    Usage:
        with log_context(request_id="123", user="test"):
            logger.info("Processing request")

    Args:
        **kwargs: Extra fields to add to log records.
    """
    # This is a simplified version - for production, use contextvars
    old_factory = logging.getLogRecordFactory()

    def record_factory(*args: Any, **record_kwargs: Any) -> logging.LogRecord:
        record = old_factory(*args, **record_kwargs)
        record.extra_data = kwargs
        return record

    logging.setLogRecordFactory(record_factory)
    try:
        yield
    finally:
        logging.setLogRecordFactory(old_factory)


def log_performance(logger: logging.Logger | None = None) -> Callable[[F], F]:
    """Decorator to log function execution time.

    Args:
        logger: Logger to use. Defaults to package logger.

    Returns:
        Decorated function.

    Usage:
        @log_performance()
        def my_function():
            pass
    """
    if logger is None:
        logger = get_logger()

    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time
                logger.debug(f"{func.__name__} completed in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                logger.error(f"{func.__name__} failed after {elapsed:.3f}s: {e}")
                raise

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed = time.perf_counter() - start_time
                logger.debug(f"{func.__name__} completed in {elapsed:.3f}s")
                return result
            except Exception as e:
                elapsed = time.perf_counter() - start_time
                logger.error(f"{func.__name__} failed after {elapsed:.3f}s: {e}")
                raise

        import asyncio

        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return wrapper  # type: ignore

    return decorator


class LoggedOperation:
    """Context manager for logging operation start/end with timing.

    Usage:
        with LoggedOperation(logger, "Processing article", article_id=123):
            # do work
    """

    def __init__(
        self,
        logger: logging.Logger,
        operation: str,
        level: int = logging.DEBUG,
        **context: Any,
    ) -> None:
        """Initialize logged operation.

        Args:
            logger: Logger to use.
            operation: Operation description.
            level: Log level.
            **context: Additional context to log.
        """
        self.logger = logger
        self.operation = operation
        self.level = level
        self.context = context
        self.start_time: float = 0

    def __enter__(self) -> "LoggedOperation":
        """Enter context - log start."""
        self.start_time = time.perf_counter()
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())
        self.logger.log(self.level, f"Starting: {self.operation} {context_str}".strip())
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit context - log completion or failure."""
        elapsed = time.perf_counter() - self.start_time
        context_str = " ".join(f"{k}={v}" for k, v in self.context.items())

        if exc_type is None:
            self.logger.log(
                self.level,
                f"Completed: {self.operation} in {elapsed:.3f}s {context_str}".strip(),
            )
        else:
            self.logger.error(
                f"Failed: {self.operation} after {elapsed:.3f}s - {exc_val} {context_str}".strip()
            )


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================


def log_extraction_start(
    logger: logging.Logger,
    source: str,
    source_type: str = "unknown",
) -> None:
    """Log the start of an extraction operation.

    Args:
        logger: Logger instance.
        source: Source URL or identifier.
        source_type: Type of source (url, rss, text).
    """
    # Truncate long sources
    display_source = source[:100] + "..." if len(source) > 100 else source
    logger.info(f"Extracting from {source_type}: {display_source}")


def log_extraction_complete(
    logger: logging.Logger,
    source: str,
    original_words: int,
    compressed_words: int,
    claims_count: int,
) -> None:
    """Log completion of an extraction operation.

    Args:
        logger: Logger instance.
        source: Source URL or identifier.
        original_words: Original word count.
        compressed_words: Compressed word count.
        claims_count: Number of claims extracted.
    """
    compression = (
        (1 - compressed_words / original_words) * 100 if original_words > 0 else 0
    )
    display_source = source[:50] + "..." if len(source) > 50 else source
    logger.info(
        f"Extracted {display_source}: "
        f"{original_words} -> {compressed_words} words ({compression:.1f}% compression), "
        f"{claims_count} claims"
    )


def log_error(
    logger: logging.Logger,
    message: str,
    exc: Exception | None = None,
    **context: Any,
) -> None:
    """Log an error with context.

    Args:
        logger: Logger instance.
        message: Error message.
        exc: Optional exception.
        **context: Additional context.
    """
    context_str = " ".join(f"{k}={v}" for k, v in context.items())
    if exc:
        logger.error(f"{message}: {exc} {context_str}".strip(), exc_info=True)
    else:
        logger.error(f"{message} {context_str}".strip())


# Initialize default logger on import
_default_logger: logging.Logger | None = None


def init_logging() -> logging.Logger:
    """Initialize logging with default settings.

    Call this at application startup to configure logging.

    Returns:
        Configured logger.
    """
    global _default_logger
    if _default_logger is None:
        _default_logger = setup_logging()
    return _default_logger
