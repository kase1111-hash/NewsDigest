"""Data persistence for NewsDigest."""

from newsdigest.storage.analytics import (
    AggregateStats,
    AnalyticsStore,
    ExtractionRecord,
    SourceStore,
)
from newsdigest.storage.base import BaseStorage, SyncStorage
from newsdigest.storage.cache import (
    CacheEntry,
    FileCache,
    MemoryCache,
    cache_key_for_text,
    cache_key_for_url,
)
from newsdigest.storage.database import Database


__all__ = [
    "AggregateStats",
    "AnalyticsStore",
    "BaseStorage",
    "CacheEntry",
    "Database",
    "ExtractionRecord",
    "FileCache",
    "MemoryCache",
    "SourceStore",
    "SyncStorage",
    "cache_key_for_text",
    "cache_key_for_url",
]
