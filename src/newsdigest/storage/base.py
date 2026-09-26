"""Base storage interface for NewsDigest."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar


T = TypeVar("T")


class BaseStorage(ABC, Generic[T]):
    """Abstract base class for storage implementations.

    Provides a consistent interface for different storage backends
    (memory, file, database, etc.).
    """

    @abstractmethod
    async def get(self, key: str) -> T | None:
        """Retrieve an item by key.

        Args:
            key: Unique identifier for the item.

        Returns:
            The stored item or None if not found.
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Store an item.

        Args:
            key: Unique identifier for the item.
            value: The item to store.
            ttl: Time-to-live in seconds (optional).
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete an item by key.

        Args:
            key: Unique identifier for the item.

        Returns:
            True if item was deleted, False if not found.
        """
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if an item exists.

        Args:
            key: Unique identifier for the item.

        Returns:
            True if item exists, False otherwise.
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all stored items."""
        pass

    @abstractmethod
    async def keys(self, pattern: str | None = None) -> list[str]:
        """Get all keys, optionally matching a pattern.

        Args:
            pattern: Optional glob pattern to filter keys.

        Returns:
            List of matching keys.
        """
        pass


class SyncStorage(ABC, Generic[T]):
    """Synchronous storage interface.

    For use cases where async is not needed or supported.
    """

    @abstractmethod
    def get(self, key: str) -> T | None:
        """Retrieve an item by key."""
        pass

    @abstractmethod
    def set(self, key: str, value: T, ttl: int | None = None) -> None:
        """Store an item."""
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete an item by key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if an item exists."""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored items."""
        pass

    @abstractmethod
    def keys(self, pattern: str | None = None) -> list[str]:
        """Get all keys, optionally matching a pattern."""
        pass
