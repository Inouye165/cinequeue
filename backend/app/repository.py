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
    def list_items(self, user_id: str) -> list[dict[str, Any]]:
        """Return all watchlist items ordered by added_at descending."""
        ...

    @abstractmethod
    def add_item(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
        is_owned: bool = False,
        owned_format: str | None = None,
        status: str = "queue",
        watch_free_streaming: bool = False,
        watch_on_sale_buy: bool = False,
        target_rental_price: float | None = None,
    ) -> dict[str, Any]:
        """Add an item to the watchlist.

        Raises:
            DuplicateItemError: If the item already exists.
        """
        ...

    @abstractmethod
    def update_item(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        is_owned: bool | None = None,
        owned_format: str | None = None,
        status: str | None = None,
        watch_free_streaming: bool | None = None,
        watch_on_sale_buy: bool | None = None,
        target_rental_price: float | None = None,
    ) -> dict[str, Any] | None:
        """Update an item's owned status, format, status, watch alert preferences, or target rental price.

        Returns:
            The updated item dictionary, or None if not found.
        """
        ...

    @abstractmethod
    def update_item_cache(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        details_cached: dict[str, Any],
    ) -> None:
        """Update the cached details and last_updated timestamp for a watchlist item."""
        ...


    @abstractmethod
    def remove_item(self, user_id: str, media_type: str, tmdb_id: int) -> bool:
        """Remove an item from the watchlist.

        Returns:
            True if the item was found and removed, False if it did not exist.
        """
        ...

    @abstractmethod
    def clear_all(self, user_id: str) -> None:
        """Remove all items. Used for testing."""
        ...

    @staticmethod
    def utc_now_iso() -> str:
        """Return the current UTC time as an ISO 8601 string."""
        return datetime.now(timezone.utc).isoformat()

    @abstractmethod
    def get_admin_user(self, username: str) -> dict[str, Any] | None:
        """Retrieve admin user by username."""
        ...

    @abstractmethod
    def create_admin_user(self, username: str, password_hash: str, salt: str) -> None:
        """Create a new admin user."""
        ...

    @abstractmethod
    def list_admin_users(self) -> list[str]:
        """List all admin usernames."""
        ...

    @abstractmethod
    def delete_admin_user(self, username: str) -> bool:
        """Delete/revoke an admin user."""
        ...

    @abstractmethod
    def create_admin_session(self, session_id: str, username: str, expires_at: str) -> None:
        """Store an admin session."""
        ...

    @abstractmethod
    def get_admin_session(self, session_id: str) -> dict[str, Any] | None:
        """Retrieve an admin session by session ID."""
        ...

    @abstractmethod
    def delete_admin_session(self, session_id: str) -> None:
        """Delete/invalidate an admin session."""
        ...

    @abstractmethod
    def get_user_approval(self, email: str) -> dict[str, Any] | None:
        """Retrieve approval status for a user email."""
        ...

    @abstractmethod
    def create_user_approval(self, email: str, status: str, requested_at: str) -> None:
        """Create a user approval request or pre-invite."""
        ...

    @abstractmethod
    def update_user_approval(self, email: str, status: str, decided_at: str, decided_by: str) -> None:
        """Approve or deny/revoke a user access request."""
        ...

    @abstractmethod
    def list_user_approvals(self) -> list[dict[str, Any]]:
        """List all user approvals and access requests."""
        ...

    @abstractmethod
    def log_login_attempt(
        self,
        email: str,
        status: str,
        reason: str,
        ip_address: str,
        user_agent: str,
        timestamp: str,
    ) -> None:
        """Audit log login attempts."""
        ...

    @abstractmethod
    def list_login_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        """List recent login attempts."""
        ...

    @abstractmethod
    def get_agent_settings(self, user_id: str) -> dict[str, Any]:
        """Get AI agent personality and feature settings for user."""
        ...

    @abstractmethod
    def save_agent_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Save or update AI agent settings for user."""
        ...

    @abstractmethod
    def update_agent_last_login(self, user_id: str, timestamp: str) -> None:
        """Update last login/briefing evaluation timestamp for user."""
        ...

    @abstractmethod
    def list_chat_messages(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List conversation history for AI agent."""
        ...

    @abstractmethod
    def add_chat_message(
        self,
        user_id: str,
        role: str,
        content: str,
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Store a chat message in history."""
        ...

    @abstractmethod
    def clear_chat_messages(self, user_id: str) -> None:
        """Clear user conversation history with AI agent."""
        ...

    @abstractmethod
    def add_query_memory(
        self,
        user_id: str,
        query_text: str,
        tmdb_id: int | None = None,
        media_type: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        """Record or update user interest/query memory in a movie or TV show."""
        ...

    @abstractmethod
    def list_query_memories(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """List remembered user query topics for persistent monitoring."""
        ...

    @abstractmethod
    def remove_query_memory(self, user_id: str, memory_id: Any) -> bool:
        """Remove a query memory record."""
        ...

    @abstractmethod
    def record_briefing_presentations(self, user_id: str, items: list[dict[str, Any]]) -> None:
        """Record or update presented briefing items for novelty tracking."""
        ...

    @abstractmethod
    def get_presented_briefing_keys(self, user_id: str) -> dict[str, dict[str, Any]]:
        """Retrieve mapping of item_key to presentation metadata for a user."""
        ...

    @abstractmethod
    def get_agent_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        """Get agent briefing session record."""
        ...

    @abstractmethod
    def save_agent_session(self, user_id: str, session_id: str, briefing_data: dict[str, Any]) -> dict[str, Any]:
        """Save or cache briefing output for a session ID."""
        ...

    @abstractmethod
    def get_user_briefing_state(self, user_id: str) -> dict[str, Any]:
        """Get previous_login_at and previous_briefing_presented_at reference timestamps."""
        ...

    @abstractmethod
    def update_user_briefing_state(
        self,
        user_id: str,
        login_at: str | None = None,
        briefing_presented_at: str | None = None,
    ) -> None:
        """Update login or presented briefing reference timestamps for user."""
        ...

