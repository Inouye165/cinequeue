"""Tests for watchlist repository implementations and backend configuration."""

import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# SQLite repository tests
# ---------------------------------------------------------------------------

class TestSqliteRepository:
    """Test the SQLite watchlist repository with a real temp database."""

    @pytest.fixture(autouse=True)
    def sqlite_repo(self):
        """Create a fresh SQLite repo in a temp directory."""
        tmpdir = tempfile.mkdtemp(prefix="cinequeue_repo_test_")
        with patch.dict(os.environ, {"DATA_DIR": tmpdir}):
            # Reload config so DATA_DIR / DB_PATH pick up the temp dir
            import importlib
            import app.config
            importlib.reload(app.config)
            from app.sqlite_repo import SqliteWatchlistRepository
            self.repo = SqliteWatchlistRepository()
            yield
            importlib.reload(app.config)

    def test_list_empty(self):
        assert self.repo.list_items("local_test_user") == []

    def test_add_item(self):
        result = self.repo.add_item("local_test_user", "movie", 12345, "Test Movie", "/poster.jpg", "2024-06-01")
        assert result["media_type"] == "movie"
        assert result["tmdb_id"] == 12345
        assert result["title"] == "Test Movie"
        assert result["poster_path"] == "/poster.jpg"
        assert result["release_date"] == "2024-06-01"
        assert "added_at" in result

        items = self.repo.list_items("local_test_user")
        assert len(items) == 1
        assert items[0]["tmdb_id"] == 12345

    def test_add_duplicate(self):
        self.repo.add_item("local_test_user", "movie", 100, "Movie A", None, None)
        from app.repository import DuplicateItemError
        with pytest.raises(DuplicateItemError):
            self.repo.add_item("local_test_user", "movie", 100, "Movie A", None, None)

    def test_add_same_id_different_type(self):
        """movie/100 and tv/100 are distinct items."""
        self.repo.add_item("local_test_user", "movie", 100, "Movie A", None, None)
        self.repo.add_item("local_test_user", "tv", 100, "Show A", None, None)
        assert len(self.repo.list_items("local_test_user")) == 2

    def test_remove_item(self):
        self.repo.add_item("local_test_user", "movie", 200, "Movie B", None, None)
        assert self.repo.remove_item("local_test_user", "movie", 200) is True
        assert self.repo.list_items("local_test_user") == []

    def test_remove_nonexistent(self):
        assert self.repo.remove_item("local_test_user", "movie", 9999) is False

    def test_clear_all(self):
        self.repo.add_item("local_test_user", "movie", 1, "A", None, None)
        self.repo.add_item("local_test_user", "tv", 2, "B", None, None)
        self.repo.clear_all("local_test_user")
        assert self.repo.list_items("local_test_user") == []

    def test_ordering(self):
        """Items should be returned in reverse chronological order."""
        import time
        self.repo.add_item("local_test_user", "movie", 1, "First", None, None)
        time.sleep(0.05)  # ensure distinct timestamps
        self.repo.add_item("local_test_user", "movie", 2, "Second", None, None)
        items = self.repo.list_items("local_test_user")
        assert items[0]["title"] == "Second"
        assert items[1]["title"] == "First"


# ---------------------------------------------------------------------------
# Firestore repository tests (mocked — no production access)
# ---------------------------------------------------------------------------

class TestFirestoreRepository:
    """Test the Firestore repository with a fully mocked Firestore client."""

    @pytest.fixture(autouse=True)
    def firestore_repo(self):
        """Set up a FirestoreWatchlistRepository with a mocked client."""
        # Mock the entire google.cloud.firestore module
        mock_client_instance = MagicMock()
        mock_users_collection = MagicMock()
        mock_user_document = MagicMock()
        mock_watchlist_collection = MagicMock()

        mock_client_instance.collection.return_value = mock_users_collection
        mock_users_collection.document.return_value = mock_user_document
        mock_user_document.collection.return_value = mock_watchlist_collection

        with patch("app.firestore_repo.firestore") as mock_firestore_module:
            mock_firestore_module.Client.return_value = mock_client_instance
            mock_firestore_module.Query.DESCENDING = "DESCENDING"

            from app.firestore_repo import FirestoreWatchlistRepository
            self.repo = FirestoreWatchlistRepository(project="test-project")
            self.mock_collection = mock_watchlist_collection
            self.mock_client = mock_client_instance
            self.mock_users_collection = mock_users_collection
            self.mock_user_document = mock_user_document
            yield

    def _make_mock_doc(self, data: dict, doc_id: str = "mock_id"):
        doc = MagicMock()
        doc.to_dict.return_value = data
        doc.id = doc_id
        doc.exists = True
        doc.reference = MagicMock()
        return doc

    def test_list_empty(self):
        query = MagicMock()
        query.stream.return_value = []
        self.mock_collection.order_by.return_value = query

        assert self.repo.list_items("user123") == []
        self.mock_users_collection.collection = MagicMock() # check path
        self.mock_users_collection.document.assert_called_with("user123")
        self.mock_user_document.collection.assert_called_with("watchlist")

    def test_list_items(self):
        doc_data = {
            "media_type": "movie",
            "tmdb_id": 123,
            "title": "Test",
            "poster_path": None,
            "release_date": None,
            "added_at": "2024-01-01T00:00:00+00:00",
        }
        mock_doc = self._make_mock_doc(doc_data, "movie_123")
        query = MagicMock()
        query.stream.return_value = [mock_doc]
        self.mock_collection.order_by.return_value = query

        items = self.repo.list_items("user123")
        assert len(items) == 1
        assert items[0]["tmdb_id"] == 123
        self.mock_collection.order_by.assert_called_with("added_at", direction="DESCENDING")
        self.mock_users_collection.document.assert_called_with("user123")

    def test_add_item(self):
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot
        self.mock_collection.document.return_value = mock_doc_ref

        result = self.repo.add_item("user123", "movie", 12345, "Test Movie", "/poster.jpg", "2024-06-01")

        self.mock_collection.document.assert_called_with("movie_12345")
        mock_doc_ref.set.assert_called_once()
        assert result["media_type"] == "movie"
        assert result["tmdb_id"] == 12345
        assert result["title"] == "Test Movie"
        assert "added_at" in result
        self.mock_users_collection.document.assert_called_with("user123")

    def test_add_duplicate(self):
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True  # Document already exists
        mock_doc_ref.get.return_value = mock_snapshot
        self.mock_collection.document.return_value = mock_doc_ref

        from app.repository import DuplicateItemError
        with pytest.raises(DuplicateItemError):
            self.repo.add_item("user123", "movie", 12345, "Test Movie", None, None)

        mock_doc_ref.set.assert_not_called()
        self.mock_users_collection.document.assert_called_with("user123")

    def test_remove_item(self):
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = True
        mock_doc_ref.get.return_value = mock_snapshot
        self.mock_collection.document.return_value = mock_doc_ref

        assert self.repo.remove_item("user123", "movie", 12345) is True
        mock_doc_ref.delete.assert_called_once()
        self.mock_users_collection.document.assert_called_with("user123")

    def test_remove_nonexistent(self):
        mock_doc_ref = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.exists = False
        mock_doc_ref.get.return_value = mock_snapshot
        self.mock_collection.document.return_value = mock_doc_ref

        assert self.repo.remove_item("user123", "movie", 9999) is False
        mock_doc_ref.delete.assert_not_called()
        self.mock_users_collection.document.assert_called_with("user123")

    def test_clear_all(self):
        mock_doc1 = self._make_mock_doc({}, "movie_1")
        mock_doc2 = self._make_mock_doc({}, "tv_2")
        self.mock_collection.stream.return_value = [mock_doc1, mock_doc2]

        self.repo.clear_all("user123")

        mock_doc1.reference.delete.assert_called_once()
        mock_doc2.reference.delete.assert_called_once()
        self.mock_users_collection.document.assert_called_with("user123")


# ---------------------------------------------------------------------------
# Configuration / backend selection tests
# ---------------------------------------------------------------------------

class TestBackendConfiguration:
    """Test that WATCHLIST_BACKEND selects the correct repository."""

    def test_default_backend_is_sqlite(self):
        """When WATCHLIST_BACKEND is unset, config defaults to 'sqlite'."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("WATCHLIST_BACKEND", None)
            import importlib
            import app.config
            importlib.reload(app.config)
            assert app.config.WATCHLIST_BACKEND == "sqlite"
            # Restore
            os.environ["WATCHLIST_BACKEND"] = "sqlite"
            importlib.reload(app.config)

    def test_firestore_backend_selection(self):
        """When WATCHLIST_BACKEND=firestore, config reflects it."""
        with patch.dict(os.environ, {"WATCHLIST_BACKEND": "firestore"}):
            import importlib
            import app.config
            importlib.reload(app.config)
            assert app.config.WATCHLIST_BACKEND == "firestore"
            # Restore
            os.environ["WATCHLIST_BACKEND"] = "sqlite"
            importlib.reload(app.config)

    def test_config_without_env_file(self):
        """Config should work when no .env file exists."""
        with patch.dict(os.environ, {"WATCHLIST_BACKEND": "sqlite"}, clear=False):
            import importlib
            import app.config
            importlib.reload(app.config)
            # Should not raise; WATCHLIST_BACKEND should still work
            assert app.config.WATCHLIST_BACKEND == "sqlite"
