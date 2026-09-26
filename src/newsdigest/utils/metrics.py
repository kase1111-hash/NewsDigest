"""Telemetry and metrics collection for NewsDigest.

This module provides utilities for collecting performance metrics,
usage statistics, and optional external reporting.
"""

import time
from collections import defaultdict
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import wraps
from threading import Lock
from typing import Any, TypeVar


F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class TimingStats:
    """Statistics for timing measurements."""

    count: int = 0
    total_ms: float = 0.0
    min_ms: float = float("inf")
    max_ms: float = 0.0
    last_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        """Average time in milliseconds."""
        return self.total_ms / self.count if self.count > 0 else 0.0

    def record(self, duration_ms: float) -> None:
        """Record a timing measurement."""
        self.count += 1
        self.total_ms += duration_ms
        self.last_ms = duration_ms
        self.min_ms = min(self.min_ms, duration_ms)
        self.max_ms = max(self.max_ms, duration_ms)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 2),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2) if self.count > 0 else None,
            "max_ms": round(self.max_ms, 2) if self.count > 0 else None,
            "last_ms": round(self.last_ms, 2) if self.count > 0 else None,
        }


@dataclass
class CounterStats:
    """Statistics for counter measurements."""

    value: int = 0
    last_increment: int = 0
    last_updated: datetime | None = None

    def increment(self, amount: int = 1) -> None:
        """Increment the counter."""
        self.value += amount
        self.last_increment = amount
        self.last_updated = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "value": self.value,
            "last_increment": self.last_increment,
            "last_updated": self.last_updated.isoformat()
            if self.last_updated
            else None,
        }


@dataclass
class GaugeStats:
    """Statistics for gauge measurements (current value)."""

    value: float = 0.0
    min_value: float = float("inf")
    max_value: float = float("-inf")
    last_updated: datetime | None = None

    def set(self, value: float) -> None:
        """Set the gauge value."""
        self.value = value
        self.min_value = min(self.min_value, value)
        self.max_value = max(self.max_value, value)
        self.last_updated = datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        has_data = self.last_updated is not None
        return {
            "value": self.value,
            "min_value": self.min_value if has_data else None,
            "max_value": self.max_value if has_data else None,
            "last_updated": self.last_updated.isoformat()
            if self.last_updated
            else None,
        }


@dataclass
class MetricsCollector:
    """Collects and aggregates metrics for NewsDigest operations.

    Thread-safe metrics collection with support for:
    - Timing measurements (extraction time, analysis time)
    - Counters (articles processed, errors)
    - Gauges (compression ratio, queue size)
    - Histograms (content length distribution)

    Example:
        >>> metrics = MetricsCollector()
        >>> with metrics.timer("extraction"):
        ...     result = extractor.extract(url)
        >>> metrics.increment("articles_processed")
        >>> print(metrics.get_stats())
    """

    _timings: dict[str, TimingStats] = field(default_factory=dict)
    _counters: dict[str, CounterStats] = field(default_factory=dict)
    _gauges: dict[str, GaugeStats] = field(default_factory=dict)
    _histograms: dict[str, list[float]] = field(
        default_factory=lambda: defaultdict(list)
    )
    _lock: Lock = field(default_factory=Lock)
    _start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    _enabled: bool = True

    def enable(self) -> None:
        """Enable metrics collection."""
        self._enabled = True

    def disable(self) -> None:
        """Disable metrics collection."""
        self._enabled = False

    @contextmanager
    def timer(self, name: str):
        """Context manager for timing operations.

        Args:
            name: Name of the operation to time.

        Yields:
            None

        Example:
            >>> with metrics.timer("extraction"):
            ...     result = extract(url)
        """
        if not self._enabled:
            yield
            return

        start = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            self.record_timing(name, duration_ms)

    def timed(self, name: str | None = None) -> Callable[[F], F]:
        """Decorator for timing function calls.

        Args:
            name: Optional name for the metric. Defaults to function name.

        Returns:
            Decorated function.

        Example:
            >>> @metrics.timed("extraction")
            ... def extract(url): ...
        """

        def decorator(func: F) -> F:
            metric_name = name or func.__name__

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                with self.timer(metric_name):
                    return func(*args, **kwargs)

            return wrapper  # type: ignore

        return decorator

    def record_timing(self, name: str, duration_ms: float) -> None:
        """Record a timing measurement.

        Args:
            name: Name of the timing metric.
            duration_ms: Duration in milliseconds.
        """
        if not self._enabled:
            return

        with self._lock:
            if name not in self._timings:
                self._timings[name] = TimingStats()
            self._timings[name].record(duration_ms)

    def increment(self, name: str, amount: int = 1) -> None:
        """Increment a counter.

        Args:
            name: Name of the counter.
            amount: Amount to increment by.
        """
        if not self._enabled:
            return

        with self._lock:
            if name not in self._counters:
                self._counters[name] = CounterStats()
            self._counters[name].increment(amount)

    def set_gauge(self, name: str, value: float) -> None:
        """Set a gauge value.

        Args:
            name: Name of the gauge.
            value: Current value.
        """
        if not self._enabled:
            return

        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = GaugeStats()
            self._gauges[name].set(value)

    def record_histogram(self, name: str, value: float) -> None:
        """Record a value in a histogram.

        Args:
            name: Name of the histogram.
            value: Value to record.
        """
        if not self._enabled:
            return

        with self._lock:
            self._histograms[name].append(value)

    def get_timing(self, name: str) -> TimingStats | None:
        """Get timing statistics for a metric.

        Args:
            name: Name of the timing metric.

        Returns:
            TimingStats or None if not found.
        """
        with self._lock:
            return self._timings.get(name)

    def get_counter(self, name: str) -> int:
        """Get current counter value.

        Args:
            name: Name of the counter.

        Returns:
            Current counter value.
        """
        with self._lock:
            counter = self._counters.get(name)
            return counter.value if counter else 0

    def get_gauge(self, name: str) -> float:
        """Get current gauge value.

        Args:
            name: Name of the gauge.

        Returns:
            Current gauge value.
        """
        with self._lock:
            gauge = self._gauges.get(name)
            return gauge.value if gauge else 0.0

    def get_histogram_percentile(self, name: str, percentile: float) -> float | None:
        """Get a percentile value from a histogram.

        Args:
            name: Name of the histogram.
            percentile: Percentile (0-100).

        Returns:
            Percentile value or None if no data.
        """
        with self._lock:
            values = self._histograms.get(name)
            if not values:
                return None

            sorted_values = sorted(values)
            idx = int(len(sorted_values) * percentile / 100)
            idx = min(idx, len(sorted_values) - 1)
            return sorted_values[idx]

    def get_stats(self) -> dict[str, Any]:
        """Get all collected statistics.

        Returns:
            Dictionary with all metrics.
        """
        with self._lock:
            now = datetime.now(UTC)
            uptime = (now - self._start_time).total_seconds()

            return {
                "uptime_seconds": round(uptime, 2),
                "enabled": self._enabled,
                "timings": {
                    name: stats.to_dict() for name, stats in self._timings.items()
                },
                "counters": {
                    name: stats.to_dict() for name, stats in self._counters.items()
                },
                "gauges": {
                    name: stats.to_dict() for name, stats in self._gauges.items()
                },
                "histograms": {
                    name: {
                        "count": len(values),
                        "min": min(values) if values else None,
                        "max": max(values) if values else None,
                        "avg": sum(values) / len(values) if values else None,
                        "p50": self.get_histogram_percentile(name, 50),
                        "p95": self.get_histogram_percentile(name, 95),
                        "p99": self.get_histogram_percentile(name, 99),
                    }
                    for name, values in self._histograms.items()
                },
            }

    def reset(self) -> None:
        """Reset all metrics."""
        with self._lock:
            self._timings.clear()
            self._counters.clear()
            self._gauges.clear()
            self._histograms.clear()
            self._start_time = datetime.now(UTC)


# Global metrics collector instance
_metrics: MetricsCollector | None = None
_metrics_lock = Lock()


def get_metrics() -> MetricsCollector:
    """Get the global metrics collector instance.

    Returns:
        Global MetricsCollector instance.
    """
    global _metrics
    with _metrics_lock:
        if _metrics is None:
            _metrics = MetricsCollector()
        return _metrics


def reset_metrics() -> None:
    """Reset the global metrics collector."""
    with _metrics_lock:
        if _metrics is not None:
            _metrics.reset()


# Convenience functions using global collector
def record_timing(name: str, duration_ms: float) -> None:
    """Record a timing measurement to the global collector."""
    get_metrics().record_timing(name, duration_ms)


def increment(name: str, amount: int = 1) -> None:
    """Increment a counter in the global collector."""
    get_metrics().increment(name, amount)


def set_gauge(name: str, value: float) -> None:
    """Set a gauge value in the global collector."""
    get_metrics().set_gauge(name, value)


def record_histogram(name: str, value: float) -> None:
    """Record a histogram value in the global collector."""
    get_metrics().record_histogram(name, value)


@contextmanager
def timer(name: str):
    """Context manager for timing operations using global collector."""
    with get_metrics().timer(name):
        yield


def timed(name: str | None = None) -> Callable[[F], F]:
    """Decorator for timing function calls using global collector."""
    return get_metrics().timed(name)


def get_stats() -> dict[str, Any]:
    """Get all statistics from the global collector."""
    return get_metrics().get_stats()


# Predefined metric names for consistency
class MetricNames:
    """Standard metric names used throughout NewsDigest."""

    # Timing metrics
    EXTRACTION_TIME = "extraction_time"
    ANALYSIS_TIME = "analysis_time"
    FETCH_TIME = "fetch_time"
    PARSE_TIME = "parse_time"
    CLUSTERING_TIME = "clustering_time"
    DEDUP_TIME = "deduplication_time"
    FORMAT_TIME = "format_time"

    # Counter metrics
    ARTICLES_PROCESSED = "articles_processed"
    ARTICLES_FAILED = "articles_failed"
    EXTRACTIONS_TOTAL = "extractions_total"
    CACHE_HITS = "cache_hits"
    CACHE_MISSES = "cache_misses"
    HTTP_REQUESTS = "http_requests"
    HTTP_ERRORS = "http_errors"

    # Gauge metrics
    COMPRESSION_RATIO = "compression_ratio"
    QUEUE_SIZE = "queue_size"
    ACTIVE_TASKS = "active_tasks"

    # Histogram metrics
    CONTENT_LENGTH = "content_length"
    SENTENCE_COUNT = "sentence_count"
    FILLER_RATIO = "filler_ratio"
    SPECULATION_RATIO = "speculation_ratio"
