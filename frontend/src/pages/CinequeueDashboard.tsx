import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "../api";
import { AgentLoginBriefing } from "../components/AgentLoginBriefing";
import { AgentModal } from "../components/AgentModal";
import { DetailModal } from "../components/DetailModal";
import { MediaCard } from "../components/MediaCard";
import { MediaCardSkeleton } from "../components/MediaCardSkeleton";
import { SearchHeader } from "../components/SearchHeader";
import { Tabs, TabType } from "../components/Tabs";
import { MobileBottomNav } from "../components/MobileBottomNav";
import { useAuth } from "../context/AuthContext";
import { StarRating } from "../components/StarRating";
import { BatchRateModal } from "../components/BatchRateModal";
import { movieService } from "../services/movieService";
import { syncService } from "../services/syncService";
import { formatPosterUrl } from "../utils/mediaUtils";
import { buildQueueAvailabilityStatus, sortQueueItems } from "../utils/queueStatusUtils";
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
  const ownerId = user?.uid || user?.email || "guest_local";

  const [tab, setTab] = useState<TabType>("watchlist");
  const [query, setQuery] = useState("");
  const [remoteItems, setRemoteItems] = useState<MediaItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [ratedMovies, setRatedMovies] = useState<RatedMovie[]>([]);
  const [selected, setSelected] = useState<MediaDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isBatchRateModalOpen, setIsBatchRateModalOpen] = useState(false);
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

  const reloadFromDb = useCallback(async () => {
    const localWatch = await movieService.getWatchlistForOwner(ownerId);
    const localRatings = await movieService.getRatingsForOwner(ownerId);
    setWatchlist(localWatch);
    setRatedMovies(localRatings);
  }, [ownerId]);

  // Initial load: IndexedDB rendering FIRST (0ms delay)
  useEffect(() => {
    void reloadFromDb();
  }, [reloadFromDb]);

  const loadWatchlist = useCallback(async () => {
    try {
      if (user && navigator.onLine) {
        const data = await api.watchlist();
        await movieService.migrateServerData(data, [], ownerId);
      }
      await reloadFromDb();
    } catch (err) {
      console.error("Failed to load watchlist from server:", err);
      await reloadFromDb();
    }
  }, [user, ownerId, reloadFromDb]);

  const loadRatedMovies = useCallback(async () => {
    try {
      if (user && navigator.onLine) {
        const data = await api.getRatings();
        await movieService.migrateServerData([], data, ownerId);
      }
      await reloadFromDb();
    } catch (err) {
      console.error("Failed to load ratings from server:", err);
      await reloadFromDb();
    }
  }, [user, ownerId, reloadFromDb]);

  // Background server fetch & sync
  useEffect(() => {
    if (user && navigator.onLine) {
      Promise.all([loadWatchlist(), loadRatedMovies()]).finally(() => {
        void syncService.triggerSync(ownerId);
      });
    }
  }, [user, ownerId, loadWatchlist, loadRatedMovies]);

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
      await movieService.saveMovie(
        {
          tmdbId: item.id,
          mediaType: item.media_type,
          title: item.title,
          posterPath: item.poster_url?.replace("https://image.tmdb.org/t/p/w342", "") ?? undefined,
          releaseDate: item.release_date ?? undefined,
          status: "queue",
        },
        ownerId
      );
      await reloadFromDb();
      setQuery("");
      setTab("watchlist");
      setSelected(null);

      if (user && navigator.onLine) {
        void api.addToWatchlist({
          media_type: item.media_type,
          tmdb_id: item.id,
          title: item.title,
          poster_path: item.poster_url?.replace("https://image.tmdb.org/t/p/w342", "") ?? undefined,
          release_date: item.release_date ?? undefined,
        }).then(() => syncService.triggerSync(ownerId)).catch(console.error);
      } else {
        void syncService.triggerSync(ownerId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add to queue");
    }
  };

  const removeFromWatchlist = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    const itemId = `${item.media_type}_${tmdbId}`;
    try {
      await movieService.deleteMovie(itemId, tmdbId, item.media_type, ownerId);
      await reloadFromDb();
      if (selected && selected.id === item.id) {
        setSelected(null);
      }

      if (user && navigator.onLine) {
        void api.removeFromWatchlist(item.media_type, tmdbId)
          .then(() => syncService.triggerSync(ownerId))
          .catch(console.error);
      } else {
        void syncService.triggerSync(ownerId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not remove from watchlist");
    }
  };

  const moveToFollowing = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await movieService.saveMovie(
        {
          tmdbId,
          mediaType: item.media_type,
          title: item.title,
          status: "following",
        },
        ownerId
      );
      await reloadFromDb();

      if (user && navigator.onLine) {
        void api.updateWatchlistItem(item.media_type, tmdbId, undefined, undefined, "following")
          .then(() => syncService.triggerSync(ownerId))
          .catch(console.error);
      } else {
        void syncService.triggerSync(ownerId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not move to following");
    }
  };

  const moveToQueue = async (item: MediaItem) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await movieService.saveMovie(
        {
          tmdbId,
          mediaType: item.media_type,
          title: item.title,
          status: "queue",
        },
        ownerId
      );
      await reloadFromDb();

      if (user && navigator.onLine) {
        void api.updateWatchlistItem(item.media_type, tmdbId, undefined, undefined, "queue")
          .then(() => syncService.triggerSync(ownerId))
          .catch(console.error);
      } else {
        void syncService.triggerSync(ownerId);
      }
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
    try {
      if (isOwned) {
        await movieService.saveMovie(
          {
            tmdbId,
            mediaType: item.media_type,
            title: item.title,
            isOwned: true,
            status: "library",
          },
          ownerId
        );
      } else {
        const itemId = `${item.media_type}_${tmdbId}`;
        await movieService.deleteMovie(itemId, tmdbId, item.media_type, ownerId);
        if (selected && selected.id === item.id) {
          setSelected(null);
        }
      }
      await reloadFromDb();

      if (user && navigator.onLine) {
        if (isOwned) {
          void api.addToWatchlist({
            media_type: item.media_type,
            tmdb_id: tmdbId,
            title: item.title,
            is_owned: true,
            owned_format: format,
          }).then(() => syncService.triggerSync(ownerId)).catch(console.error);
        } else {
          void api.removeFromWatchlist(item.media_type, tmdbId)
            .then(() => syncService.triggerSync(ownerId))
            .catch(console.error);
        }
      } else {
        void syncService.triggerSync(ownerId);
      }
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
      await reloadFromDb();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update watch options");
    }
  };

  const handleUpdateRating = async (item: MediaItem, rating: number) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      await movieService.saveMovie(
        {
          tmdbId,
          mediaType: item.media_type,
          title: item.title,
          rating,
          status: rating > 0 ? "watched" : "queue",
          watchStatus: rating > 0 ? "watched" : "unwatched",
        },
        ownerId
      );
      await reloadFromDb();

      if (user && navigator.onLine) {
        if (rating === 0) {
          void api.deleteRating(item.media_type, tmdbId).then(() => syncService.triggerSync(ownerId)).catch(console.error);
        } else {
          void api.rateMovie({
            media_type: item.media_type,
            tmdb_id: tmdbId,
            title: item.title,
            rating,
          }).then(() => syncService.triggerSync(ownerId)).catch(console.error);
        }
      } else {
        void syncService.triggerSync(ownerId);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rating");
    }
  };

  const handleEditRatedMovie = async (movie: RatedMovie, rating: number) => {
    try {
      await movieService.saveMovie(
        {
          tmdbId: movie.tmdb_id,
          mediaType: movie.media_type,
          title: movie.title,
          rating,
          status: rating > 0 ? "watched" : "queue",
          watchStatus: rating > 0 ? "watched" : "unwatched",
        },
        ownerId
      );
      await reloadFromDb();

      if (user && navigator.onLine) {
        if (rating === 0) {
          void api.deleteRating(movie.media_type, movie.tmdb_id).then(() => syncService.triggerSync(ownerId)).catch(console.error);
        } else {
          void api.rateMovie({
            media_type: movie.media_type,
            tmdb_id: movie.tmdb_id,
            title: movie.title,
            rating,
          }).then(() => syncService.triggerSync(ownerId)).catch(console.error);
        }
      } else {
        void syncService.triggerSync(ownerId);
      }
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
      return sortQueueItems(queueItems);
    }
    if (tab === "following") {
      const followingItems = watchlist.filter(
        (item) => !item.is_owned && item.status === "following"
      );
      return sortQueueItems(followingItems);
    }
    if (tab === "library") {
      return sortQueueItems(watchlist.filter((item) => item.is_owned));
    }
    return [];
  }, [watchlist, tab]);

  const [queueFilter, setQueueFilter] = useState<"all" | "available" | "upcoming" | "tv" | "movies">("all");

  const [agentModalOpen, setAgentModalOpen] = useState(false);
  const [agentModalTab, setAgentModalTab] = useState<"chat" | "settings" | "logs">("chat");

  const openAgentModal = (tab: "chat" | "settings" | "logs" = "chat") => {
    setAgentModalTab(tab);
    setAgentModalOpen(true);
  };

  const isLocalTab = ["watchlist", "following", "library"].includes(tab);
  const rawItems = isLocalTab ? localItems : remoteItems;

  const items = useMemo(() => {
    if (queueFilter === "all") return rawItems;
    return rawItems.filter((item) => {
      const status = buildQueueAvailabilityStatus(item);
      if (queueFilter === "available") {
        return status.state === "available" || status.state === "partially_available" || status.state === "complete";
      }
      if (queueFilter === "upcoming") {
        return status.state === "upcoming" || status.state === "releasing_today" || status.state === "confirmed_tbd";
      }
      if (queueFilter === "tv") return item.media_type === "tv";
      if (queueFilter === "movies") return item.media_type === "movie";
      return true;
    });
  }, [rawItems, queueFilter]);

  const sectionTitle =
    tab === "search"
      ? `Results for “${query.trim()}”`
      : TABS.find((entry) => entry.id === tab)?.label ?? "Browse";

  if (!user) return null;

  return (
    <div className="app-shell">
      <SearchHeader
        query={query}
        setQuery={setQuery}
        onSubmit={handleSearch}
        user={user}
        onLogout={logout}
        onOpenAgentModal={openAgentModal}
        ownerId={ownerId}
        onDataCleared={reloadFromDb}
      />

      <AgentLoginBriefing onOpenChat={() => openAgentModal("chat")} />

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="desktop-only-tabs">
        <Tabs tabsList={TABS} activeTab={tab} onChangeTab={setTab} />
      </div>

      <AgentModal
        isOpen={agentModalOpen}
        initialTab={agentModalTab}
        onClose={() => setAgentModalOpen(false)}
        onWatchlistUpdated={() => {
          void loadWatchlist();
          void loadRatedMovies();
        }}
      />


      <BatchRateModal
        isOpen={isBatchRateModalOpen}
        onClose={() => setIsBatchRateModalOpen(false)}
        onRatingsAdded={() => void loadRatedMovies()}
      />

      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "16px", flexWrap: "wrap", gap: "12px" }}>
        <h2 className="section-title" style={{ margin: 0 }}>{sectionTitle}</h2>
        {isLocalTab && (
          <div className="queue-filter-chips" role="tablist" aria-label="Filter queue items">
            {(
              [
                { id: "all", label: "All" },
                { id: "available", label: "Available now" },
                { id: "upcoming", label: "Upcoming" },
                { id: "tv", label: "TV" },
                { id: "movies", label: "Movies" },
              ] as const
            ).map((chip) => (
              <button
                key={chip.id}
                type="button"
                className={`filter-chip ${queueFilter === chip.id ? "active" : ""}`}
                onClick={() => setQueueFilter(chip.id)}
                role="tab"
                aria-selected={queueFilter === chip.id}
              >
                {chip.label}
              </button>
            ))}
          </div>
        )}
        {tab === "rated" && (
          <button
            className="btn-primary"
            onClick={() => setIsBatchRateModalOpen(true)}
            style={{ display: "flex", alignItems: "center", gap: "6px" }}
          >
            <span>⭐ Add Ratings</span>
          </button>
        )}
      </div>

      {loading ? (
        <MediaCardSkeleton count={6} />
      ) : tab === "rated" ? (
        ratedMovies.length ? (
          <div className="media-grid">
            {ratedMovies.map((movie) => {
              const posterUrl = formatPosterUrl(movie.poster_url || movie.poster_path);
              return (
                <div key={`${movie.media_type}:${movie.tmdb_id}`} className="media-card rated-card" style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
                  <div
                    className="poster-wrapper"
                    onClick={() => void openDetails({ id: movie.tmdb_id, media_type: movie.media_type, title: movie.title })}
                    style={{ cursor: "pointer" }}
                  >
                    {posterUrl ? (
                      <img src={posterUrl} alt={movie.title} className="poster-img" />
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
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: "4px" }}>
                      <span style={{ fontSize: "0.75rem", color: "rgba(255, 255, 255, 0.5)" }}>
                        Rated {movie.rated_ago || "recently"}
                      </span>
                      <button
                        type="button"
                        title="Remove rating"
                        onClick={(e) => {
                          e.stopPropagation();
                          void handleEditRatedMovie(movie, 0);
                        }}
                        style={{
                          background: "none",
                          border: "none",
                          color: "rgba(255, 99, 132, 0.8)",
                          cursor: "pointer",
                          fontSize: "0.85rem",
                          padding: "2px 6px",
                        }}
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
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
            const cardItem = watchItem ? { ...item, ...watchItem } : item;
            return (
              <MediaCard
                key={key}
                item={cardItem}
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

      <MobileBottomNav activeTab={tab} onChangeTab={setTab} />
    </div>
  );
}
