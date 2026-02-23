"""Caching implementations for NewsDigest."""

import asyncio
import fnmatch
import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generic, TypeVar

from newsdigest.storage.base import BaseStorage, SyncStorage

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """A cached item with metadata."""

    value: T
    created_at: float
    expires_at: float | None = None

    def is_expired(self) -> bool:
        """Check if the entry has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at


class MemoryCache(BaseStorage[T]):
    """In-memory cache with TTL support.

    Fast, ephemeral cache that lives for the duration of the process.
    Useful for caching extraction results during a session.

    TODO: Consider replacing with cachetools.TTLCache for production use —
    it handles eviction policies and thread safety more robustly.
    """

    def __init__(self, max_size: int = 1000, default_ttl: int | None = 3600) -> None:
        """Initialize memory cache.

        Args:
            max_size: Maximum number of items to store.
            default_ttl: Default TTL in seconds (None = no expiry).
        """
        self._cache: dict[str, CacheEntry[T]] = {}
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> T | None:
        """Retrieve an item from cache."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            if entry.is_expired():
                del self._cache[key]
                return None

            return entry.value

    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Store an item in cache."""
        async with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self._max_size:
                self._evict_oldest()

            actual_ttl = ttl if ttl is not None else self._default_ttl
            expires_at = time.time() + actual_ttl if actual_ttl else None

            self._cache[key] = CacheEntry(
                value=value,
                created_at=time.time(),
                expires_at=expires_at,
            )

    async def delete(self, key: str) -> bool:
        """Delete an item from cache."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        """Check if an item exists in cache."""
        async with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return False
            if entry.is_expired():
                del self._cache[key]
                return False
            return True

    async def clear(self) -> None:
        """Clear all cached items."""
        async with self._lock:
            self._cache.clear()

    async def keys(self, pattern: str | None = None) -> list[str]:
        """Get all cache keys, optionally filtered by pattern."""
        async with self._lock:
            # Clean expired entries first
            self._clean_expired()

            if pattern is None:
                return list(self._cache.keys())

            return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]

    def _evict_oldest(self) -> None:
        """Evict the oldest cache entry."""
        if not self._cache:
            return

        oldest_key = min(
            self._cache.keys(),
            key=lambda k: self._cache[k].created_at,
        )
        del self._cache[oldest_key]

    def _clean_expired(self) -> None:
        """Remove all expired entries."""
        expired = [k for k, v in self._cache.items() if v.is_expired()]
        for key in expired:
            del self._cache[key]


class FileCache(SyncStorage[dict[str, Any]]):
    """File-based cache for persistent storage.

    Stores cached items as JSON files in a directory.
    Survives process restarts.
    """

    def __init__(
        self,
        cache_dir: Path | str,
        default_ttl: int | None = 86400,
    ) -> None:
        """Initialize file cache.

        Args:
            cache_dir: Directory to store cache files.
            default_ttl: Default TTL in seconds (None = no expiry).
        """
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._default_ttl = default_ttl

    def get(self, key: str) -> dict[str, Any] | None:
        """Retrieve an item from cache."""
        file_path = self._key_to_path(key)
        if not file_path.exists():
            return None

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                entry = json.load(f)

            # Check expiry
            expires_at = entry.get("expires_at")
            if expires_at and time.time() > expires_at:
                file_path.unlink()
                return None

            return entry.get("value")
        except (json.JSONDecodeError, OSError):
            return None

    def set(
        self,
        key: str,
        value: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """Store an item in cache."""
        file_path = self._key_to_path(key)

        actual_ttl = ttl if ttl is not None else self._default_ttl
        expires_at = time.time() + actual_ttl if actual_ttl else None

        entry = {
            "value": value,
            "created_at": time.time(),
            "expires_at": expires_at,
        }

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(entry, f)

    def delete(self, key: str) -> bool:
        """Delete an item from cache."""
        file_path = self._key_to_path(key)
        if file_path.exists():
            file_path.unlink()
            return True
        return False

    def exists(self, key: str) -> bool:
        """Check if an item exists in cache."""
        return self.get(key) is not None

    def clear(self) -> None:
        """Clear all cached items."""
        for file_path in self._cache_dir.glob("*.json"):
            file_path.unlink()

    def keys(self, pattern: str | None = None) -> list[str]:
        """Get all cache keys."""
        # FIXME: Cannot recover original keys from hashed filenames;
        # consider storing a key->hash mapping separately
        keys = [f.stem for f in self._cache_dir.glob("*.json")]
        if pattern:
            keys = [k for k in keys if fnmatch.fnmatch(k, pattern)]
        return keys

    def _key_to_path(self, key: str) -> Path:
        """Convert a key to a file path."""
        # Hash the key to create a safe filename
        key_hash = hashlib.sha256(key.encode()).hexdigest()[:16]
        return self._cache_dir / f"{key_hash}.json"


def cache_key_for_url(url: str) -> str:
    """Generate a cache key for a URL.

    Args:
        url: The URL to generate a key for.

    Returns:
        A cache key string.
    """
    return f"url:{hashlib.sha256(url.encode()).hexdigest()[:32]}"


def cache_key_for_text(text: str) -> str:
    """Generate a cache key for text content.

    Args:
        text: The text to generate a key for.

    Returns:
        A cache key string.
    """
    return f"text:{hashlib.sha256(text.encode()).hexdigest()[:32]}"
