import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { DetailModal } from "../components/DetailModal";
import { MediaCard } from "../components/MediaCard";
import { SearchHeader } from "../components/SearchHeader";
import { Tabs, TabType } from "../components/Tabs";
import { useAuth } from "../context/AuthContext";
import type { MediaDetails, MediaItem, WatchlistItem } from "../types";

const TABS: { id: TabType; label: string }[] = [
  { id: "watchlist", label: "My Queue" },
  { id: "following", label: "Following" },
  { id: "library", label: "My Library" },
  { id: "upcoming", label: "Upcoming" },
  { id: "theatres", label: "In Theatres" },
  { id: "on-air", label: "TV On Air" },
  { id: "trending", label: "Trending" },
];

export function CinequeueDashboard() {
  const { user, logout } = useAuth();

  const [tab, setTab] = useState<TabType>("watchlist");
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<MediaItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [selected, setSelected] = useState<MediaDetails | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const queueKeys = useMemo(
    () => new Set(watchlist.filter((item) => !item.is_owned && (item.status === "queue" || !item.status)).map((item) => `${item.media_type}:${item.tmdb_id ?? item.id}`)),
    [watchlist],
  );

  const followingKeys = useMemo(
    () => new Set(watchlist.filter((item) => !item.is_owned && item.status === "following").map((item) => `${item.media_type}:${item.tmdb_id ?? item.id}`)),
    [watchlist],
  );

  const libraryKeys = useMemo(
    () => new Set(watchlist.filter((item) => item.is_owned).map((item) => `${item.media_type}:${item.tmdb_id ?? item.id}`)),
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

  const loadTab = useCallback(async (activeTab: TabType, searchQuery = "") => {
    if (!user) return;
    setLoading(true);
    setError(null);
    try {
      if (activeTab === "watchlist") {
        const data = await loadWatchlist();
        const queueItems = data.filter((item) => !item.is_owned && (item.status === "queue" || !item.status));
        queueItems.sort((a, b) => {
          const dateA = a.release_date || "";
          const dateB = b.release_date || "";
          if (!dateA && !dateB) return 0;
          if (!dateA) return 1;
          if (!dateB) return -1;
          return dateA.localeCompare(dateB);
        });
        setItems(queueItems);
      } else if (activeTab === "following") {
        const data = await loadWatchlist();
        const followingItems = data.filter((item) => !item.is_owned && item.status === "following");
        followingItems.sort((a, b) => {
          const dateA = a.release_date || "";
          const dateB = b.release_date || "";
          if (!dateA && !dateB) return 0;
          if (!dateA) return 1;
          if (!dateB) return -1;
          return dateA.localeCompare(dateB);
        });
        setItems(followingItems);
      } else if (activeTab === "library") {
        const data = await loadWatchlist();
        setItems(data.filter((item) => item.is_owned));
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
      const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
      const details = await api.details(item.media_type, tmdbId);
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
      await loadTab(tab);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add to queue");
    }
  };

  const removeFromWatchlist = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.removeFromWatchlist(item.media_type, tmdbId);
      await loadWatchlist();
      await loadTab(tab);
      if (selected && selected.id === item.id) {
        setSelected(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove from watchlist");
    }
  };

  const moveToFollowing = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.updateWatchlistItem(item.media_type, tmdbId, undefined, undefined, "following");
      await loadWatchlist();
      await loadTab(tab);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move to following");
    }
  };

  const moveToQueue = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.updateWatchlistItem(item.media_type, tmdbId, undefined, undefined, "queue");
      await loadWatchlist();
      await loadTab(tab);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move to queue");
    }
  };

  const handleUpdateOwned = async (
    item: MediaItem,
    isOwned: boolean,
    format: "electronic" | "cloud" | "hard_copy" = "electronic"
  ) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    const key = `${item.media_type}:${tmdbId}`;
    const exists = watchlist.some((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);

    try {
      if (exists) {
        if (isOwned) {
          await api.updateWatchlistItem(item.media_type, tmdbId, true, format);
        } else {
          await api.removeFromWatchlist(item.media_type, tmdbId);
          if (selected && selected.id === item.id) {
            setSelected(null);
          }
        }
      } else {
        if (isOwned) {
          await api.addToWatchlist({
            media_type: item.media_type,
            tmdb_id: tmdbId,
            title: item.title,
            poster_path: item.poster_url?.replace("https://image.tmdb.org/t/p/w342", "") ?? undefined,
            release_date: item.release_date ?? undefined,
            is_owned: true,
            owned_format: format,
          });
        }
      }
      await loadWatchlist();
      await loadTab(tab);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update library status");
    }
  };

  const sectionTitle =
    tab === "search"
      ? `Results for “${query.trim()}”`
      : TABS.find((entry) => entry.id === tab)?.label ?? "Browse";

  if (!user) return null;

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

      <SearchHeader query={query} setQuery={setQuery} onSubmit={handleSearch} />

      {error ? <div className="error-banner">{error}</div> : null}

      <Tabs tabsList={TABS} activeTab={tab} onChangeTab={setTab} />

      <h2 className="section-title">{sectionTitle}</h2>

      {loading ? (
        <div className="loading">Loading…</div>
      ) : items.length ? (
        <div className="media-grid">
          {items.map((item) => {
            const key = `${item.media_type}:${"tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id}`;
            const isOwned = libraryKeys.has(key);
            const isOnQueue = queueKeys.has(key);
            const isFollowing = followingKeys.has(key);
            const ownedFormat = watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key)?.owned_format || null;
            return (
              <MediaCard
                key={key}
                item={item}
                onOpen={openDetails}
                onAdd={addToWatchlist}
                onRemove={removeFromWatchlist}
                isOnWatchlist={isOnQueue || isFollowing}
                isOnQueue={isOnQueue}
                isFollowing={isFollowing}
                isOwned={isOwned}
                ownedFormat={ownedFormat}
                onMoveToFollowing={moveToFollowing}
                onMoveToQueue={moveToQueue}
              />
            );
          })}
        </div>
      ) : (
        <div className="empty-state">
          {tab === "watchlist"
            ? "Your queue is empty. Search for something to add."
            : tab === "following"
            ? "You are not following any shows or movies. Move them from your queue here once you start watching."
            : tab === "library"
            ? "Your library is empty. Search for something or mark items as owned."
            : "Nothing to show right now."}
        </div>
      )}

      {selected ? (
        <DetailModal
          details={selected}
          isOnQueue={queueKeys.has(`${selected.media_type}:${selected.id}`)}
          isFollowing={followingKeys.has(`${selected.media_type}:${selected.id}`)}
          isOwned={libraryKeys.has(`${selected.media_type}:${selected.id}`)}
          ownedFormat={watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === `${selected.media_type}:${selected.id}`)?.owned_format || null}
          onClose={() => setSelected(null)}
          onAdd={() => void addToWatchlist(selected)}
          onRemove={() => void removeFromWatchlist(selected)}
          onUpdateOwned={handleUpdateOwned}
          onMoveToFollowing={() => void moveToFollowing(selected)}
          onMoveToQueue={() => void moveToQueue(selected)}
        />
      ) : null}
    </div>
  );
}
