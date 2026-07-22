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
            d.setdefault("target_rental_price", None)
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
        target_rental_price: float | None = None,
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
            "target_rental_price": target_rental_price,
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
        target_rental_price: float | None = None,
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
        if target_rental_price is not None:
            data["target_rental_price"] = target_rental_price

        doc_ref.update(data)
        updated = snapshot.to_dict()
        updated.update(data)
        if "is_owned" in updated:
            updated["is_owned"] = bool(updated["is_owned"])
        updated.setdefault("status", "queue")
        updated.setdefault("watch_free_streaming", False)
        updated.setdefault("watch_on_sale_buy", False)
        updated.setdefault("target_rental_price", None)
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

    def get_agent_settings(self, user_id: str) -> dict[str, Any]:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        doc = doc_ref.get()
        if not doc.exists:
            return {
                "user_id": user_id,
                "personality_preset": "cinephile",
                "custom_prompt": "",
                "location": "",
                "notify_on_login": True,
                "auto_add_mentioned": True,
                "track_price_drops": True,
                "updated_at": self.utc_now_iso(),
            }
        d = doc.to_dict() or {}
        d.setdefault("user_id", user_id)
        d.setdefault("personality_preset", "cinephile")
        d.setdefault("custom_prompt", "")
        d.setdefault("location", "")
        d.setdefault("notify_on_login", True)
        d.setdefault("auto_add_mentioned", True)
        d.setdefault("track_price_drops", True)
        return d

    def save_agent_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        now = self.utc_now_iso()
        data = {
            "user_id": user_id,
            "personality_preset": settings.get("personality_preset", "cinephile"),
            "custom_prompt": settings.get("custom_prompt", ""),
            "location": settings.get("location", "").strip(),
            "notify_on_login": bool(settings.get("notify_on_login", True)),
            "auto_add_mentioned": bool(settings.get("auto_add_mentioned", True)),
            "track_price_drops": bool(settings.get("track_price_drops", True)),
            "updated_at": now,
        }
        doc_ref.set(data, merge=True)
        return data

    def update_agent_last_login(self, user_id: str, timestamp: str) -> None:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        doc_ref.set({"updated_at": timestamp}, merge=True)

    def list_chat_messages(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        col = self._db.collection("users").document(user_id).collection("agent_conversations")
        docs = (
            col
            .order_by("created_at", direction=firestore.Query.ASCENDING)
            .limit(limit)
            .stream()
        )
        res = []
        for doc in docs:
            d = doc.to_dict()
            if d is not None:
                d["id"] = doc.id
                d.setdefault("actions", [])
                res.append(d)
        return res

    def add_chat_message(
        self,
        user_id: str,
        role: str,
        content: str,
        actions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        col = self._db.collection("users").document(user_id).collection("agent_conversations")
        now = self.utc_now_iso()
        data = {
            "user_id": user_id,
            "role": role,
            "content": content,
            "actions": actions or [],
            "created_at": now,
        }
        _, doc_ref = col.add(data)
        data["id"] = doc_ref.id
        return data

    def clear_chat_messages(self, user_id: str) -> None:
        col = self._db.collection("users").document(user_id).collection("agent_conversations")
        docs = col.stream()
        for doc in docs:
            doc.reference.delete()

    def add_query_memory(
        self,
        user_id: str,
        query_text: str,
        tmdb_id: int | None = None,
        media_type: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        item_title = title or query_text
        doc_id = item_title.lower().replace(" ", "_")
        col = self._db.collection("users").document(user_id).collection("agent_query_memories")
        now = self.utc_now_iso()
        data = {
            "user_id": user_id,
            "query_text": query_text,
            "title": item_title,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "asked_at": now,
        }
        col.document(doc_id).set(data, merge=True)
        data["id"] = doc_id
        return data

    def list_query_memories(self, user_id: str, limit: int = 50) -> list[dict[str, Any]]:
        col = self._db.collection("users").document(user_id).collection("agent_query_memories")
        docs = col.order_by("asked_at", direction=firestore.Query.DESCENDING).limit(limit).stream()
        res = []
        for doc in docs:
            d = doc.to_dict()
            if d:
                d["id"] = doc.id
                res.append(d)
        return res

    def remove_query_memory(self, user_id: str, memory_id: Any) -> bool:
        col = self._db.collection("users").document(user_id).collection("agent_query_memories")
        doc_ref = col.document(str(memory_id))
        doc = doc_ref.get()
        if doc.exists:
            doc_ref.delete()
            return True
        return False

    def record_briefing_presentations(self, user_id: str, items: list[dict[str, Any]]) -> None:
        col = self._db.collection("users").document(user_id).collection("briefing_presentations")
        now = self.utc_now_iso()
        for item in items:
            item_key = item.get("item_key") or item.get("story_cluster_id") or f"item_{item.get('title_id', 'gen')}"
            doc_ref = col.document(item_key)
            existing = doc_ref.get()
            data = {
                "user_id": user_id,
                "item_key": item_key,
                "story_cluster_id": str(item.get("story_cluster_id") or item_key),
                "news_item_id": str(item.get("news_item_id") or item_key),
                "related_title_id": str(item.get("title_id") or ""),
                "news_category": str(item.get("category") or item.get("type", "unknown")),
                "item_type": item.get("type") or item.get("category", "unknown"),
                "title_id": str(item.get("title_id") or ""),
                "source_id": str(item.get("source") or item.get("source_id") or ""),
                "content_fingerprint": str(item.get("content_fingerprint") or ""),
                "last_updated_at": now,
                "last_material_change_at": str(item.get("last_material_change_at") or now),
                "last_presented_at": now,
                "importance": int(item.get("importance_score") or item.get("urgency", 3)),
                "importance_score": int(item.get("importance_score") or item.get("urgency", 3)),
                "acknowledged": False,
                "dismissed": False,
            }
            if existing.exists:
                prev = existing.to_dict() or {}
                data["first_discovered_at"] = prev.get("first_discovered_at", now)
                data["first_presented_at"] = prev.get("first_presented_at", now)
                data["presentation_count"] = prev.get("presentation_count", 1) + 1
            else:
                data["first_discovered_at"] = now
                data["first_presented_at"] = now
                data["presentation_count"] = 1
            doc_ref.set(data, merge=True)

    def get_presented_briefing_keys(self, user_id: str) -> dict[str, dict[str, Any]]:
        col = self._db.collection("users").document(user_id).collection("briefing_presentations")
        docs = col.stream()
        res = {}
        for d in docs:
            dict_val = d.to_dict()
            if dict_val:
                res[d.id] = dict_val
        return res

    def get_user_briefing_state(self, user_id: str) -> dict[str, Any]:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        doc = doc_ref.get()
        if not doc.exists:
            return {"previous_login_at": None, "previous_briefing_presented_at": None}
        d = doc.to_dict() or {}
        return {
            "previous_login_at": d.get("previous_login_at"),
            "previous_briefing_presented_at": d.get("previous_briefing_presented_at"),
        }

    def update_user_briefing_state(
        self,
        user_id: str,
        login_at: str | None = None,
        briefing_presented_at: str | None = None,
    ) -> None:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        now = self.utc_now_iso()
        data: dict[str, Any] = {"updated_at": now}
        if login_at is not None:
            data["previous_login_at"] = login_at
        if briefing_presented_at is not None:
            data["previous_briefing_presented_at"] = briefing_presented_at
        doc_ref.set(data, merge=True)

    def get_agent_session(self, user_id: str, session_id: str) -> dict[str, Any] | None:
        doc = self._db.collection("users").document(user_id).collection("agent_sessions").document(session_id).get()
        if doc.exists:
            d = doc.to_dict()
            if d and "briefing_data" in d:
                return d["briefing_data"]
        return None

    def save_agent_session(self, user_id: str, session_id: str, briefing_data: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        doc_ref = self._db.collection("users").document(user_id).collection("agent_sessions").document(session_id)
        doc_ref.set({
            "user_id": user_id,
            "session_id": session_id,
            "briefing_data": briefing_data,
            "created_at": now,
        }, merge=True)
        return briefing_data

