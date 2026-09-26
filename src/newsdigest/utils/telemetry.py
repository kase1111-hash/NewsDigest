"""
Telemetry Collection for NewsDigest.

This module provides application-level telemetry for tracking:
- Feature usage and adoption
- User sessions and workflows
- Performance characteristics
- Error patterns and diagnostics

Privacy:
- No PII is collected by default
- URLs are hashed for privacy
- All telemetry can be disabled via configuration

Usage:
    from newsdigest.utils.telemetry import get_telemetry, TelemetryConfig

    # Initialize
    config = TelemetryConfig(enabled=True)
    telemetry = get_telemetry(config)

    # Track events
    telemetry.track_event("extraction_started", {"source": "rss"})
    telemetry.track_feature_usage("digest_generation")

    # Track session
    with telemetry.session("cli_session"):
        # do work
        pass
"""

from __future__ import annotations

import hashlib
import logging
import platform
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from newsdigest.version import __version__


if TYPE_CHECKING:
    from collections.abc import Generator

logger = logging.getLogger(__name__)


@dataclass
class TelemetryEvent:
    """A telemetry event."""

    event_name: str
    timestamp: datetime
    session_id: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class TelemetryConfig:
    """Configuration for telemetry collection."""

    enabled: bool = True
    anonymize_urls: bool = True
    include_system_info: bool = True
    max_events_buffer: int = 1000
    flush_threshold: int = 100


@dataclass
class SessionInfo:
    """Information about a telemetry session."""

    session_id: str
    start_time: datetime
    end_time: datetime | None = None
    event_count: int = 0
    properties: dict[str, Any] = field(default_factory=dict)


class TelemetryCollector:
    """Collects and manages telemetry data."""

    def __init__(self, config: TelemetryConfig | None = None) -> None:
        self._config = config or TelemetryConfig()
        self._events: list[TelemetryEvent] = []
        self._sessions: dict[str, SessionInfo] = {}
        self._current_session_id: str | None = None
        self._feature_usage: dict[str, int] = {}
        self._lock = threading.Lock()
        self._system_info: dict[str, str] | None = None

    @property
    def enabled(self) -> bool:
        """Check if telemetry is enabled."""
        return self._config.enabled

    def _get_system_info(self) -> dict[str, str]:
        """Get anonymized system information."""
        if self._system_info is None and self._config.include_system_info:
            self._system_info = {
                "os": platform.system(),
                "os_version": platform.release(),
                "python_version": platform.python_version(),
                "newsdigest_version": __version__,
                "architecture": platform.machine(),
            }
        return self._system_info or {}

    def _anonymize_url(self, url: str) -> str:
        """Hash URL for privacy."""
        if not self._config.anonymize_urls:
            return url
        return hashlib.sha256(url.encode()).hexdigest()[:16]

    def _sanitize_properties(self, properties: dict[str, Any]) -> dict[str, Any]:
        """Sanitize properties to remove sensitive data."""
        sanitized = {}
        sensitive_keys = {
            "password",
            "token",
            "api_key",
            "secret",
            "auth",
            "credential",
        }

        for key, value in properties.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                sanitized[key] = "[REDACTED]"
            elif key_lower == "url" and isinstance(value, str):
                sanitized[key] = self._anonymize_url(value)
            elif isinstance(value, str) and len(value) > 500:
                sanitized[key] = value[:500] + "...[truncated]"
            else:
                sanitized[key] = value

        return sanitized

    def track_event(
        self,
        event_name: str,
        properties: dict[str, Any] | None = None,
    ) -> None:
        """Track a telemetry event."""
        if not self._config.enabled:
            return

        with self._lock:
            event = TelemetryEvent(
                event_name=event_name,
                timestamp=datetime.now(UTC),
                session_id=self._current_session_id,
                properties=self._sanitize_properties(properties or {}),
            )
            self._events.append(event)

            if self._current_session_id and self._current_session_id in self._sessions:
                self._sessions[self._current_session_id].event_count += 1

            if len(self._events) > self._config.max_events_buffer:
                self._events = self._events[-self._config.max_events_buffer :]

            if len(self._events) >= self._config.flush_threshold:
                self._flush_internal()

    def track_feature_usage(self, feature_name: str) -> None:
        """Track usage of a specific feature."""
        if not self._config.enabled:
            return

        with self._lock:
            self._feature_usage[feature_name] = (
                self._feature_usage.get(feature_name, 0) + 1
            )

        self.track_event("feature_used", {"feature": feature_name})

    def track_extraction(
        self,
        url: str,
        source_type: str,
        success: bool,
        duration_ms: float,
        word_count: int = 0,
        error_type: str | None = None,
    ) -> None:
        """Track an extraction operation."""
        properties = {
            "url": url,
            "source_type": source_type,
            "success": success,
            "duration_ms": duration_ms,
            "word_count": word_count,
        }
        if error_type:
            properties["error_type"] = error_type

        self.track_event("extraction_completed", properties)

    def track_digest_generation(
        self,
        article_count: int,
        output_format: str,
        duration_ms: float,
    ) -> None:
        """Track digest generation."""
        self.track_event(
            "digest_generated",
            {
                "article_count": article_count,
                "output_format": output_format,
                "duration_ms": duration_ms,
            },
        )

    def track_error(
        self,
        error_type: str,
        component: str,
        message: str | None = None,
    ) -> None:
        """Track an error occurrence."""
        properties = {
            "error_type": error_type,
            "component": component,
        }
        if message:
            properties["message"] = message[:200]

        self.track_event("error_occurred", properties)

    def start_session(
        self,
        session_type: str = "default",
        properties: dict[str, Any] | None = None,
    ) -> str:
        """Start a new telemetry session."""
        session_id = str(uuid.uuid4())

        with self._lock:
            session_props = {"session_type": session_type}
            session_props.update(self._get_system_info())
            if properties:
                session_props.update(self._sanitize_properties(properties))

            self._sessions[session_id] = SessionInfo(
                session_id=session_id,
                start_time=datetime.now(UTC),
                properties=session_props,
            )
            self._current_session_id = session_id

        self.track_event("session_started", {"session_type": session_type})
        return session_id

    def end_session(self, session_id: str | None = None) -> None:
        """End a telemetry session."""
        sid = session_id or self._current_session_id
        if not sid:
            return

        with self._lock:
            if sid in self._sessions:
                session = self._sessions[sid]
                session.end_time = datetime.now(UTC)

                duration = (session.end_time - session.start_time).total_seconds()
                self.track_event(
                    "session_ended",
                    {
                        "session_id": sid,
                        "duration_seconds": duration,
                        "event_count": session.event_count,
                    },
                )

            if self._current_session_id == sid:
                self._current_session_id = None

    @contextmanager
    def session(
        self,
        session_type: str = "default",
        properties: dict[str, Any] | None = None,
    ) -> Generator[str, None, None]:
        """Context manager for telemetry sessions."""
        session_id = self.start_session(session_type, properties)
        try:
            yield session_id
        finally:
            self.end_session(session_id)

    def get_feature_usage(self) -> dict[str, int]:
        """Get feature usage statistics."""
        with self._lock:
            return dict(self._feature_usage)

    def get_events(self, limit: int = 100) -> list[TelemetryEvent]:
        """Get recent events."""
        with self._lock:
            return list(self._events[-limit:])

    def get_session_info(self, session_id: str) -> SessionInfo | None:
        """Get information about a session."""
        with self._lock:
            return self._sessions.get(session_id)

    def _flush_internal(self) -> None:
        """Internal flush without lock (caller must hold lock)."""
        if not self._events:
            return

        logger.debug(
            "Flushing %d telemetry events",
            len(self._events),
        )

    def flush(self) -> None:
        """Flush buffered telemetry data."""
        with self._lock:
            self._flush_internal()

    def get_summary(self) -> dict[str, Any]:
        """Get a summary of collected telemetry."""
        with self._lock:
            total_events = len(self._events)
            event_types: dict[str, int] = {}
            for event in self._events:
                event_types[event.event_name] = event_types.get(event.event_name, 0) + 1

            return {
                "total_events": total_events,
                "event_types": event_types,
                "feature_usage": dict(self._feature_usage),
                "active_sessions": sum(
                    1 for s in self._sessions.values() if s.end_time is None
                ),
                "total_sessions": len(self._sessions),
                "system_info": self._get_system_info(),
            }

    def clear(self) -> None:
        """Clear all telemetry data."""
        with self._lock:
            self._events.clear()
            self._sessions.clear()
            self._feature_usage.clear()
            self._current_session_id = None


# Global telemetry instance
_telemetry_instance: TelemetryCollector | None = None
_telemetry_lock = threading.Lock()


def get_telemetry(config: TelemetryConfig | None = None) -> TelemetryCollector:
    """Get or create the global telemetry collector."""
    global _telemetry_instance
    with _telemetry_lock:
        if _telemetry_instance is None:
            _telemetry_instance = TelemetryCollector(config)
        return _telemetry_instance


def configure_telemetry(config: TelemetryConfig | None = None) -> TelemetryCollector:
    """Configure the global telemetry collector."""
    global _telemetry_instance
    with _telemetry_lock:
        _telemetry_instance = TelemetryCollector(config)
        return _telemetry_instance


def reset_telemetry() -> None:
    """Reset the global telemetry collector."""
    global _telemetry_instance
    with _telemetry_lock:
        if _telemetry_instance:
            _telemetry_instance.clear()
        _telemetry_instance = None


# Convenience functions
def track_event(event_name: str, properties: dict[str, Any] | None = None) -> None:
    """Track an event using global telemetry."""
    get_telemetry().track_event(event_name, properties)


def track_feature_usage(feature_name: str) -> None:
    """Track feature usage using global telemetry."""
    get_telemetry().track_feature_usage(feature_name)


def track_error(error_type: str, component: str, message: str | None = None) -> None:
    """Track an error using global telemetry."""
    get_telemetry().track_error(error_type, component, message)
