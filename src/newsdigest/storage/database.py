"""SQLite database storage for NewsDigest.

Provides persistent storage using SQLite for:
- Extraction history and analytics
- Configured sources
- Cached results
- API keys
"""

import json
import sqlite3
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from newsdigest.storage.analytics import AggregateStats, ExtractionRecord


class Database:
    """SQLite database for persistent storage.

    Thread-safe database operations with connection pooling.

    Example:
        >>> db = Database("~/.newsdigest/data.db")
        >>> db.initialize()
        >>> db.save_extraction(record)
        >>> records = db.get_extractions(limit=100)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        """Initialize database.

        Args:
            db_path: Path to SQLite database file.
                    If None, uses in-memory database.
        """
        self._db_path: Path | None
        if db_path:
            self._db_path = Path(db_path).expanduser()
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
            self._connection_string = str(self._db_path)
        else:
            self._db_path = None
            self._connection_string = ":memory:"

        # Every connection to ":memory:" opens a separate, empty database, so
        # an in-memory database keeps one shared connection for its lifetime.
        self._lock = threading.RLock()
        self._memory_conn: sqlite3.Connection | None = None
        if self._db_path is None:
            self._memory_conn = sqlite3.connect(
                self._connection_string, check_same_thread=False
            )
            self._memory_conn.row_factory = sqlite3.Row

        self._initialized = False

    @contextmanager
    def _get_connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection.

        Yields:
            SQLite connection with row factory.
        """
        if self._db_path is None:
            if self._memory_conn is None:
                raise sqlite3.ProgrammingError("Cannot operate on a closed database.")
            with self._lock:
                try:
                    yield self._memory_conn
                    self._memory_conn.commit()
                except Exception:
                    self._memory_conn.rollback()
                    raise
            return

        conn = sqlite3.connect(self._connection_string)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def close(self) -> None:
        """Close the shared in-memory connection, discarding its data.

        File-backed databases open a connection per operation, so there is
        nothing to close for them.
        """
        with self._lock:
            if self._memory_conn is not None:
                self._memory_conn.close()
                self._memory_conn = None

    def initialize(self) -> None:
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Extractions table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS extractions (
                    id TEXT PRIMARY KEY,
                    timestamp REAL NOT NULL,
                    source_url TEXT,
                    source_type TEXT DEFAULT 'text',
                    original_words INTEGER DEFAULT 0,
                    compressed_words INTEGER DEFAULT 0,
                    compression_ratio REAL DEFAULT 0.0,
                    claims_extracted INTEGER DEFAULT 0,
                    speculation_removed INTEGER DEFAULT 0,
                    emotional_removed INTEGER DEFAULT 0,
                    unnamed_sources INTEGER DEFAULT 0,
                    processing_time_ms REAL DEFAULT 0.0,
                    success INTEGER DEFAULT 1,
                    error TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Sources table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sources (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    type TEXT NOT NULL,
                    url TEXT NOT NULL UNIQUE,
                    name TEXT,
                    category TEXT,
                    enabled INTEGER DEFAULT 1,
                    last_fetched REAL,
                    fetch_count INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Cache table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    expires_at REAL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # API keys table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS api_keys (
                    key_hash TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    rate_limit INTEGER DEFAULT 100,
                    scopes TEXT DEFAULT '["read", "write"]',
                    enabled INTEGER DEFAULT 1,
                    last_used REAL,
                    request_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_extractions_timestamp
                ON extractions(timestamp)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_extractions_source_type
                ON extractions(source_type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_sources_type
                ON sources(type)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_cache_expires
                ON cache(expires_at)
            """)

        self._initialized = True

    def _ensure_initialized(self) -> None:
        """Ensure database is initialized."""
        if not self._initialized:
            self.initialize()

    # =========================================================================
    # Extraction Operations
    # =========================================================================

    def save_extraction(self, record: ExtractionRecord) -> None:
        """Save an extraction record.

        Args:
            record: Extraction record to save.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO extractions (
                    id, timestamp, source_url, source_type,
                    original_words, compressed_words, compression_ratio,
                    claims_extracted, speculation_removed, emotional_removed,
                    unnamed_sources, processing_time_ms, success, error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.id,
                    record.timestamp,
                    record.source_url,
                    record.source_type,
                    record.original_words,
                    record.compressed_words,
                    record.compression_ratio,
                    record.claims_extracted,
                    record.speculation_removed,
                    record.emotional_removed,
                    record.unnamed_sources,
                    record.processing_time_ms,
                    1 if record.success else 0,
                    record.error,
                ),
            )

    def get_extractions(
        self,
        since: float | None = None,
        until: float | None = None,
        source_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ExtractionRecord]:
        """Get extraction records.

        Args:
            since: Only records after this timestamp.
            until: Only records before this timestamp.
            source_type: Filter by source type.
            limit: Maximum records to return.
            offset: Number of records to skip.

        Returns:
            List of extraction records.
        """
        self._ensure_initialized()

        query = "SELECT * FROM extractions WHERE 1=1"
        params: list[Any] = []

        if since is not None:
            query += " AND timestamp >= ?"
            params.append(since)

        if until is not None:
            query += " AND timestamp <= ?"
            params.append(until)

        if source_type is not None:
            query += " AND source_type = ?"
            params.append(source_type)

        query += " ORDER BY timestamp DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [
            ExtractionRecord(
                id=row["id"],
                timestamp=row["timestamp"],
                source_url=row["source_url"],
                source_type=row["source_type"],
                original_words=row["original_words"],
                compressed_words=row["compressed_words"],
                compression_ratio=row["compression_ratio"],
                claims_extracted=row["claims_extracted"],
                speculation_removed=row["speculation_removed"],
                emotional_removed=row["emotional_removed"],
                unnamed_sources=row["unnamed_sources"],
                processing_time_ms=row["processing_time_ms"],
                success=bool(row["success"]),
                error=row["error"],
            )
            for row in rows
        ]

    def get_extraction_stats(
        self,
        since: float | None = None,
        until: float | None = None,
    ) -> AggregateStats:
        """Get aggregated extraction statistics.

        Args:
            since: Start of period.
            until: End of period.

        Returns:
            Aggregated statistics.
        """
        self._ensure_initialized()

        query = """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful,
                SUM(original_words) as total_original,
                SUM(compressed_words) as total_compressed,
                SUM(claims_extracted) as total_claims,
                SUM(speculation_removed) as total_speculation,
                SUM(emotional_removed) as total_emotional,
                AVG(processing_time_ms) as avg_processing
            FROM extractions
            WHERE 1=1
        """
        params: list[Any] = []

        if since is not None:
            query += " AND timestamp >= ?"
            params.append(since)

        if until is not None:
            query += " AND timestamp <= ?"
            params.append(until)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            row = cursor.fetchone()

        if not row or row["total"] == 0:
            return AggregateStats(
                period_start=since or 0,
                period_end=until or time.time(),
            )

        total_orig = row["total_original"] or 0
        total_comp = row["total_compressed"] or 0
        compression = 1 - (total_comp / total_orig) if total_orig > 0 else 0

        return AggregateStats(
            period_start=since or 0,
            period_end=until or time.time(),
            total_extractions=row["total"],
            successful_extractions=row["successful"] or 0,
            failed_extractions=(row["total"] or 0) - (row["successful"] or 0),
            total_original_words=total_orig,
            total_compressed_words=total_comp,
            avg_compression_ratio=compression,
            total_claims=row["total_claims"] or 0,
            total_speculation_removed=row["total_speculation"] or 0,
            total_emotional_removed=row["total_emotional"] or 0,
            avg_processing_time_ms=row["avg_processing"] or 0,
        )

    # =========================================================================
    # Source Operations
    # =========================================================================

    def add_source(
        self,
        source_type: str,
        url: str,
        name: str | None = None,
        category: str | None = None,
    ) -> int:
        """Add a news source.

        Args:
            source_type: Type of source (rss, url, newsapi).
            url: Source URL.
            name: Display name.
            category: Category for grouping.

        Returns:
            Source ID.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO sources (type, url, name, category)
                VALUES (?, ?, ?, ?)
                """,
                (source_type, url, name or url, category),
            )
            return cursor.lastrowid or 0

    def get_sources(
        self,
        source_type: str | None = None,
        category: str | None = None,
        enabled_only: bool = True,
    ) -> list[dict[str, Any]]:
        """Get configured sources.

        Args:
            source_type: Filter by type.
            category: Filter by category.
            enabled_only: Only return enabled sources.

        Returns:
            List of source dictionaries.
        """
        self._ensure_initialized()

        query = "SELECT * FROM sources WHERE 1=1"
        params: list[Any] = []

        if enabled_only:
            query += " AND enabled = 1"

        if source_type:
            query += " AND type = ?"
            params.append(source_type)

        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY name"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()

        return [dict(row) for row in rows]

    def update_source_stats(
        self,
        url: str,
        success: bool = True,
    ) -> None:
        """Update source fetch statistics.

        Args:
            url: Source URL.
            success: Whether fetch was successful.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            if success:
                cursor.execute(
                    """
                    UPDATE sources
                    SET last_fetched = ?, fetch_count = fetch_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE url = ?
                    """,
                    (time.time(), url),
                )
            else:
                cursor.execute(
                    """
                    UPDATE sources
                    SET error_count = error_count + 1,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE url = ?
                    """,
                    (url,),
                )

    def remove_source(self, url: str) -> bool:
        """Remove a source.

        Args:
            url: Source URL to remove.

        Returns:
            True if removed.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM sources WHERE url = ?", (url,))
            return cursor.rowcount > 0

    # =========================================================================
    # Cache Operations
    # =========================================================================

    def cache_get(self, key: str) -> Any | None:
        """Get a cached value.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found/expired.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT value, expires_at FROM cache
                WHERE key = ?
                """,
                (key,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        # Check expiry
        if row["expires_at"] and time.time() > row["expires_at"]:
            self.cache_delete(key)
            return None

        return json.loads(row["value"])

    def cache_set(
        self,
        key: str,
        value: Any,
        ttl: int | None = None,
    ) -> None:
        """Set a cached value.

        Args:
            key: Cache key.
            value: Value to cache (must be JSON-serializable).
            ttl: Time-to-live in seconds.
        """
        self._ensure_initialized()

        expires_at = time.time() + ttl if ttl else None

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO cache (key, value, expires_at)
                VALUES (?, ?, ?)
                """,
                (key, json.dumps(value), expires_at),
            )

    def cache_delete(self, key: str) -> bool:
        """Delete a cached value.

        Args:
            key: Cache key.

        Returns:
            True if deleted.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM cache WHERE key = ?", (key,))
            return cursor.rowcount > 0

    def cache_clear_expired(self) -> int:
        """Clear expired cache entries.

        Returns:
            Number of entries cleared.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                DELETE FROM cache
                WHERE expires_at IS NOT NULL AND expires_at < ?
                """,
                (time.time(),),
            )
            return cursor.rowcount

    # =========================================================================
    # API Key Operations
    # =========================================================================

    def save_api_key(
        self,
        key_hash: str,
        name: str,
        rate_limit: int = 100,
        scopes: list[str] | None = None,
    ) -> None:
        """Save an API key.

        Args:
            key_hash: SHA-256 hash of the key.
            name: Key name.
            rate_limit: Requests per minute.
            scopes: Permission scopes.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO api_keys
                (key_hash, name, rate_limit, scopes)
                VALUES (?, ?, ?, ?)
                """,
                (
                    key_hash,
                    name,
                    rate_limit,
                    json.dumps(scopes or ["read", "write"]),
                ),
            )

    def get_api_key(self, key_hash: str) -> dict[str, Any] | None:
        """Get API key by hash.

        Args:
            key_hash: SHA-256 hash of the key.

        Returns:
            Key data or None if not found.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM api_keys WHERE key_hash = ? AND enabled = 1",
                (key_hash,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        result = dict(row)
        result["scopes"] = json.loads(result["scopes"])
        return result

    def record_api_key_usage(self, key_hash: str) -> None:
        """Record API key usage.

        Args:
            key_hash: SHA-256 hash of the key.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                UPDATE api_keys
                SET last_used = ?, request_count = request_count + 1
                WHERE key_hash = ?
                """,
                (time.time(), key_hash),
            )

    def disable_api_key(self, key_hash: str) -> bool:
        """Disable an API key.

        Args:
            key_hash: SHA-256 hash of the key.

        Returns:
            True if disabled.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE api_keys SET enabled = 0 WHERE key_hash = ?",
                (key_hash,),
            )
            return cursor.rowcount > 0

    # =========================================================================
    # Maintenance
    # =========================================================================

    def vacuum(self) -> None:
        """Optimize database by running VACUUM."""
        with self._get_connection() as conn:
            conn.execute("VACUUM")

    # Allowed table names for validation (prevents SQL injection)
    ALLOWED_TABLES = frozenset(["extractions", "sources", "cache", "api_keys"])

    def get_stats(self) -> dict[str, int]:
        """Get database statistics.

        Returns:
            Dictionary with table row counts.
        """
        self._ensure_initialized()

        with self._get_connection() as conn:
            cursor = conn.cursor()

            stats = {}
            for table in self.ALLOWED_TABLES:
                # Table name validated against ALLOWED_TABLES whitelist
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]

        return stats
