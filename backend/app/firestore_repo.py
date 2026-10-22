"""Firestore-backed watchlist repository."""

import logging
import hashlib
import time
from datetime import datetime, timezone
from typing import Any, Optional

from google.cloud import firestore  # type: ignore[import-untyped]

from app.repository import DuplicateItemError, WatchlistRepository
from app.sync_protocol import (
    check_receipt, operation_fingerprint, operation_result, sync_record, sync_records,
    validate_operation, write_values,
)

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

    def sync_snapshot(self, user_id: str) -> list[dict[str, Any]]:
        user = self._db.collection("users").document(user_id)

        @firestore.transactional
        def read(transaction):
            # Passing the same transaction pins both queries to a single snapshot.
            watch = [doc.to_dict() for doc in user.collection("watchlist").stream(transaction=transaction)]
            rated = [doc.to_dict() for doc in user.collection("rated_movies").stream(transaction=transaction)]
            return sync_records(watch, rated)

        return read(self._db.transaction())

    def apply_sync_operation(self, user_id: str, operation: dict[str, Any]) -> dict[str, Any]:
        validate_operation(operation, user_id)
        fingerprint = operation_fingerprint(operation)
        p = operation["payload"]
        media, tmdb = p.get("mediaType", "movie"), p["tmdbId"]
        user = self._db.collection("users").document(user_id)
        watch_ref = user.collection("watchlist").document(_doc_id(media, tmdb))
        rated_ref = user.collection("rated_movies").document(_doc_id(media, tmdb))
        receipt_ref = user.collection("sync_receipts").document(
            hashlib.sha256(operation["operationId"].encode()).hexdigest()
        )

        @firestore.transactional
        def apply(transaction):
            receipt = receipt_ref.get(transaction=transaction)
            if receipt.exists:
                return check_receipt(receipt.to_dict(), fingerprint)
            # Firestore requires all reads before any writes.
            watch = watch_ref.get(transaction=transaction).to_dict()
            rated = rated_ref.get(transaction=transaction).to_dict()
            now = self.utc_now_iso()
            result = operation_result(operation, sync_record(media, tmdb, watch, rated, now))
            if not result:
                if operation["operationType"] == "delete":
                    transaction.delete(watch_ref)
                    transaction.delete(rated_ref)
                    revision = "absent"
                else:
                    values = write_values(p, watch, now)
                    transaction.set(watch_ref, values, merge=True)
                    new_rated = None
                    if values["user_rating"]:
                        new_rated = {
                            "user_id": user_id, "media_type": media, "tmdb_id": tmdb,
                            "title": values["title"], "poster_path": values["poster_path"],
                            "release_date": values["release_date"], "rating": values["user_rating"],
                            "rated_at": (rated or {}).get("rated_at") or now, "updated_at": now,
                        }
                        transaction.set(rated_ref, new_rated)
                    else:
                        transaction.delete(rated_ref)
                    revision = sync_record(media, tmdb, values, new_rated)["revision"]
                result = {"applied": {"operationId": operation["operationId"], "revision": revision}}
            transaction.set(receipt_ref, {
                "fingerprint": fingerprint, "result": result, "created_at": now,
            })
            return result

        return apply(self._db.transaction())

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
            d.setdefault("user_rating", 0)
            res.append(d)
        return res

    def get_item(self, user_id: str, media_type: str, tmdb_id: int) -> dict[str, Any] | None:
        doc_id = _doc_id(media_type, tmdb_id)
        doc_ref = self._user_watchlist_col(user_id).document(doc_id)
        snapshot = doc_ref.get()
        if not snapshot.exists:
            return None
        d = snapshot.to_dict() or {}
        d.setdefault("is_owned", False)
        d.setdefault("owned_format", None)
        d.setdefault("status", "queue")
        d.setdefault("watch_free_streaming", False)
        d.setdefault("watch_on_sale_buy", False)
        d.setdefault("target_rental_price", None)
        d.setdefault("user_rating", 0)
        return d

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
        user_rating: int = 0,
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
            "user_rating": user_rating,
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
        user_rating: int | None = None,
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
        if user_rating is not None:
            data["user_rating"] = user_rating

        doc_ref.update(data)
        updated = snapshot.to_dict()
        updated.update(data)
        if "is_owned" in updated:
            updated["is_owned"] = bool(updated["is_owned"])
        updated.setdefault("status", "queue")
        updated.setdefault("watch_free_streaming", False)
        updated.setdefault("watch_on_sale_buy", False)
        updated.setdefault("target_rental_price", None)
        updated.setdefault("user_rating", 0)
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
        username_normalized = (username or "").strip().lower()
        if not username_normalized:
            return None
        doc_ref = self._db.collection("admin_users").document(username_normalized)
        snapshot = doc_ref.get()
        if snapshot.exists:
            res = snapshot.to_dict()
            if res is not None:
                res["username"] = username_normalized
                return res
        return None

    def create_admin_user(self, username: str, password_hash: str, salt: str) -> None:
        username_normalized = (username or "").strip().lower()
        if not username_normalized or not password_hash:
            raise ValueError("Admin username and password_hash must not be empty")
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

    def list_login_logs(
        self,
        limit: int = 100,
        email: Optional[str] = None,
        status: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        ref: Any = self._db.collection("login_logs")
        if email:
            ref = ref.where("email", "==", email.strip().lower())
        if status:
            ref = ref.where("status", "==", status.strip().lower())
        if reason:
            ref = ref.where("reason", "==", reason.strip().lower())
        docs = (
            ref.order_by("timestamp", direction=firestore.Query.DESCENDING)
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

    def should_deduplicate_session_restoration(
        self,
        email: str,
        user_agent: str,
        ip_address: str,
        window_seconds: int = 1800,
    ) -> bool:
        try:
            key_raw = f"{email.strip().lower()}:{user_agent.strip()}:{ip_address.strip()}"
            cache_key = hashlib.sha256(key_raw.encode("utf-8")).hexdigest()
            now = time.time()

            if not hasattr(self, "_restoration_cache"):
                self._restoration_cache = {}

            # Periodic cleanup of expired items if cache grows large
            if len(self._restoration_cache) > 500:
                self._restoration_cache = {
                    k: t for k, t in self._restoration_cache.items()
                    if (now - t) < window_seconds
                }

            last_time = self._restoration_cache.get(cache_key)
            if last_time is not None and (now - last_time) < window_seconds:
                return True

            self._restoration_cache[cache_key] = now
            return False
        except Exception as e:
            logger.error("Error evaluating session restoration deduplication: %s", e)
            return False

    def get_agent_settings(self, user_id: str) -> dict[str, Any]:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        doc = doc_ref.get()
        if not doc.exists:
            return {
                "user_id": user_id,
                "personality_preset": "cinephile",
                "custom_prompt": "",
                "location": "",
                "timezone": "America/Los_Angeles",
                "user_timezone": "America/Los_Angeles",
                "notify_on_login": True,
                "auto_add_mentioned": True,
                "track_price_drops": True,
                "auto_speak_briefing": False,
                "updated_at": self.utc_now_iso(),
            }
        d = doc.to_dict() or {}
        d.setdefault("user_id", user_id)
        d.setdefault("personality_preset", "cinephile")
        d.setdefault("custom_prompt", "")
        d.setdefault("location", "")
        tz = d.get("timezone") or d.get("user_timezone") or "America/Los_Angeles"
        d["timezone"] = tz
        d["user_timezone"] = tz
        d.setdefault("notify_on_login", True)
        d.setdefault("auto_add_mentioned", True)
        d.setdefault("track_price_drops", True)
        d.setdefault("auto_speak_briefing", False)
        return d

    def save_agent_settings(self, user_id: str, settings: dict[str, Any]) -> dict[str, Any]:
        doc_ref = self._db.collection("users").document(user_id).collection("agent").document("settings")
        now = self.utc_now_iso()
        tz = (settings.get("timezone") or settings.get("user_timezone") or "America/Los_Angeles").strip()
        data = {
            "user_id": user_id,
            "personality_preset": settings.get("personality_preset", "cinephile"),
            "custom_prompt": settings.get("custom_prompt", ""),
            "location": settings.get("location", "").strip(),
            "timezone": tz,
            "user_timezone": tz,
            "notify_on_login": bool(settings.get("notify_on_login", True)),
            "auto_add_mentioned": bool(settings.get("auto_add_mentioned", True)),
            "track_price_drops": bool(settings.get("track_price_drops", True)),
            "auto_speak_briefing": bool(settings.get("auto_speak_briefing", False)),
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

    def get_daily_greeting(self, user_id: str, date_str: str) -> dict[str, Any] | None:
        doc = self._db.collection("users").document(user_id).collection("daily_greetings").document(date_str).get()
        if doc.exists:
            d = doc.to_dict()
            if d:
                if "briefing_data" in d:
                    b_data = d["briefing_data"]
                    if isinstance(b_data, dict):
                        return b_data
                return d
        return None

    def claim_daily_greeting_generation(
        self, user_id: str, date_str: str, lease_seconds: int = 30, force_refresh: bool = False
    ) -> tuple[bool, dict[str, Any] | None]:
        from datetime import datetime, timezone, timedelta
        doc_ref = self._db.collection("users").document(user_id).collection("daily_greetings").document(date_str)

        try:
            @firestore.transactional
            def _in_transaction(transaction, ref):
                snapshot = ref.get(transaction=transaction)
                now_dt = datetime.now(timezone.utc)
                now_iso = now_dt.isoformat()
                lease_exp = (now_dt + timedelta(seconds=lease_seconds)).isoformat()

                if snapshot.exists and not force_refresh:
                    d = snapshot.to_dict() or {}
                    b_data = d.get("briefing_data", d)
                    status = b_data.get("status", d.get("status", "completed"))
                    exp_str = b_data.get("lease_expires_at", d.get("lease_expires_at"))

                    if status == "completed":
                        return False, b_data

                    if status == "generating" and exp_str:
                        try:
                            exp_dt = datetime.fromisoformat(exp_str)
                            if exp_dt > now_dt:
                                return False, b_data
                        except Exception:
                            pass

                claiming_record = {
                    "user_id": user_id,
                    "date_str": date_str,
                    "status": "generating",
                    "lease_expires_at": lease_exp,
                    "created_at": now_iso,
                }
                transaction.set(ref, {"user_id": user_id, "date_str": date_str, "briefing_data": claiming_record, "created_at": now_iso}, merge=True)
                return True, None

            transaction = self._db.transaction()
            return _in_transaction(transaction, doc_ref)
        except Exception as e:
            logger.warning(f"Firestore claim_daily_greeting_generation error: {e}")
            return True, None

    def save_daily_greeting(self, user_id: str, date_str: str, briefing_data: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        briefing_data.setdefault("status", "completed")
        doc_ref = self._db.collection("users").document(user_id).collection("daily_greetings").document(date_str)
        doc_ref.set({
            "user_id": user_id,
            "date_str": date_str,
            "briefing_data": briefing_data,
            "created_at": now,
        }, merge=True)
        return briefing_data

    def list_rated_movies(self, user_id: str) -> list[dict[str, Any]]:
        try:
            col = self._db.collection("users").document(user_id).collection("rated_movies")
            try:
                docs = list(col.order_by("updated_at", direction=firestore.Query.DESCENDING).stream())
            except Exception as order_err:
                logger.warning("Firestore order_by updated_at query failed (%s), falling back to unordered stream", order_err)
                docs = list(col.stream())
                docs.sort(
                    key=lambda d: (d.to_dict() or {}).get("updated_at", "") or (d.to_dict() or {}).get("rated_at", ""),
                    reverse=True,
                )

            res = []
            now = datetime.now(timezone.utc)
            from app.models import poster_url
            for doc in docs:
                d = doc.to_dict()
                if d:
                    d["id"] = doc.id
                    p_path = d.get("poster_path")
                    d["poster_url"] = poster_url(p_path) if p_path else None
                    rated_at_str = d.get("updated_at") or d.get("rated_at")
                    rated_ago = "recently"
                    if rated_at_str:
                        try:
                            dt = datetime.fromisoformat(rated_at_str)
                            if dt.tzinfo is None:
                                dt = dt.replace(tzinfo=timezone.utc)
                            seconds = int((now - dt).total_seconds())
                            if seconds < 60:
                                rated_ago = "just now"
                            elif seconds < 3600:
                                mins = seconds // 60
                                rated_ago = f"{mins} min{'s' if mins > 1 else ''} ago"
                            elif seconds < 86400:
                                hrs = seconds // 3600
                                rated_ago = f"{hrs} hour{'s' if hrs > 1 else ''} ago"
                            elif seconds < 2592000:
                                days = seconds // 86400
                                rated_ago = f"{days} day{'s' if days > 1 else ''} ago"
                            elif seconds < 31536000:
                                months = seconds // 2592000
                                rated_ago = f"{months} month{'s' if months > 1 else ''} ago"
                            else:
                                yrs = seconds // 31536000
                                rated_ago = f"{yrs} year{'s' if yrs > 1 else ''} ago"
                        except Exception:
                            rated_ago = "recently"
                    d["rated_ago"] = rated_ago
                    res.append(d)
            return res
        except Exception as e:
            logger.error("Error listing rated movies in Firestore: %s", e, exc_info=True)
            return []

    def rate_movie(
        self,
        user_id: str,
        media_type: str,
        tmdb_id: int,
        title: str,
        poster_path: str | None,
        release_date: str | None,
        rating: int,
    ) -> dict[str, Any]:
        doc_id = f"{media_type}_{tmdb_id}"
        user_ref = self._db.collection("users").document(user_id)
        doc_ref = user_ref.collection("rated_movies").document(doc_id)
        watch_ref = user_ref.collection("watchlist").document(doc_id)
        now = self.utc_now_iso()
        rating = max(1, min(5, int(rating)))
        existing = doc_ref.get()
        prev = existing.to_dict() if existing.exists else {}
        data = {
            "user_id": user_id,
            "media_type": media_type,
            "tmdb_id": tmdb_id,
            "title": title,
            "poster_path": poster_path if poster_path is not None else (prev or {}).get("poster_path"),
            "release_date": release_date if release_date is not None else (prev or {}).get("release_date"),
            "rating": rating,
            "updated_at": now,
        }
        if not existing.exists:
            data["rated_at"] = now
        doc_ref.set(data, merge=True)

        # Synchronize user_rating in watchlist if present
        watch_snap = watch_ref.get()
        if watch_snap.exists:
            watch_ref.update({"user_rating": rating})

        from app.models import poster_url
        data["id"] = doc_id
        data["rated_ago"] = "just now"
        if data.get("poster_path"):
            data["poster_url"] = poster_url(data["poster_path"])
        return data

    def delete_rated_movie(self, user_id: str, media_type: str, tmdb_id: int) -> bool:
        try:
            doc_id = f"{media_type}_{tmdb_id}"
            user_ref = self._db.collection("users").document(user_id)
            doc_ref = user_ref.collection("rated_movies").document(doc_id)
            watch_ref = user_ref.collection("watchlist").document(doc_id)
            doc = doc_ref.get()
            deleted_rated = False
            if doc.exists:
                doc_ref.delete()
                deleted_rated = True

            watch_snap = watch_ref.get()
            modified_watch = False
            if watch_snap.exists:
                w_data = watch_snap.to_dict() or {}
                if not bool(w_data.get("is_owned")) and (w_data.get("status") == "watched" or not w_data.get("status")):
                    watch_ref.delete()
                else:
                    watch_ref.update({"user_rating": 0})
                modified_watch = True

            return deleted_rated or modified_watch
        except Exception as e:
            logger.error("Error deleting rated movie in Firestore: %s", e, exc_info=True)
            return False

    def add_decision_log(self, log_dict: dict[str, Any]) -> dict[str, Any]:
        from app.decision_models import scrub_secrets
        clean_dict = scrub_secrets(log_dict)
        try:
            log_id = clean_dict.get("log_id") or f"log_{int(time.time()*1000)}"
            doc_ref = self._db.collection("agent_decision_logs").document(log_id)
            data = dict(clean_dict)
            data["log_id"] = log_id
            if "event_type" not in data:
                data["event_type"] = "startup_briefing_candidate_decision"
            if "gemini_called" not in data:
                data["gemini_called"] = False
            doc_ref.set(data, merge=True)
        except Exception as e:
            logger.warning(f"Failed to save Firestore decision log '{log_dict.get('log_id')}': {e}")
        return clean_dict

    def _format_decision_log_doc(self, data: dict[str, Any]) -> dict[str, Any]:
        t_ver = data.get("telemetry_version")
        if t_ver != 2 or data.get("event_type") == "startup_briefing_decision":
            data["is_legacy"] = True
            summary = data.get("selection_summary", "")
            if "Legacy Candidate Decision — Gemini Call Unverified" not in summary:
                data["selection_summary"] = f"Legacy Candidate Decision — Gemini Call Unverified: {summary}".strip(": ")
        else:
            data["is_legacy"] = False
        return data

    def list_decision_logs(
        self,
        limit: int = 50,
        offset: int = 0,
        user_id: str | None = None,
        candidate_type: str | None = None,
        required_only: bool | None = None,
        fallback_only: bool | None = None,
        model: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> dict[str, Any]:
        col = self._db.collection("agent_decision_logs")
        try:
            query: Any = col.order_by("timestamp", direction=firestore.Query.DESCENDING)
            if user_id:
                query = query.where("user_id", "==", user_id)
            if fallback_only:
                query = query.where("fallback_used", "==", True)
            docs = list(query.stream())
        except Exception as query_err:
            logger.warning("Firestore composite query on agent_decision_logs failed (%s), falling back to client-side filter", query_err)
            docs = list(col.order_by("timestamp", direction=firestore.Query.DESCENDING).limit(500).stream())

        filtered = []
        for d in docs:
            raw = d.to_dict() or {}
            if user_id and raw.get("user_id") != user_id:
                continue
            if fallback_only and not raw.get("fallback_used"):
                continue
            data = self._format_decision_log_doc(raw)
            if start_date and data.get("timestamp", "") < start_date:
                continue
            if end_date and data.get("timestamp", "") > end_date:
                continue
            if model and data.get("model_requested") != model and data.get("model_used") != model:
                continue
            if candidate_type:
                cands = (
                    (data.get("selected_candidates") or [])
                    + (data.get("optional_candidates") or [])
                    + (data.get("required_candidates") or [])
                )
                if not any(candidate_type in str(c) for c in cands):
                    continue
            filtered.append(data)

        total = len(filtered)
        paginated = filtered[offset : offset + limit]
        return {"total": total, "logs": paginated, "limit": limit, "offset": offset}

    def get_decision_log(self, log_id: str) -> dict[str, Any] | None:
        doc = self._db.collection("agent_decision_logs").document(log_id).get()
        if doc.exists:
            return self._format_decision_log_doc(doc.to_dict())
        return None

    def get_active_decision_config(self) -> dict[str, Any]:
        try:
            docs = list(
                self._db.collection("agent_decision_configs")
                .order_by("version", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            if docs:
                d = docs[0].to_dict()
                if d:
                    return d
        except Exception as e:
            logger.warning("Failed to fetch active decision config from Firestore: %s", e)
        from app.decision_models import DEFAULT_DECISION_CONFIG
        return DEFAULT_DECISION_CONFIG.to_dict()

    def save_decision_config(self, config_dict: dict[str, Any], updated_by: str, change_note: str) -> dict[str, Any]:
        col = self._db.collection("agent_decision_configs")
        try:
            docs = list(col.order_by("version", direction=firestore.Query.DESCENDING).limit(1).stream())
            max_ver = (docs[0].to_dict() or {}).get("version", 0) if docs else 0
        except Exception:
            max_ver = 0
        new_ver = int(max_ver or 0) + 1
        saved = dict(config_dict)
        saved["version"] = new_ver
        saved["updated_at"] = self.utc_now_iso()
        saved["updated_by"] = updated_by
        saved["change_note"] = change_note
        col.document(f"v_{new_ver}").set(saved)
        return saved

    def get_active_prompt_version(self) -> dict[str, Any]:
        try:
            docs = list(
                self._db.collection("agent_prompt_versions")
                .order_by("version", direction=firestore.Query.DESCENDING)
                .limit(1)
                .stream()
            )
            if docs:
                d = docs[0].to_dict()
                if d:
                    return d
        except Exception as e:
            logger.warning("Failed to fetch active prompt version from Firestore: %s", e)
        from app.decision_models import DEFAULT_PROMPT_VERSION
        return DEFAULT_PROMPT_VERSION.to_dict()

    def list_prompt_versions(self) -> list[dict[str, Any]]:
        results = []
        try:
            docs = (
                self._db.collection("agent_prompt_versions")
                .order_by("version", direction=firestore.Query.DESCENDING)
                .stream()
            )
            for doc in docs:
                d = doc.to_dict()
                if d:
                    results.append(d)
        except Exception as e:
            logger.warning("Failed to list prompt versions from Firestore: %s", e)
        if not results:
            from app.decision_models import DEFAULT_PROMPT_VERSION
            results = [DEFAULT_PROMPT_VERSION.to_dict()]
        return results

    def save_prompt_version(self, prompt_dict: dict[str, Any], updated_by: str, change_note: str) -> dict[str, Any]:
        col = self._db.collection("agent_prompt_versions")
        try:
            docs = list(col.order_by("version", direction=firestore.Query.DESCENDING).limit(1).stream())
            max_ver = (docs[0].to_dict() or {}).get("version", 0) if docs else 0
        except Exception:
            max_ver = 0
        new_ver = int(max_ver or 0) + 1
        saved = dict(prompt_dict)
        saved["version"] = new_ver
        saved["updated_at"] = self.utc_now_iso()
        saved["updated_by"] = updated_by
        saved["change_note"] = change_note
        col.document(f"v_{new_ver}").set(saved)
        return saved

    def is_trivia_presented(self, user_id: str, fact_id: str) -> bool:
        safe_id = hashlib.sha256(fact_id.encode("utf-8")).hexdigest()
        doc = (
            self._db.collection("users")
            .document(user_id)
            .collection("trivia_presentation_history")
            .document(safe_id)
            .get()
        )
        return doc.exists

    def record_trivia_presentation(self, user_id: str, fact_id: str) -> None:
        safe_id = hashlib.sha256(fact_id.encode("utf-8")).hexdigest()
        now = self.utc_now_iso()
        (
            self._db.collection("users")
            .document(user_id)
            .collection("trivia_presentation_history")
            .document(safe_id)
            .set({"user_id": user_id, "fact_id": fact_id, "presented_at": now}, merge=True)
        )

    def get_news_presentation(self, user_id: str, story_cluster_id: str) -> dict[str, Any] | None:
        safe_id = hashlib.sha256(story_cluster_id.encode("utf-8")).hexdigest()
        doc = (
            self._db.collection("users")
            .document(user_id)
            .collection("news_presentation_history")
            .document(safe_id)
            .get()
        )
        if doc.exists:
            return doc.to_dict()
        return None

    def record_news_presentation(self, user_id: str, story_cluster_id: str, content_fingerprint: str) -> None:
        safe_id = hashlib.sha256(story_cluster_id.encode("utf-8")).hexdigest()
        now = self.utc_now_iso()
        (
            self._db.collection("users")
            .document(user_id)
            .collection("news_presentation_history")
            .document(safe_id)
            .set(
                {
                    "user_id": user_id,
                    "story_cluster_id": story_cluster_id,
                    "content_fingerprint": content_fingerprint,
                    "presented_at": now,
                },
                merge=True,
            )
        )

    def list_verified_trivia(self, title: str | None = None, tmdb_id: int | None = None) -> list[dict[str, Any]]:
        col = self._db.collection("trivia_facts")
        try:
            if tmdb_id:
                docs = col.where("tmdb_id", "==", tmdb_id).stream()
                return [d.to_dict() for d in docs if d.to_dict()]
            docs = col.limit(50).stream()
            items = [d.to_dict() for d in docs if d.to_dict()]
            if title:
                t_low = title.lower()
                items = [i for i in items if t_low in str(i.get("title", "")).lower()]
            return items
        except Exception as e:
            logger.warning("Failed to list verified trivia from Firestore: %s", e)
            return []

    def add_verified_trivia(self, fact_dict: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        fact_id = fact_dict.get("fact_id") or f"trivia:{fact_dict.get('tmdb_id', 'gen')}:{hash(fact_dict.get('fact_text'))}"
        safe_id = hashlib.sha256(fact_id.encode("utf-8")).hexdigest()
        data = {
            "fact_id": fact_id,
            "title": fact_dict["title"],
            "tmdb_id": fact_dict.get("tmdb_id"),
            "media_type": fact_dict.get("media_type", "movie"),
            "fact_text": fact_dict["fact_text"],
            "source": fact_dict.get("source", "verified_archive"),
            "created_at": now,
        }
        self._db.collection("trivia_facts").document(safe_id).set(data, merge=True)
        res = dict(fact_dict)
        res["fact_id"] = fact_id
        return res

    def list_major_news(self) -> list[dict[str, Any]]:
        col = self._db.collection("entertainment_news")
        try:
            docs = col.where("is_major", "==", True).limit(20).stream()
            items = [d.to_dict() for d in docs if d.to_dict()]
            items.sort(key=lambda x: str(x.get("published_at", "")), reverse=True)
            return items[:20]
        except Exception as e:
            logger.warning("Failed to list major news from Firestore: %s", e)
            return []

    def add_major_news(self, news_dict: dict[str, Any]) -> dict[str, Any]:
        now = self.utc_now_iso()
        story_id = news_dict.get("story_id") or f"news:{news_dict.get('story_cluster_id', 'c')}:{hash(news_dict.get('title'))}"
        safe_id = hashlib.sha256(story_id.encode("utf-8")).hexdigest()
        data = {
            "story_id": story_id,
            "story_cluster_id": news_dict["story_cluster_id"],
            "title": news_dict["title"],
            "summary": news_dict["summary"],
            "source": news_dict.get("source", "verified_media"),
            "news_category": news_dict.get("news_category", "official_announcement"),
            "is_major": bool(news_dict.get("is_major", True)),
            "is_rumor": bool(news_dict.get("is_rumor", False)),
            "published_at": news_dict.get("published_at", now),
            "content_fingerprint": news_dict.get("content_fingerprint", news_dict["title"]),
        }
        self._db.collection("entertainment_news").document(safe_id).set(data, merge=True)
        res = dict(news_dict)
        res["story_id"] = story_id
        return res
