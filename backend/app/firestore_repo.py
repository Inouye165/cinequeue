"""Firestore-backed watchlist repository."""

import logging
from typing import Any

from google.cloud import firestore  # type: ignore[import-untyped]

from app.repository import DuplicateItemError, WatchlistRepository

logger = logging.getLogger(__name__)

COLLECTION = "watchlist"


def _doc_id(media_type: str, tmdb_id: int) -> str:
    """Build a deterministic document ID like 'movie_12345'."""
    return f"{media_type}_{tmdb_id}"


class FirestoreWatchlistRepository(WatchlistRepository):
    """Watchlist repository backed by Google Cloud Firestore.

    Uses Application Default Credentials via ``firestore.Client()``.
    Targets the default ``(default)`` database.
    """

    def __init__(self, project: str | None = None) -> None:
        self._db = firestore.Client(project=project)
        self._col = self._db.collection(COLLECTION)
        logger.info("Firestore watchlist repository initialised (project=%s)", project)

    # -- Repository interface --------------------------------------------------

    def list_items(self) -> list[dict[str, Any]]:
        docs = (
            self._col
            .order_by("added_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        return [doc.to_dict() for doc in docs]

    def add_item(
        self,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
    ) -> dict[str, Any]:
        doc_id = _doc_id(media_type, tmdb_id)
        doc_ref = self._col.document(doc_id)

        # Check for duplicate
        if doc_ref.get().exists:
            raise DuplicateItemError(f"Item {media_type}/{tmdb_id} already exists")

        added_at = self.utc_now_iso()
        data: dict[str, Any] = {
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "poster_path": poster_path,
            "release_date": release_date,
            "added_at": added_at,
        }
        doc_ref.set(data)
        return data

    def remove_item(self, media_type: str, tmdb_id: int) -> bool:
        doc_id = _doc_id(media_type, tmdb_id)
        doc_ref = self._col.document(doc_id)

        if not doc_ref.get().exists:
            return False

        doc_ref.delete()
        return True

    def clear_all(self) -> None:
        for doc in self._col.stream():
            doc.reference.delete()
