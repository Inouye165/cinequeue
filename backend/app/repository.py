"""Abstract watchlist repository interface.

Defines the contract that all watchlist storage backends must implement.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any


class DuplicateItemError(Exception):
    """Raised when attempting to add an item that already exists."""
    pass


class WatchlistRepository(ABC):
    """Abstract base class for watchlist storage backends."""

    @abstractmethod
    def list_items(self) -> list[dict[str, Any]]:
        """Return all watchlist items ordered by added_at descending."""
        ...

    @abstractmethod
    def add_item(
        self,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
    ) -> dict[str, Any]:
        """Add an item to the watchlist.

        Raises:
            DuplicateItemError: If the item already exists.
        """
        ...

    @abstractmethod
    def remove_item(self, media_type: str, tmdb_id: int) -> bool:
        """Remove an item from the watchlist.

        Returns:
            True if the item was found and removed, False if it did not exist.
        """
        ...

    @abstractmethod
    def clear_all(self) -> None:
        """Remove all items. Used for testing."""
        ...

    @staticmethod
    def utc_now_iso() -> str:
        """Return the current UTC time as an ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()
