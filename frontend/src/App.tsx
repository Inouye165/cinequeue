import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { DetailModal } from "./components/DetailModal";
import { MediaCard } from "./components/MediaCard";
import type { MediaDetails, MediaItem, WatchlistItem } from "./types";
import { AuthProvider, useAuth } from "./context/AuthContext";

type Tab = "watchlist" | "upcoming" | "theatres" | "trending" | "on-air" | "search";

const TABS: { id: Tab; label: string }[] = [
  { id: "watchlist", label: "My Queue" },
  { id: "upcoming", label: "Upcoming" },
  { id: "theatres", label: "In Theatres" },
  { id: "on-air", label: "TV On Air" },
  { id: "trending", label: "Trending" },
];

function CinequeueApp() {
  const { user, loading: authLoading, error: authError, loginWithGoogle, logout } = useAuth();

  const [tab, setTab] = useState<Tab>("watchlist");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MediaItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selected, setSelected] = useState<MediaDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const watchlistKeys = useMemo(
    () => new Set(watchlist.map((item) => `${item.media_type}:${item.tmdb_id ?? item.id}`)),
    [watchlist],
  );

  const loadWatchlist = useCallback(async () => {
    if (!user) return [];
    try {
      const data = await api.watchlist();
      setWatchlist(data);
      return data;
    } catch (err) {
      console.error("Failed to load watchlist:", err);
      return [];
    }
  }, [user]);

  const loadTab = useCallback(async (activeTab: Tab, searchQuery = "") => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      if (activeTab === "watchlist") {
        const data = await loadWatchlist();
        setItems(data);
      } else if (activeTab === "search") {
        if (!searchQuery.trim()) {
          setItems([]);
          return;
        }
        const data = await api.search(searchQuery);
        setItems(data);
      } else if (activeTab === "upcoming") {
        setItems(await api.upcoming());
      } else if (activeTab === "theatres") {
        setItems(await api.nowPlaying());
      } else if (activeTab === "trending") {
        setItems(await api.trending());
      } else if (activeTab === "on-air") {
        setItems(await api.onAir());
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [loadWatchlist, user]);

  useEffect(() => {
    if (user) {
      void loadTab(tab);
    }
  }, [tab, loadTab, user]);

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setTab("search");
    void loadTab("search", query.trim());
  };

  const openDetails = async (item: MediaItem) => {
    setError(null);
    try {
      const details = await api.details(item.media_type, item.id);
      setSelected(details);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load details");
    }
  };

  const addToWatchlist = async (item: MediaItem) => {
    try {
      await api.addToWatchlist({
        media_type: item.media_type,
        tmdb_id: item.id,
        title: item.title,
        poster_path: item.poster_url?.replace("https://image.tmdb.org/t/p/w342", "") ?? undefined,
        release_date: item.release_date ?? undefined,
      });
      await loadWatchlist();
      if (tab === "watchlist") {
        await loadTab("watchlist");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add to queue");
    }
  };

  const removeFromWatchlist = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.removeFromWatchlist(item.media_type, tmdbId);
      await loadWatchlist();
      if (tab === "watchlist") {
        await loadTab("watchlist");
      }
      if (selected && selected.id === item.id) {
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove from queue");
    }
  };

  const sectionTitle =
    tab === "search"
      ? `Results for “${query.trim()}”`
      : TABS.find((entry) => entry.id === tab)?.label ?? "Browse";

  if (authLoading) {
    return (
      <div className="auth-loading">
        <div className="spinner"></div>
        <p>Verifying session…</p>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="auth-container">
        <div className="auth-card">
          <h1>Cinequeue</h1>
          <p>
            Track what you want to watch, see days until release, where to stream or buy,
            and skim reviews and headlines in one place.
          </p>
          
          {authError ? (
            <div style={{ marginBottom: "20px" }} className="error-banner">{authError}</div>
          ) : null}

          <button className="login-btn" onClick={loginWithGoogle}>
            <svg className="google-icon" viewBox="0 0 24 24" width="20" height="20">
              <path
                fill="#4285F4"
                d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
              />
              <path
                fill="#34A853"
                d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
              />
              <path
                fill="#FBBC05"
                d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z"
              />
              <path
                fill="#EA4335"
                d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z"
              />
            </svg>
            Sign in with Google
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <div className="user-profile-bar">
        <div className="user-info">
          {user.photo_url ? (
            <img src={user.photo_url} alt={user.display_name || user.email} className="user-avatar" />
          ) : (
            <div className="user-avatar-fallback">
              {(user.display_name || user.email)[0].toUpperCase()}
            </div>
          )}
          <div className="user-details">
            <span className="user-name">{user.display_name || user.email}</span>
            <span className="user-email">{user.email}</span>
          </div>
        </div>
        <button className="logout-btn" onClick={logout}>Sign Out</button>
      </div>

      <header className="hero">
        <div>
          <h1>Cinequeue</h1>
          <p>
            Track what you want to watch, see days until release, where to stream or buy,
            and skim reviews and headlines in one place.
          </p>
        </div>
        <form className="search-bar" onSubmit={handleSearch}>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search movies and TV…"
          />
          <button type="submit">Search</button>
        </form>
      </header>

      {error ? <div className="error-banner">{error}</div> : null}

      <nav className="tabs">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            className={`tab ${tab === entry.id ? "active" : ""}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
        {tab === "search" ? <span className="tab active">Search</span> : null}
      </nav>

      <h2 className="section-title">{sectionTitle}</h2>

      {loading ? (
        <div className="loading">Loading…</div>
      ) : items.length ? (
        <div className="media-grid">
          {items.map((item) => {
            const key = `${item.media_type}:${"tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id}`;
            return (
              <MediaCard
                key={key}
                item={item}
                onOpen={openDetails}
                onAdd={addToWatchlist}
                onRemove={removeFromWatchlist}
                isOnWatchlist={watchlistKeys.has(key)}
              />
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          {tab === "watchlist"
            ? "Your queue is empty. Search for something to add."
            : "Nothing to show right now."}
        </div>
      )}

      {selected ? (
        <DetailModal
          details={selected}
          isOnWatchlist={watchlistKeys.has(`${selected.media_type}:${selected.id}`)}
          onClose={() => setSelected(null)}
          onAdd={() => void addToWatchlist(selected)}
          onRemove={() => void removeFromWatchlist(selected)}
        />
      ) : null}
    </div>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <CinequeueApp />
    </AuthProvider>
  );
}
