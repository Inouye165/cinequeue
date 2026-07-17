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
        logger.info("Firestore watchlist repository initialised (project=%s)", project)

    def _user_watchlist_col(self, user_id: str):
        return self._db.collection("users").document(user_id).collection(COLLECTION)

    # -- Repository interface --------------------------------------------------

    def list_items(self, user_id: str) -> list[dict[str, Any]]:
        col = self._user_watchlist_col(user_id)
        docs = (
            col
            .order_by("added_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        res = []
        for doc in docs:
            d = doc.to_dict()
            d.setdefault("is_owned", False)
            d.setdefault("owned_format", None)
            d.setdefault("status", "queue")
            d.setdefault("watch_free_streaming", False)
            d.setdefault("watch_on_sale_buy", False)
            res.append(d)
        return res

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
    ) -> dict[str, Any]:
        doc_id = _doc_id(media_type, tmdb_id)
        col = self._user_watchlist_col(user_id)
        doc_ref = col.document(doc_id)

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
            "is_owned": is_owned,
            "owned_format": owned_format,
            "status": status,
            "watch_free_streaming": watch_free_streaming,
            "watch_on_sale_buy": watch_on_sale_buy,
        }
        doc_ref.set(data)
        return data

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
    ) -> dict[str, Any] | None:
        doc_id = _doc_id(media_type, tmdb_id)
        col = self._user_watchlist_col(user_id)
        doc_ref = col.document(doc_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        
        data: dict[str, Any] = {}
        if is_owned is not None:
            data["is_owned"] = is_owned
            if not is_owned:
                data["owned_format"] = None
            elif owned_format is not None:
                data["owned_format"] = owned_format
        if status is not None:
            data["status"] = status
        if watch_free_streaming is not None:
            data["watch_free_streaming"] = watch_free_streaming
        if watch_on_sale_buy is not None:
            data["watch_on_sale_buy"] = watch_on_sale_buy

        doc_ref.update(data)
        updated = snapshot.to_dict()
        updated.update(data)
        if "is_owned" in updated:
            updated["is_owned"] = bool(updated["is_owned"])
        updated.setdefault("status", "queue")
        updated.setdefault("watch_free_streaming", False)
        updated.setdefault("watch_on_sale_buy", False)
        return updated

    def update_item_cache(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        details_cached: dict[str, Any],
    ) -> None:
        doc_id = _doc_id(media_type, tmdb_id)
        col = self._user_watchlist_col(user_id)
        doc_ref = col.document(doc_id)
        if doc_ref.get().exists:
            last_updated = self.utc_now_iso()
            doc_ref.update({
                "details_cached": details_cached,
                "last_updated": last_updated,
            })


    def remove_item(self, user_id: str, media_type: str, tmdb_id: int) -> bool:
        doc_id = _doc_id(media_type, tmdb_id)
        col = self._user_watchlist_col(user_id)
        doc_ref = col.document(doc_id)

        if not doc_ref.get().exists:
            return False

        doc_ref.delete()
        return True

    def clear_all(self, user_id: str) -> None:
        col = self._user_watchlist_col(user_id)
        for doc in col.stream():
            doc.reference.delete()

    # -- Admin & Auth Methods -------------------------------------------------

    def get_admin_user(self, username: str) -> dict[str, Any] | None:
        username_normalized = username.strip().lower()
        doc_ref = self._db.collection("admin_users").document(username_normalized)
        snapshot = doc_ref.get()
        if snapshot.exists:
            res = snapshot.to_dict()
            if res is not None:
                res["username"] = username_normalized
                return res
        return None

    def create_admin_user(self, username: str, password_hash: str, salt: str) -> None:
        username_normalized = username.strip().lower()
        doc_ref = self._db.collection("admin_users").document(username_normalized)
        doc_ref.set({
            "password_hash": password_hash,
            "salt": salt
        })

    def list_admin_users(self) -> list[str]:
        docs = self._db.collection("admin_users").stream()
        return [doc.id for doc in docs]

    def delete_admin_user(self, username: str) -> bool:
        username_normalized = username.strip().lower()
        doc_ref = self._db.collection("admin_users").document(username_normalized)
        if not doc_ref.get().exists:
            return False
        doc_ref.delete()
        # Clean up any active sessions for this admin user
        sessions = self._db.collection("admin_sessions").where("username", "==", username_normalized).stream()
        for sess in sessions:
            sess.reference.delete()
        return True

    def create_admin_session(self, session_id: str, username: str, expires_at: str) -> None:
        created_at = self.utc_now_iso()
        doc_ref = self._db.collection("admin_sessions").document(session_id)
        doc_ref.set({
            "username": username,
            "created_at": created_at,
            "expires_at": expires_at
        })

    def get_admin_session(self, session_id: str) -> dict[str, Any] | None:
        doc_ref = self._db.collection("admin_sessions").document(session_id)
        snapshot = doc_ref.get()
        if snapshot.exists:
            res = snapshot.to_dict()
            if res is not None:
                res["session_id"] = session_id
                return res
        return None

    def delete_admin_session(self, session_id: str) -> None:
        doc_ref = self._db.collection("admin_sessions").document(session_id)
        doc_ref.delete()

    def get_user_approval(self, email: str) -> dict[str, Any] | None:
        doc_ref = self._db.collection("user_approvals").document(email)
        snapshot = doc_ref.get()
        if snapshot.exists:
            res = snapshot.to_dict()
            if res is not None:
                res["email"] = email
                return res
        return None

    def create_user_approval(self, email: str, status: str, requested_at: str) -> None:
        doc_ref = self._db.collection("user_approvals").document(email)
        if not doc_ref.get().exists:
            doc_ref.set({
                "status": status,
                "requested_at": requested_at,
                "decided_at": None,
                "decided_by": None
            })

    def update_user_approval(self, email: str, status: str, decided_at: str, decided_by: str) -> None:
        doc_ref = self._db.collection("user_approvals").document(email)
        doc_ref.update({
            "status": status,
            "decided_at": decided_at,
            "decided_by": decided_by
        })

    def list_user_approvals(self) -> list[dict[str, Any]]:
        docs = (
            self._db.collection("user_approvals")
            .order_by("requested_at", direction=firestore.Query.DESCENDING)
            .stream()
        )
        res = []
        for doc in docs:
            d = doc.to_dict()
            if d is not None:
                d["email"] = doc.id
                res.append(d)
        return res

    def log_login_attempt(
        self,
        email: str,
        status: str,
        reason: str,
        ip_address: str,
        user_agent: str,
        timestamp: str,
    ) -> None:
        col = self._db.collection("login_logs")
        col.add({
            "email": email,
            "timestamp": timestamp,
            "status": status,
            "reason": reason,
            "ip_address": ip_address,
            "user_agent": user_agent
        })

    def list_login_logs(self, limit: int = 100) -> list[dict[str, Any]]:
        docs = (
            self._db.collection("login_logs")
            .order_by("timestamp", direction=firestore.Query.DESCENDING)
            .limit(limit)
            .stream()
        )
        res = []
        for doc in docs:
            d = doc.to_dict()
            if d is not None:
                d["id"] = doc.id
                res.append(d)
        return res

