"""Analytics storage for NewsDigest."""

import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
class ExtractionRecord:
    """Record of a single extraction."""

    id: str
    timestamp: float
    source_url: str | None = None
    source_type: str = "text"  # url, rss, text
    original_words: int = 0
    compressed_words: int = 0
    compression_ratio: float = 0.0
    claims_extracted: int = 0
    speculation_removed: int = 0
    emotional_removed: int = 0
    unnamed_sources: int = 0
    processing_time_ms: float = 0.0
    success: bool = True
    error: str | None = None


@dataclass
class AggregateStats:
    """Aggregated statistics over a time period."""

    period_start: float
    period_end: float
    total_extractions: int = 0
    successful_extractions: int = 0
    failed_extractions: int = 0
    total_original_words: int = 0
    total_compressed_words: int = 0
    avg_compression_ratio: float = 0.0
    total_claims: int = 0
    total_speculation_removed: int = 0
    total_emotional_removed: int = 0
    avg_processing_time_ms: float = 0.0


class AnalyticsStore:
    """Storage for extraction analytics and statistics.

    Tracks extraction history and provides aggregated statistics.
    Data is stored in a JSON file for persistence.
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        """Initialize analytics store.

        Args:
            storage_path: Path to storage file. If None, uses in-memory only.
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._records: list[ExtractionRecord] = []
        self._load()

    def record_extraction(
        self,
        id: str,
        source_url: str | None = None,
        source_type: str = "text",
        original_words: int = 0,
        compressed_words: int = 0,
        claims_extracted: int = 0,
        speculation_removed: int = 0,
        emotional_removed: int = 0,
        unnamed_sources: int = 0,
        processing_time_ms: float = 0.0,
        success: bool = True,
        error: str | None = None,
    ) -> ExtractionRecord:
        """Record an extraction event.

        Args:
            id: Unique extraction ID.
            source_url: Source URL if applicable.
            source_type: Type of source (url, rss, text).
            original_words: Original word count.
            compressed_words: Compressed word count.
            claims_extracted: Number of claims extracted.
            speculation_removed: Count of speculation removed.
            emotional_removed: Count of emotional language removed.
            unnamed_sources: Count of unnamed source references.
            processing_time_ms: Processing time in milliseconds.
            success: Whether extraction succeeded.
            error: Error message if failed.

        Returns:
            The recorded extraction record.
        """
        compression = (
            1 - (compressed_words / original_words) if original_words > 0 else 0.0
        )

        record = ExtractionRecord(
            id=id,
            timestamp=time.time(),
            source_url=source_url,
            source_type=source_type,
            original_words=original_words,
            compressed_words=compressed_words,
            compression_ratio=compression,
            claims_extracted=claims_extracted,
            speculation_removed=speculation_removed,
            emotional_removed=emotional_removed,
            unnamed_sources=unnamed_sources,
            processing_time_ms=processing_time_ms,
            success=success,
            error=error,
        )

        self._records.append(record)
        self._save()

        return record

    def get_records(
        self,
        since: float | None = None,
        until: float | None = None,
        limit: int | None = None,
        source_type: str | None = None,
    ) -> list[ExtractionRecord]:
        """Get extraction records with optional filters.

        Args:
            since: Only records after this timestamp.
            until: Only records before this timestamp.
            limit: Maximum number of records to return.
            source_type: Filter by source type.

        Returns:
            List of matching extraction records.
        """
        records = self._records

        if since is not None:
            records = [r for r in records if r.timestamp >= since]

        if until is not None:
            records = [r for r in records if r.timestamp <= until]

        if source_type is not None:
            records = [r for r in records if r.source_type == source_type]

        # Sort by timestamp descending (newest first)
        records = sorted(records, key=lambda r: r.timestamp, reverse=True)

        if limit is not None:
            records = records[:limit]

        return records

    def get_aggregate_stats(
        self,
        since: float | None = None,
        until: float | None = None,
    ) -> AggregateStats:
        """Get aggregated statistics for a time period.

        Args:
            since: Start of period (timestamp).
            until: End of period (timestamp).

        Returns:
            Aggregated statistics.
        """
        records = self.get_records(since=since, until=until)

        if not records:
            return AggregateStats(
                period_start=since or 0,
                period_end=until or time.time(),
            )

        successful = [r for r in records if r.success]

        total_original = sum(r.original_words for r in successful)
        total_compressed = sum(r.compressed_words for r in successful)
        avg_compression = (
            1 - (total_compressed / total_original) if total_original > 0 else 0.0
        )

        processing_times = [r.processing_time_ms for r in successful]
        avg_processing = (
            sum(processing_times) / len(processing_times) if processing_times else 0.0
        )

        return AggregateStats(
            period_start=since or min(r.timestamp for r in records),
            period_end=until or max(r.timestamp for r in records),
            total_extractions=len(records),
            successful_extractions=len(successful),
            failed_extractions=len(records) - len(successful),
            total_original_words=total_original,
            total_compressed_words=total_compressed,
            avg_compression_ratio=avg_compression,
            total_claims=sum(r.claims_extracted for r in successful),
            total_speculation_removed=sum(r.speculation_removed for r in successful),
            total_emotional_removed=sum(r.emotional_removed for r in successful),
            avg_processing_time_ms=avg_processing,
        )

    def get_daily_stats(self, days: int = 7) -> list[AggregateStats]:
        """Get daily aggregate stats for recent days.

        Args:
            days: Number of days to include.

        Returns:
            List of daily aggregate stats.
        """
        stats = []
        now = time.time()

        for i in range(days):
            day_end = now - (i * 86400)
            day_start = day_end - 86400
            daily = self.get_aggregate_stats(since=day_start, until=day_end)
            stats.append(daily)

        return stats

    def clear(self) -> None:
        """Clear all stored records."""
        self._records = []
        self._save()

    def _load(self) -> None:
        """Load records from storage file."""
        if self._storage_path is None or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open(encoding="utf-8") as f:
                data = json.load(f)

            self._records = [
                ExtractionRecord(**record) for record in data.get("records", [])
            ]
        except (json.JSONDecodeError, OSError):
            self._records = []

    def _save(self) -> None:
        """Save records to storage file."""
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {"records": [asdict(r) for r in self._records]}

        with self._storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)


class SourceStore:
    """Storage for configured news sources.

    Persists RSS feeds and other sources for digest generation.
    """

    def __init__(self, storage_path: Path | str | None = None) -> None:
        """Initialize source store.

        Args:
            storage_path: Path to storage file.
        """
        self._storage_path = Path(storage_path) if storage_path else None
        self._sources: list[dict[str, Any]] = []
        self._load()

    def add_source(
        self,
        source_type: str,
        url: str,
        name: str | None = None,
        category: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Add a news source.

        Args:
            source_type: Type of source (rss, url, newsapi).
            url: Source URL.
            name: Display name.
            category: Category for grouping.
            **kwargs: Additional source-specific options.

        Returns:
            The added source dictionary.
        """
        source = {
            "type": source_type,
            "url": url,
            "name": name or url,
            "category": category,
            "added_at": time.time(),
            **kwargs,
        }

        self._sources.append(source)
        self._save()

        return source

    def remove_source(self, url: str) -> bool:
        """Remove a source by URL.

        Args:
            url: Source URL to remove.

        Returns:
            True if source was removed, False if not found.
        """
        original_count = len(self._sources)
        self._sources = [s for s in self._sources if s.get("url") != url]

        if len(self._sources) < original_count:
            self._save()
            return True
        return False

    def get_sources(
        self,
        source_type: str | None = None,
        category: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get configured sources with optional filters.

        Args:
            source_type: Filter by source type.
            category: Filter by category.

        Returns:
            List of matching sources.
        """
        sources = self._sources

        if source_type is not None:
            sources = [s for s in sources if s.get("type") == source_type]

        if category is not None:
            sources = [s for s in sources if s.get("category") == category]

        return sources

    def get_categories(self) -> list[str]:
        """Get list of unique categories.

        Returns:
            List of category names.
        """
        categories = set()
        for source in self._sources:
            if source.get("category"):
                categories.add(source["category"])
        return sorted(categories)

    def clear(self) -> None:
        """Clear all stored sources."""
        self._sources = []
        self._save()

    def _load(self) -> None:
        """Load sources from storage file."""
        if self._storage_path is None or not self._storage_path.exists():
            return

        try:
            with self._storage_path.open(encoding="utf-8") as f:
                data = json.load(f)
            self._sources = data.get("sources", [])
        except (json.JSONDecodeError, OSError):
            self._sources = []

    def _save(self) -> None:
        """Save sources to storage file."""
        if self._storage_path is None:
            return

        self._storage_path.parent.mkdir(parents=True, exist_ok=True)

        data = {"sources": self._sources}

        with self._storage_path.open("w", encoding="utf-8") as f:
            json.dump(data, f)
