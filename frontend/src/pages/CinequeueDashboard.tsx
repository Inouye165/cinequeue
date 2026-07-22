import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AgentLoginBriefing } from "../components/AgentLoginBriefing";
import { AgentModal } from "../components/AgentModal";
import { DetailModal } from "../components/DetailModal";
import { MediaCard } from "../components/MediaCard";
import { SearchHeader } from "../components/SearchHeader";
import { Tabs, TabType } from "../components/Tabs";
import { useAuth } from "../context/AuthContext";
import { StarRating } from "../components/StarRating";
import type { MediaDetails, MediaItem, RatedMovie, WatchlistItem } from "../types";



const TABS: { id: TabType; label: string }[] = [
  { id: "watchlist", label: "My Queue" },
  { id: "following", label: "Monitoring" },
  { id: "library", label: "My Library" },
  { id: "rated", label: "My Ratings" },
  { id: "upcoming", label: "Upcoming" },
  { id: "theatres", label: "In Theatres" },
  { id: "on-air", label: "TV On Air" },
  { id: "trending", label: "Trending" },
];


export function CinequeueDashboard() {
  const { user, logout } = useAuth();

  const [tab, setTab] = useState<TabType>("watchlist");
  const [query, setQuery] = useState("");
  const [remoteItems, setRemoteItems] = useState<MediaItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [ratedMovies, setRatedMovies] = useState<RatedMovie[]>([]);
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

  const loadRatedMovies = useCallback(async () => {
    if (!user) return [];
    try {
      const data = await api.getRatings();
      setRatedMovies(data);
      return data;
    } catch (err) {
      console.error("Failed to load ratings:", err);
      return [];
    }
  }, [user]);

  // Initial watchlist fetch on mount or user change
  useEffect(() => {
    if (user) {
      setLoading(true);
      Promise.all([loadWatchlist(), loadRatedMovies()]).finally(() => {
        setLoading(false);
      });
    }
  }, [user, loadWatchlist, loadRatedMovies]);

  useEffect(() => {
    if (user && tab === "rated") {
      setLoading(true);
      loadRatedMovies().finally(() => setLoading(false));
    }
  }, [tab, user, loadRatedMovies]);


  // Handle remote data fetching when tab is a remote tab
  useEffect(() => {
    if (!user) return;
    const isRemoteTab = ["search", "upcoming", "theatres", "on-air", "trending"].includes(tab);
    if (!isRemoteTab) return;

    let active = true;
    const fetchRemoteData = async () => {
      setLoading(true);
      setError(null);
      try {
        let data: MediaItem[] = [];
        if (tab === "upcoming") {
          data = await api.upcoming();
        } else if (tab === "theatres") {
          data = await api.nowPlaying();
        } else if (tab === "trending") {
          data = await api.trending();
        } else if (tab === "on-air") {
          data = await api.onAir();
        } else if (tab === "search") {
          if (query.trim()) {
            data = await api.search(query.trim());
          } else {
            data = [];
          }
        }
        if (active) {
          setRemoteItems(data);
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Something went wrong");
          setRemoteItems([]);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };

    void fetchRemoteData();

    return () => {
      active = false;
    };
  }, [tab, user, query]);

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    setTab("search");
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
      setQuery("");
      setTab("watchlist");
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add to queue");
    }
  };

  const removeFromWatchlist = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.removeFromWatchlist(item.media_type, tmdbId);
      await loadWatchlist();
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move to following");
    }
  };

  const moveToQueue = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await api.updateWatchlistItem(item.media_type, tmdbId, undefined, undefined, "queue");
      await loadWatchlist();
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
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update library status");
    }
  };

  const handleUpdateWatchOptions = async (
    watchFreeStreaming: boolean,
    watchOnSaleBuy: boolean
  ) => {
    if (!selected) return;
    try {
      await api.updateWatchlistItem(
        selected.media_type,
        selected.id,
        undefined,
        undefined,
        undefined,
        watchFreeStreaming,
        watchOnSaleBuy
      );
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update watch options");
    }
  };

  const handleUpdateRating = async (item: MediaItem, rating: number) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    const key = `${item.media_type}:${tmdbId}`;
    const exists = watchlist.some((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);

    try {
      if (rating === 0) {
        await api.deleteRating(item.media_type, tmdbId);
      } else {
        await api.rateMovie({
          media_type: item.media_type,
          tmdb_id: tmdbId,
          title: item.title,
          poster_path: item.poster_url?.replace("https://image.tmdb.org/t/p/w342", "") ?? undefined,
          release_date: item.release_date ?? undefined,
          rating,
        });
      }

      if (exists) {
        await api.updateWatchlistItem(
          item.media_type,
          tmdbId,
          undefined,
          undefined,
          undefined,
          undefined,
          undefined,
          rating
        );
      }
      const updatedList = await loadWatchlist();
      await loadRatedMovies();
      if (selected && selected.id === tmdbId) {
        const updatedItem = updatedList.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);
        setSelected((prev) => (prev ? { ...prev, user_rating: updatedItem?.user_rating ?? rating } : null));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rating");
    }
  };

  const handleEditRatedMovie = async (movie: RatedMovie, rating: number) => {
    try {
      if (rating === 0) {
        await api.deleteRating(movie.media_type, movie.tmdb_id);
      } else {
        await api.rateMovie({
          media_type: movie.media_type,
          tmdb_id: movie.tmdb_id,
          title: movie.title,
          poster_path: movie.poster_path,
          release_date: movie.release_date,
          rating,
        });
      }
      await loadRatedMovies();
      await loadWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update rating");
    }
  };


  const localItems = useMemo(() => {
    if (tab === "watchlist") {
      const queueItems = watchlist.filter((item) => {
        if (item.is_owned) return false;
        if (item.status === "queue" || !item.status) return true;
        if (item.status === "following") {
          return (
            item.media_type === "tv" &&
            item.next_season &&
            item.next_season.days_away !== undefined &&
            item.next_season.days_away !== null &&
            item.next_season.days_away >= 0 &&
            item.next_season.days_away <= 30
          );
        }
        return false;
      });
      return [...queueItems].sort((a, b) => {
        const dateA = (a.media_type === "tv" && a.next_season?.air_date) ? a.next_season.air_date : (a.release_date || "");
        const dateB = (b.media_type === "tv" && b.next_season?.air_date) ? b.next_season.air_date : (b.release_date || "");
        if (!dateA && !dateB) return 0;
        if (!dateA) return 1;
        if (!dateB) return -1;
        return dateA.localeCompare(dateB);
      });
    }
    if (tab === "following") {
      const followingItems = watchlist.filter((item) => !item.is_owned && item.status === "following");
      return [...followingItems].sort((a, b) => {
        const dateA = (a.media_type === "tv" && a.next_season?.air_date) ? a.next_season.air_date : (a.release_date || "");
        const dateB = (b.media_type === "tv" && b.next_season?.air_date) ? b.next_season.air_date : (b.release_date || "");
        if (!dateA && !dateB) return 0;
        if (!dateA) return 1;
        if (!dateB) return -1;
        return dateA.localeCompare(dateB);
      });
    }
    if (tab === "library") {
      return watchlist.filter((item) => item.is_owned);
    }
    return [];
  }, [watchlist, tab]);

  const [showAvatarMenu, setShowAvatarMenu] = useState(false);
  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [agentModalTab, setAgentModalTab] = useState<"chat" | "settings">("chat");

  const openAgentModal = (tab: "chat" | "settings" = "chat") => {
    setAgentModalTab(tab);
    setAgentModalOpen(true);
    setShowAvatarMenu(false);
  };

  const isLocalTab = ["watchlist", "following", "library"].includes(tab);
  const items = isLocalTab ? localItems : remoteItems;

  const sectionTitle =
    tab === "search"
      ? `Results for “${query.trim()}”`
      : TABS.find((entry) => entry.id === tab)?.label ?? "Browse";

  if (!user) return null;

  return (
    <div className="app-shell">
      <div className="user-profile-bar">
        <div className="user-info-dropdown-container">
          <button
            className="avatar-dropdown-trigger"
            onClick={() => setShowAvatarMenu((prev) => !prev)}
            aria-label="User Account and AI Agent Menu"
          >
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
            <span className="dropdown-caret">▼</span>
          </button>

          {showAvatarMenu ? (
            <div className="avatar-dropdown-menu">
              <button
                className="dropdown-menu-item"
                onClick={() => openAgentModal("chat")}
              >
                <span className="menu-item-icon">💬</span> Chat with AI Agent
              </button>
              <button
                className="dropdown-menu-item"
                onClick={() => openAgentModal("settings")}
              >
                <span className="menu-item-icon">⚙️</span> AI Personality & Settings
              </button>
              <hr className="dropdown-divider" />
              <button className="dropdown-menu-item logout-item" onClick={logout}>
                <span className="menu-item-icon">🚪</span> Sign Out
              </button>
            </div>
          ) : null}
        </div>
      </div>

      <AgentLoginBriefing onOpenChat={() => openAgentModal("chat")} />

      <SearchHeader query={query} setQuery={setQuery} onSubmit={handleSearch} />

      {error ? <div className="error-banner">{error}</div> : null}

      <Tabs tabsList={TABS} activeTab={tab} onChangeTab={setTab} />

      <AgentModal
        isOpen={agentModalOpen}
        initialTab={agentModalTab}
        onClose={() => setAgentModalOpen(false)}
        onWatchlistUpdated={() => void loadWatchlist()}
      />


      <h2 className="section-title">{sectionTitle}</h2>

      {loading ? (
        <div className="loading">Loading…</div>
      ) : tab === "rated" ? (
        ratedMovies.length ? (
          <div className="media-grid">
            {ratedMovies.map((movie) => (
              <div key={`${movie.media_type}:${movie.tmdb_id}`} className="media-card rated-card" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                <div
                  className="poster-wrapper"
                  onClick={() => void openDetails({ id: movie.tmdb_id, media_type: movie.media_type, title: movie.title })}
                  style={{ cursor: "pointer" }}
                >
                  {movie.poster_url ? (
                    <img src={movie.poster_url} alt={movie.title} className="poster-img" />
                  ) : (
                    <div className="poster-fallback">
                      <span>{movie.title}</span>
                    </div>
                  )}
                  {movie.media_type === "tv" ? <span className="media-type-badge">TV</span> : null}
                </div>
                <div className="card-info" style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
                  <h3 className="card-title" onClick={() => void openDetails({ id: movie.tmdb_id, media_type: movie.media_type, title: movie.title })} style={{ cursor: "pointer" }}>
                    {movie.title}
                  </h3>
                  {movie.release_date ? <span className="card-year">{movie.release_date.slice(0, 4)}</span> : null}
                  <div style={{ margin: "4px 0" }}>
                    <StarRating
                      rating={movie.rating}
                      onRate={(r) => void handleEditRatedMovie(movie, r)}
                      size="md"
                    />
                  </div>
                  <div style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.5)" }}>
                    Rated {movie.rated_ago || "recently"}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state">
            You haven't rated any movies yet. Rate movies when searching, in your Queue, or ask the AI agent to quiz you!
          </div>
        )
      ) : items.length ? (
        <div className="media-grid">
          {items.map((item) => {
            const key = `${item.media_type}:${"tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id}`;
            const isOwned = libraryKeys.has(key);
            const isOnQueue = queueKeys.has(key);
            const isFollowing = followingKeys.has(key);
            const watchItem = watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);
            const ownedFormat = watchItem?.owned_format || null;
            return (
              <MediaCard
                key={key}
                item={item}
                onOpen={openDetails}
                onAdd={addToWatchlist}
                onRemove={removeFromWatchlist}
                onRate={handleUpdateRating}
                userRating={watchItem?.user_rating}
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
            ? "You are not monitoring any shows or movies. Move them from your Queue here to start tracking prices, streaming availability, and alerts."
            : tab === "library"
            ? "Your library is empty. Search for something or mark items as owned."
            : "Nothing to show right now."}
        </div>
      )}


      {selected ? (
        (() => {
          const watchKey = `${selected.media_type}:${selected.id}`;
          const watchItem = watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === watchKey);
          return (
            <DetailModal
              details={selected}
              isOnQueue={queueKeys.has(watchKey)}
              isFollowing={followingKeys.has(watchKey)}
              isOwned={libraryKeys.has(watchKey)}
              ownedFormat={watchItem?.owned_format || null}
              watchFreeStreaming={watchItem?.watch_free_streaming || false}
              watchOnSaleBuy={watchItem?.watch_on_sale_buy || false}
              userRating={watchItem?.user_rating}
              onClose={() => setSelected(null)}
              onAdd={() => void addToWatchlist(selected)}
              onRemove={() => void removeFromWatchlist(selected)}
              onRate={(rating) => void handleUpdateRating(selected, rating)}
              onUpdateOwned={handleUpdateOwned}
              onMoveToFollowing={() => void moveToFollowing(selected)}
              onMoveToQueue={() => void moveToQueue(selected)}
              onUpdateWatchOptions={handleUpdateWatchOptions}
            />
          );
        })()
      ) : null}
    </div>
  );
}
