"""End-to-end tests for the storage layer.

Tests cache, database, and analytics storage.
"""

import tempfile
import time
from pathlib import Path

import pytest

from newsdigest.storage import (
    AnalyticsStore,
    Database,
    ExtractionRecord,
    FileCache,
    MemoryCache,
    SourceStore,
)


class TestMemoryCache:
    """Tests for in-memory cache."""

    @pytest.fixture
    def cache(self) -> MemoryCache:
        """Create a memory cache."""
        return MemoryCache(max_size=100, default_ttl=60)

    @pytest.mark.asyncio
    async def test_set_and_get(self, cache: MemoryCache):
        """Test basic set and get."""
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, cache: MemoryCache):
        """Test getting nonexistent key."""
        result = await cache.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, cache: MemoryCache):
        """Test deleting a key."""
        await cache.set("key1", "value1")
        deleted = await cache.delete("key1")
        assert deleted is True

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_exists(self, cache: MemoryCache):
        """Test exists check."""
        await cache.set("key1", "value1")

        assert await cache.exists("key1") is True
        assert await cache.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear(self, cache: MemoryCache):
        """Test clearing cache."""
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        await cache.clear()

        assert await cache.get("key1") is None
        assert await cache.get("key2") is None

    @pytest.mark.asyncio
    async def test_ttl_expiry(self):
        """Test TTL expiration."""
        cache = MemoryCache(default_ttl=1)  # 1 second TTL

        await cache.set("key1", "value1")
        assert await cache.get("key1") == "value1"

        # Wait for expiry
        time.sleep(1.5)

        result = await cache.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_max_size_eviction(self):
        """Test max size eviction."""
        cache = MemoryCache(max_size=3, default_ttl=None)

        await cache.set("key1", "value1")
        await cache.set("key2", "value2")
        await cache.set("key3", "value3")
        await cache.set("key4", "value4")  # Should evict oldest

        # One of the first keys should be evicted
        keys = await cache.keys()
        assert len(keys) <= 3

    @pytest.mark.asyncio
    async def test_keys_with_pattern(self, cache: MemoryCache):
        """Test getting keys with pattern."""
        await cache.set("user:1", "data1")
        await cache.set("user:2", "data2")
        await cache.set("item:1", "item1")

        user_keys = await cache.keys("user:*")
        assert len(user_keys) == 2
        assert all(k.startswith("user:") for k in user_keys)

    @pytest.mark.asyncio
    async def test_complex_values(self, cache: MemoryCache):
        """Test caching complex values."""
        data = {
            "name": "test",
            "values": [1, 2, 3],
            "nested": {"key": "value"},
        }

        await cache.set("complex", data)
        result = await cache.get("complex")

        assert result == data


class TestFileCache:
    """Tests for file-based cache."""

    @pytest.fixture
    def cache_dir(self) -> Path:
        """Create a temporary cache directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def cache(self, cache_dir: Path) -> FileCache:
        """Create a file cache."""
        return FileCache(cache_dir, default_ttl=60)

    def test_set_and_get(self, cache: FileCache):
        """Test basic set and get."""
        cache.set("key1", {"value": "data1"})
        result = cache.get("key1")
        assert result == {"value": "data1"}

    def test_get_nonexistent(self, cache: FileCache):
        """Test getting nonexistent key."""
        result = cache.get("nonexistent")
        assert result is None

    def test_delete(self, cache: FileCache):
        """Test deleting a key."""
        cache.set("key1", {"value": "data1"})
        deleted = cache.delete("key1")
        assert deleted is True

        result = cache.get("key1")
        assert result is None

    def test_exists(self, cache: FileCache):
        """Test exists check."""
        cache.set("key1", {"value": "data1"})

        assert cache.exists("key1") is True
        assert cache.exists("nonexistent") is False

    def test_clear(self, cache: FileCache):
        """Test clearing cache."""
        cache.set("key1", {"value": "data1"})
        cache.set("key2", {"value": "data2"})

        cache.clear()

        assert cache.get("key1") is None
        assert cache.get("key2") is None

    def test_persistence(self, cache_dir: Path):
        """Test cache persists across instances."""
        # First instance
        cache1 = FileCache(cache_dir, default_ttl=60)
        cache1.set("persistent", {"data": "test"})

        # Second instance
        cache2 = FileCache(cache_dir, default_ttl=60)
        result = cache2.get("persistent")

        assert result == {"data": "test"}


class TestDatabase:
    """Tests for SQLite database."""

    @pytest.fixture
    def db(self) -> Database:
        """Create an in-memory database."""
        db = Database(None)  # In-memory
        db.initialize()
        return db

    @pytest.fixture
    def file_db(self) -> Database:
        """Create a file-based database."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            db = Database(f.name)
            db.initialize()
            yield db

    def test_save_and_get_extraction(self, db: Database):
        """Test saving and retrieving extractions."""
        record = ExtractionRecord(
            id="ext-001",
            timestamp=time.time(),
            source_url="https://example.com",
            source_type="url",
            original_words=100,
            compressed_words=20,
            compression_ratio=0.8,
            claims_extracted=5,
        )

        db.save_extraction(record)
        records = db.get_extractions(limit=10)

        assert len(records) == 1
        assert records[0].id == "ext-001"

    def test_extraction_filtering(self, db: Database):
        """Test extraction filtering by time and type."""
        now = time.time()

        # Add records
        for i in range(5):
            record = ExtractionRecord(
                id=f"ext-{i}",
                timestamp=now - (i * 3600),  # 1 hour apart
                source_type="url" if i % 2 == 0 else "text",
            )
            db.save_extraction(record)

        # Filter by time
        recent = db.get_extractions(since=now - 7200)  # Last 2 hours
        assert len(recent) <= 3

        # Filter by type
        url_records = db.get_extractions(source_type="url")
        assert all(r.source_type == "url" for r in url_records)

    def test_extraction_stats(self, db: Database):
        """Test aggregated extraction statistics."""
        now = time.time()

        for i in range(10):
            record = ExtractionRecord(
                id=f"ext-{i}",
                timestamp=now,
                original_words=100,
                compressed_words=20,
                claims_extracted=5,
                success=True,
            )
            db.save_extraction(record)

        stats = db.get_extraction_stats()

        assert stats.total_extractions == 10
        assert stats.successful_extractions == 10
        assert stats.total_original_words == 1000
        assert stats.total_claims == 50

    def test_source_management(self, db: Database):
        """Test adding and retrieving sources."""
        db.add_source(
            source_type="rss",
            url="https://example.com/feed",
            name="Example Feed",
            category="tech",
        )

        sources = db.get_sources()
        assert len(sources) == 1
        assert sources[0]["url"] == "https://example.com/feed"

    def test_source_filtering(self, db: Database):
        """Test source filtering."""
        db.add_source("rss", "https://feed1.com", category="tech")
        db.add_source("rss", "https://feed2.com", category="news")
        db.add_source("url", "https://site.com", category="tech")

        tech_sources = db.get_sources(category="tech")
        assert len(tech_sources) == 2

        rss_sources = db.get_sources(source_type="rss")
        assert len(rss_sources) == 2

    def test_cache_operations(self, db: Database):
        """Test database cache operations."""
        db.cache_set("key1", {"data": "value1"})
        result = db.cache_get("key1")

        assert result == {"data": "value1"}

    def test_cache_ttl(self, db: Database):
        """Test cache TTL in database."""
        db.cache_set("expiring", {"data": "test"}, ttl=1)

        # Should exist initially
        assert db.cache_get("expiring") is not None

        # Wait for expiry
        time.sleep(1.5)

        # Should be expired
        assert db.cache_get("expiring") is None

    def test_api_key_operations(self, db: Database):
        """Test API key storage."""
        import hashlib

        key_hash = hashlib.sha256(b"test-key").hexdigest()

        db.save_api_key(
            key_hash=key_hash,
            name="test-app",
            rate_limit=200,
            scopes=["read", "write"],
        )

        key_data = db.get_api_key(key_hash)

        assert key_data is not None
        assert key_data["name"] == "test-app"
        assert key_data["rate_limit"] == 200

    def test_database_stats(self, db: Database):
        """Test getting database statistics."""
        # Add some data
        db.add_source("rss", "https://example.com")
        db.cache_set("key1", {"data": "value"})

        stats = db.get_stats()

        assert "sources" in stats
        assert "cache" in stats
        assert stats["sources"] >= 1
        assert stats["cache"] >= 1


class TestAnalyticsStore:
    """Tests for analytics storage."""

    @pytest.fixture
    def store(self) -> AnalyticsStore:
        """Create an in-memory analytics store."""
        return AnalyticsStore(storage_path=None)

    def test_record_extraction(self, store: AnalyticsStore):
        """Test recording an extraction."""
        record = store.record_extraction(
            id="ext-001",
            source_url="https://example.com",
            original_words=100,
            compressed_words=20,
            claims_extracted=5,
        )

        assert record.id == "ext-001"
        assert record.compression_ratio == 0.8

    def test_get_records(self, store: AnalyticsStore):
        """Test getting records with filters."""
        for i in range(5):
            store.record_extraction(
                id=f"ext-{i}",
                source_type="url" if i % 2 == 0 else "text",
            )

        all_records = store.get_records()
        assert len(all_records) == 5

        url_records = store.get_records(source_type="url")
        assert all(r.source_type == "url" for r in url_records)

    def test_aggregate_stats(self, store: AnalyticsStore):
        """Test aggregated statistics."""
        for i in range(10):
            store.record_extraction(
                id=f"ext-{i}",
                original_words=100,
                compressed_words=20,
                processing_time_ms=50.0,
            )

        stats = store.get_aggregate_stats()

        assert stats.total_extractions == 10
        assert stats.total_original_words == 1000
        assert stats.avg_processing_time_ms == 50.0


class TestSourceStore:
    """Tests for source storage."""

    @pytest.fixture
    def store(self) -> SourceStore:
        """Create an in-memory source store."""
        return SourceStore(storage_path=None)

    def test_add_source(self, store: SourceStore):
        """Test adding a source."""
        source = store.add_source(
            source_type="rss",
            url="https://example.com/feed",
            name="Example",
            category="tech",
        )

        assert source["url"] == "https://example.com/feed"
        assert source["type"] == "rss"

    def test_get_sources(self, store: SourceStore):
        """Test getting sources."""
        store.add_source("rss", "https://feed1.com", category="tech")
        store.add_source("rss", "https://feed2.com", category="news")

        all_sources = store.get_sources()
        assert len(all_sources) == 2

        tech_sources = store.get_sources(category="tech")
        assert len(tech_sources) == 1

    def test_remove_source(self, store: SourceStore):
        """Test removing a source."""
        store.add_source("rss", "https://example.com")

        removed = store.remove_source("https://example.com")
        assert removed is True

        sources = store.get_sources()
        assert len(sources) == 0

    def test_get_categories(self, store: SourceStore):
        """Test getting unique categories."""
        store.add_source("rss", "https://feed1.com", category="tech")
        store.add_source("rss", "https://feed2.com", category="news")
        store.add_source("rss", "https://feed3.com", category="tech")

        categories = store.get_categories()

        assert len(categories) == 2
        assert "tech" in categories
        assert "news" in categories
