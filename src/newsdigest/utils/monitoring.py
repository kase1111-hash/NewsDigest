"""Monitoring and alerting system for NewsDigest.

Provides health checks, metrics collection, and alerting capabilities.
"""

import asyncio
import contextlib
import time
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import httpx

from newsdigest.utils.logging import get_logger


logger = get_logger(__name__)


class HealthStatus(Enum):
    """Service health status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class AlertSeverity(Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str | None = None
    latency_ms: float = 0.0
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)


@dataclass
class Alert:
    """An alert notification."""

    name: str
    severity: AlertSeverity
    message: str
    source: str = "newsdigest"
    timestamp: float = field(default_factory=time.time)
    details: dict[str, Any] = field(default_factory=dict)
    resolved: bool = False


@dataclass
class MetricPoint:
    """A single metric data point."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: dict[str, str] = field(default_factory=dict)


AlertHandler = Callable[[Alert], Coroutine[Any, Any, None]]
HealthCheckFn = Callable[[], Coroutine[Any, Any, HealthCheck]]


class HealthMonitor:
    """Monitors service health with configurable checks.

    Example:
        >>> monitor = HealthMonitor()
        >>> monitor.register_check("database", check_database)
        >>> monitor.register_check("cache", check_cache)
        >>> status = await monitor.check_health()
    """

    def __init__(self) -> None:
        """Initialize health monitor."""
        self._checks: dict[str, HealthCheckFn] = {}
        self._last_results: dict[str, HealthCheck] = {}

    def register_check(
        self,
        name: str,
        check_fn: HealthCheckFn,
    ) -> None:
        """Register a health check.

        Args:
            name: Check name.
            check_fn: Async function that returns HealthCheck.
        """
        self._checks[name] = check_fn

    def unregister_check(self, name: str) -> None:
        """Unregister a health check.

        Args:
            name: Check name to remove.
        """
        self._checks.pop(name, None)
        self._last_results.pop(name, None)

    async def check_health(self) -> dict[str, Any]:
        """Run all health checks.

        Returns:
            Dictionary with overall status and individual check results.
        """
        results: list[HealthCheck] = []

        for name, check_fn in self._checks.items():
            start = time.perf_counter()
            try:
                result = await check_fn()
                result.latency_ms = (time.perf_counter() - start) * 1000
            except Exception as e:
                result = HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                    latency_ms=(time.perf_counter() - start) * 1000,
                )

            results.append(result)
            self._last_results[name] = result

        # Determine overall status
        statuses = [r.status for r in results]
        if HealthStatus.UNHEALTHY in statuses:
            overall = HealthStatus.UNHEALTHY
        elif HealthStatus.DEGRADED in statuses:
            overall = HealthStatus.DEGRADED
        else:
            overall = HealthStatus.HEALTHY

        return {
            "status": overall.value,
            "timestamp": datetime.now(UTC).isoformat(),
            "checks": {
                r.name: {
                    "status": r.status.value,
                    "message": r.message,
                    "latency_ms": r.latency_ms,
                    "details": r.details,
                }
                for r in results
            },
        }

    def get_last_results(self) -> dict[str, HealthCheck]:
        """Get last health check results.

        Returns:
            Dictionary mapping check name to last result.
        """
        return self._last_results.copy()


class AlertManager:
    """Manages alerts and notifications.

    Supports multiple notification channels (webhook, email, etc.).

    Example:
        >>> manager = AlertManager()
        >>> manager.add_webhook("https://hooks.slack.com/...")
        >>> await manager.send_alert(Alert(...))
    """

    def __init__(self) -> None:
        """Initialize alert manager."""
        self._handlers: list[AlertHandler] = []
        self._webhooks: list[str] = []
        self._alert_history: list[Alert] = []
        self._max_history = 1000
        self._client = httpx.AsyncClient(timeout=10.0)

    def add_handler(self, handler: AlertHandler) -> None:
        """Add a custom alert handler.

        Args:
            handler: Async function to handle alerts.
        """
        self._handlers.append(handler)

    def add_webhook(self, url: str) -> None:
        """Add a webhook URL for alerts.

        Args:
            url: Webhook URL (Slack, Discord, etc.).
        """
        self._webhooks.append(url)

    async def send_alert(self, alert: Alert) -> None:
        """Send an alert to all configured channels.

        Args:
            alert: Alert to send.
        """
        # Store in history
        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history :]

        # Send to webhooks
        for webhook in self._webhooks:
            await self._send_webhook(webhook, alert)

        # Send to custom handlers
        for handler in self._handlers:
            with contextlib.suppress(Exception):  # Don't fail on handler errors
                await handler(alert)

    async def _send_webhook(self, url: str, alert: Alert) -> None:
        """Send alert to webhook.

        Args:
            url: Webhook URL.
            alert: Alert to send.
        """
        # Format for Slack-compatible webhooks
        color = {
            AlertSeverity.INFO: "#36a64f",
            AlertSeverity.WARNING: "#ffcc00",
            AlertSeverity.ERROR: "#ff6600",
            AlertSeverity.CRITICAL: "#ff0000",
        }.get(alert.severity, "#808080")

        payload = {
            "attachments": [
                {
                    "color": color,
                    "title": f"[{alert.severity.value.upper()}] {alert.name}",
                    "text": alert.message,
                    "fields": [
                        {"title": "Source", "value": alert.source, "short": True},
                        {
                            "title": "Time",
                            "value": datetime.fromtimestamp(
                                alert.timestamp, tz=UTC
                            ).isoformat(),
                            "short": True,
                        },
                    ],
                    "footer": "NewsDigest Alert",
                }
            ]
        }

        with contextlib.suppress(Exception):  # Don't fail on webhook errors
            await self._client.post(url, json=payload)

    def get_recent_alerts(
        self,
        limit: int = 100,
        severity: AlertSeverity | None = None,
    ) -> list[Alert]:
        """Get recent alerts.

        Args:
            limit: Maximum alerts to return.
            severity: Filter by severity.

        Returns:
            List of recent alerts.
        """
        alerts = self._alert_history
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        return alerts[-limit:]

    async def close(self) -> None:
        """Close HTTP client."""
        await self._client.aclose()


class MetricsCollector:
    """Collects and stores metrics.

    Provides a simple interface for recording metrics that can
    be exported to monitoring systems.

    Example:
        >>> collector = MetricsCollector()
        >>> collector.record("extraction_time_ms", 150.5)
        >>> collector.record("articles_processed", 1, tags={"source": "rss"})
    """

    def __init__(self, max_points: int = 10000) -> None:
        """Initialize metrics collector.

        Args:
            max_points: Maximum data points to keep per metric.
        """
        self._metrics: dict[str, list[MetricPoint]] = {}
        self._max_points = max_points
        self._counters: dict[str, float] = {}

    def record(
        self,
        name: str,
        value: float,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Record a metric value.

        Args:
            name: Metric name.
            value: Metric value.
            tags: Optional tags for the metric.
        """
        point = MetricPoint(name=name, value=value, tags=tags or {})

        if name not in self._metrics:
            self._metrics[name] = []

        self._metrics[name].append(point)

        # Trim old points
        if len(self._metrics[name]) > self._max_points:
            self._metrics[name] = self._metrics[name][-self._max_points :]

    def increment(
        self,
        name: str,
        value: float = 1.0,
        tags: dict[str, str] | None = None,
    ) -> None:
        """Increment a counter metric.

        Args:
            name: Counter name.
            value: Amount to increment.
            tags: Optional tags.
        """
        key = f"{name}:{tags}" if tags else name
        self._counters[key] = self._counters.get(key, 0) + value
        self.record(name, self._counters[key], tags)

    def get_metric(
        self,
        name: str,
        since: float | None = None,
    ) -> list[MetricPoint]:
        """Get metric data points.

        Args:
            name: Metric name.
            since: Only points after this timestamp.

        Returns:
            List of metric points.
        """
        points = self._metrics.get(name, [])
        if since:
            points = [p for p in points if p.timestamp >= since]
        return points

    def get_summary(self, name: str) -> dict[str, float]:
        """Get summary statistics for a metric.

        Args:
            name: Metric name.

        Returns:
            Dictionary with min, max, avg, count.
        """
        points = self._metrics.get(name, [])
        if not points:
            return {"min": 0, "max": 0, "avg": 0, "count": 0}

        values = [p.value for p in points]
        return {
            "min": min(values),
            "max": max(values),
            "avg": sum(values) / len(values),
            "count": len(values),
        }

    def get_all_metrics(self) -> dict[str, dict[str, float]]:
        """Get summaries for all metrics.

        Returns:
            Dictionary mapping metric name to summary.
        """
        return {name: self.get_summary(name) for name in self._metrics}

    def clear(self) -> None:
        """Clear all metrics."""
        self._metrics.clear()
        self._counters.clear()


class ServiceMonitor:
    """Comprehensive service monitoring.

    Combines health checks, alerts, and metrics into a single
    monitoring solution.

    Example:
        >>> monitor = ServiceMonitor()
        >>> monitor.register_health_check("api", check_api)
        >>> monitor.add_alert_webhook("https://hooks.slack.com/...")
        >>> await monitor.start()
    """

    def __init__(
        self,
        check_interval: float = 60.0,
        alert_on_unhealthy: bool = True,
    ) -> None:
        """Initialize service monitor.

        Args:
            check_interval: Seconds between health checks.
            alert_on_unhealthy: Send alerts when unhealthy.
        """
        self.health = HealthMonitor()
        self.alerts = AlertManager()
        self.metrics = MetricsCollector()
        self._check_interval = check_interval
        self._alert_on_unhealthy = alert_on_unhealthy
        self._running = False
        self._task: asyncio.Task[None] | None = None

    def register_health_check(
        self,
        name: str,
        check_fn: HealthCheckFn,
    ) -> None:
        """Register a health check.

        Args:
            name: Check name.
            check_fn: Check function.
        """
        self.health.register_check(name, check_fn)

    def add_alert_webhook(self, url: str) -> None:
        """Add alert webhook.

        Args:
            url: Webhook URL.
        """
        self.alerts.add_webhook(url)

    async def start(self) -> None:
        """Start background monitoring."""
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop background monitoring."""
        self._running = False
        if self._task:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task

    async def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._running:
            try:
                result = await self.health.check_health()

                # Record metrics
                for name, check in result.get("checks", {}).items():
                    self.metrics.record(
                        f"health_check_{name}_latency_ms",
                        check.get("latency_ms", 0),
                    )
                    status_value = 1 if check.get("status") == "healthy" else 0
                    self.metrics.record(
                        f"health_check_{name}_status",
                        status_value,
                    )

                # Send alerts for unhealthy services
                if self._alert_on_unhealthy:
                    for name, check in result.get("checks", {}).items():
                        if check.get("status") == "unhealthy":
                            await self.alerts.send_alert(
                                Alert(
                                    name=f"Health Check Failed: {name}",
                                    severity=AlertSeverity.ERROR,
                                    message=check.get("message", "Health check failed"),
                                    details=check,
                                )
                            )

            except Exception as e:
                # Don't crash on monitor errors
                logger.warning(f"Health monitor check failed: {e}")

            await asyncio.sleep(self._check_interval)

    async def get_status(self) -> dict[str, Any]:
        """Get current monitoring status.

        Returns:
            Dictionary with health, metrics, and recent alerts.
        """
        health = await self.health.check_health()
        return {
            "health": health,
            "metrics": self.metrics.get_all_metrics(),
            "recent_alerts": [
                {
                    "name": a.name,
                    "severity": a.severity.value,
                    "message": a.message,
                    "timestamp": a.timestamp,
                }
                for a in self.alerts.get_recent_alerts(limit=10)
            ],
        }


# =============================================================================
# Pre-built Health Checks
# =============================================================================


async def check_memory() -> HealthCheck:
    """Check memory usage.

    Returns:
        Health check result.
    """
    import sys

    # Get basic memory info
    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF)
        memory_mb = usage.ru_maxrss / 1024  # Convert to MB on Linux
        if sys.platform == "darwin":
            memory_mb = usage.ru_maxrss / (1024 * 1024)  # Bytes on macOS
    except ImportError:
        memory_mb = 0

    # Consider > 1GB as degraded, > 2GB as unhealthy
    if memory_mb > 2048:
        status = HealthStatus.UNHEALTHY
    elif memory_mb > 1024:
        status = HealthStatus.DEGRADED
    else:
        status = HealthStatus.HEALTHY

    return HealthCheck(
        name="memory",
        status=status,
        message=f"Memory usage: {memory_mb:.1f} MB",
        details={"memory_mb": memory_mb},
    )


async def check_disk(path: str = "/") -> HealthCheck:
    """Check disk space.

    Args:
        path: Path to check.

    Returns:
        Health check result.
    """
    import shutil

    try:
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024**3)
        total_gb = usage.total / (1024**3)
        used_percent = (usage.used / usage.total) * 100

        if used_percent > 95:
            status = HealthStatus.UNHEALTHY
        elif used_percent > 85:
            status = HealthStatus.DEGRADED
        else:
            status = HealthStatus.HEALTHY

        return HealthCheck(
            name="disk",
            status=status,
            message=f"Disk: {used_percent:.1f}% used, {free_gb:.1f} GB free",
            details={
                "free_gb": free_gb,
                "total_gb": total_gb,
                "used_percent": used_percent,
            },
        )
    except Exception as e:
        return HealthCheck(
            name="disk",
            status=HealthStatus.UNHEALTHY,
            message=str(e),
        )


def create_http_check(
    name: str,
    url: str,
    timeout: float = 5.0,
) -> HealthCheckFn:
    """Create an HTTP health check.

    Args:
        name: Check name.
        url: URL to check.
        timeout: Request timeout.

    Returns:
        Health check function.
    """

    async def check() -> HealthCheck:
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.get(url)
                if response.status_code < 400:
                    return HealthCheck(
                        name=name,
                        status=HealthStatus.HEALTHY,
                        message=f"HTTP {response.status_code}",
                        details={"status_code": response.status_code},
                    )
                else:
                    return HealthCheck(
                        name=name,
                        status=HealthStatus.UNHEALTHY,
                        message=f"HTTP {response.status_code}",
                        details={"status_code": response.status_code},
                    )
            except Exception as e:
                return HealthCheck(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message=str(e),
                )

    return check
