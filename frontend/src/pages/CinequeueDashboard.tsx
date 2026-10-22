import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { liveQuery } from "dexie";
import { api } from "../api";
import { AgentLoginBriefing } from "../components/AgentLoginBriefing";
import { AgentModal } from "../components/AgentModal";
import { DetailModal } from "../components/DetailModal";
import { MediaCard } from "../components/MediaCard";
import { MediaCardSkeleton } from "../components/MediaCardSkeleton";
import { SearchHeader } from "../components/SearchHeader";
import { SyncStatusBar } from "../components/SyncStatusBar";
import { Tabs, TabType } from "../components/Tabs";
import { MobileBottomNav } from "../components/MobileBottomNav";
import { useAuth } from "../context/AuthContext";
import { StarRating } from "../components/StarRating";
import { BatchRateModal } from "../components/BatchRateModal";
import { movieService } from "../services/movieService";
import { syncService } from "../services/syncService";
import { formatPosterUrl } from "../utils/mediaUtils";
import { buildQueueAvailabilityStatus, sortQueueItems } from "../utils/queueStatusUtils";
import type { MediaDetails, MediaItem, RatedMovie, SearchFilterState, WatchlistItem } from "../types";

const initialSearchFilters: SearchFilterState = {
  query: "",
  actors: [],
  director: "",
  yearType: "any",
  mediaType: "all",
};

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

export function CinequeueDashboard({ onSignIn }: { onSignIn?: () => void }) {
  const { user: cloudUser, logout, localOwnerId, sessionReady, error: authError, useDeviceWorkspace } = useAuth();
  const ownerId = localOwnerId;
  const user = sessionReady && cloudUser?.uid === ownerId ? cloudUser : null;

  const [tab, setTab] = useState<TabType>("watchlist");
  const [query, setQuery] = useState("");
  const [searchFilters, setSearchFilters] = useState<SearchFilterState>(initialSearchFilters);
  const [remoteItems, setRemoteItems] = useState<MediaItem[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [ratedMovies, setRatedMovies] = useState<RatedMovie[]>([]);
  const [selected, setSelected] = useState<MediaDetails | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isBatchRateModalOpen, setIsBatchRateModalOpen] = useState(false);
  const enrichedShows = useRef(new Set<number>());
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

  useEffect(() => {
    syncService.setWorkspaceOwner(ownerId);
    const subscription = liveQuery(() => Promise.all([
      movieService.getWatchlistForOwner(ownerId), movieService.getRatingsForOwner(ownerId),
    ])).subscribe({
      next: ([localWatch, localRatings]) => { setWatchlist(localWatch); setRatedMovies(localRatings); },
      error: (err) => setError(`Device storage unavailable: ${String(err)}`),
    });
    return () => subscription.unsubscribe();
  }, [ownerId]);

  const loadWatchlist = useCallback(async () => {
    try {
      if (user && navigator.onLine) await syncService.triggerSync(ownerId);
      await reloadFromDb();
    } catch (err) {
      console.error("Failed to load watchlist from server:", err);
      await reloadFromDb();
    }
  }, [user, ownerId, reloadFromDb]);

  const loadRatedMovies = useCallback(async () => {
    try {
      if (user && navigator.onLine) await syncService.triggerSync(ownerId);
      await reloadFromDb();
    } catch (err) {
      console.error("Failed to load ratings from server:", err);
      await reloadFromDb();
    }
  }, [user, ownerId, reloadFromDb]);

  // The provider owns cloud startup; local mutations wake the shared worker.
  useEffect(() => {
    if (user && navigator.onLine) {
      void syncService.triggerSync(ownerId);
    }
  }, [user, ownerId]);

  useEffect(() => {
    if (user && tab === "rated") {
      setLoading(true);
      loadRatedMovies().finally(() => setLoading(false));
    }
  }, [tab, user, loadRatedMovies]);

  // Auto-enrich TV series in watchlist with seasons/next_season if missing from offline storage
  useEffect(() => {
    if (!user || !navigator.onLine || !watchlist.length) return;
    const tvShowsNeedingEnrichment = watchlist.filter(
      (item) => item.media_type === "tv" && !enrichedShows.current.has(item.tmdb_id ?? item.id) &&
        !item.next_season && (!item.seasons || item.seasons.length === 0)
    );
    if (!tvShowsNeedingEnrichment.length) return;

    let active = true;
    const enrichTvShows = async () => {
      let anyEnriched = false;
      for (const item of tvShowsNeedingEnrichment) {
        if (!active) break;
        const tmdbId = item.tmdb_id ?? item.id;
        if (!tmdbId) continue;
        try {
          const details = await api.details("tv", tmdbId);
          if (!active) break;
          await movieService.cacheDetails(ownerId, details);
          enrichedShows.current.add(tmdbId);
          anyEnriched = true;
        } catch (err) {
          console.warn(`Could not enrich TV show ${item.title}:`, err);
        }
      }
      if (active && anyEnriched) {
        await reloadFromDb();
      }
    };

    void enrichTvShows();
    return () => {
      active = false;
    };
  }, [user, watchlist, ownerId, reloadFromDb]);


  const handleSetQuery = (q: string) => {
    setQuery(q);
    setSearchFilters((prev) => ({ ...prev, query: q }));
  };

  const handleUpdateFilters = (newFilters: SearchFilterState) => {
    setSearchFilters(newFilters);
    if (newFilters.query !== query) {
      setQuery(newFilters.query);
    }
  };

  const handleResetFilters = () => {
    setSearchFilters(initialSearchFilters);
    setQuery("");
  };

  // Handle remote data fetching when tab is a remote tab (with local-first IndexedDB caching for discovery feeds)
  useEffect(() => {
    const isDiscoveryTab = ["upcoming", "theatres", "on-air", "trending"].includes(tab);
    const isRemoteTab = isDiscoveryTab || tab === "search";
    if (!isRemoteTab) return;

    let active = true;
    const fetchRemoteData = async () => {
      if (isDiscoveryTab) {
        const cached = await movieService.getCachedDiscoveryFeed<MediaItem>(tab);
        if (active && cached?.items?.length) {
          setRemoteItems(cached.items);
        }
        if (!user || !navigator.onLine) {
          if (active && !cached?.items?.length) {
            setRemoteItems([]);
            setError("Discovery requires an online cloud session. Your saved collection is available on this device.");
          } else if (active) {
            setError(null);
          }
          return;
        }
      } else if (!user || !navigator.onLine) {
        setRemoteItems([]);
        setError("Discovery requires an online cloud session. Your saved collection is available on this device.");
        return;
      }

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
          const hasContent = Boolean(
            query.trim() ||
            searchFilters.actors.length > 0 ||
            searchFilters.director.trim() ||
            searchFilters.yearType !== "any" ||
            searchFilters.mediaType !== "all"
          );
          if (hasContent) {
            data = await api.search({
              ...searchFilters,
              query: query.trim(),
            });
          } else {
            data = [];
          }
        }
        if (active) {
          setRemoteItems(data);
          if (isDiscoveryTab && data.length > 0) {
            void movieService.cacheDiscoveryFeed(tab, data);
          }
        }
      } catch (err) {
        if (active) {
          setError(err instanceof Error ? err.message : "Something went wrong");
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
  }, [tab, user, query, searchFilters]);

  const handleSearch = (event: FormEvent) => {
    event.preventDefault();
    const hasContent = Boolean(
      query.trim() ||
      searchFilters.actors.length > 0 ||
      searchFilters.director.trim() ||
      searchFilters.yearType !== "any" ||
      searchFilters.mediaType !== "all"
    );
    if (!hasContent) return;
    setTab("search");
  };


  const openDetails = async (item: MediaItem) => {
    setError(null);
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    try {
      const cached = await movieService.getCachedDetails(ownerId, item.media_type, tmdbId);
      if (cached) setSelected(cached);
      if (!user || !navigator.onLine) {
        if (!cached) setError("Details have not been saved on this device.");
        return;
      }
      const details = await api.details(item.media_type, tmdbId);
      await movieService.cacheDetails(ownerId, details);
      setSelected(details);
    } catch (err) {
      setError(`Could not refresh details; saved details remain available. ${err instanceof Error ? err.message : ""}`);
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
          details: selected?.id === item.id ? selected : undefined,
        },
        ownerId
      );
      await reloadFromDb();
      setQuery("");
      setTab("watchlist");
      setSelected(null);

      void syncService.triggerSync(ownerId);
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

      void syncService.triggerSync(ownerId);
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

      void syncService.triggerSync(ownerId);
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

      void syncService.triggerSync(ownerId);
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
            ownedFormat: format,
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

      void syncService.triggerSync(ownerId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update library status");
    }
  };

  const handleUpdateWatchOptions = async (
    watchFreeStreaming: boolean,
    watchOnSaleBuy: boolean
  ) => {
    if (!selected) return;
    const tmdbId = "tmdb_id" in selected ? (selected as WatchlistItem).tmdb_id : selected.id;
    try {
      await movieService.saveMovie(
        {
          tmdbId,
          mediaType: selected.media_type,
          title: selected.title,
          watchFreeStreaming,
          watchOnSaleBuy,
        },
        ownerId
      );
      await reloadFromDb();

      void syncService.triggerSync(ownerId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update watch options");
    }
  };

  const handleUpdateRating = async (item: MediaItem, rating: number) => {
    const tmdbId = "tmdb_id" in item ? (item as WatchlistItem).tmdb_id : item.id;
    const itemId = `${item.media_type}_${tmdbId}`;
    const key = `${item.media_type}:${tmdbId}`;
    const isTracked = queueKeys.has(key) || followingKeys.has(key) || libraryKeys.has(key);
    const existingWatch = watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);
    const preservedStatus = existingWatch?.is_owned
      ? "library"
      : existingWatch?.status === "following"
      ? "following"
      : "queue";
    try {
      if (rating <= 0) {
        if (isTracked) {
          await movieService.saveMovie(
            {
              tmdbId,
              mediaType: item.media_type,
              title: item.title,
              rating: null,
              status: preservedStatus,
              watchStatus: "unwatched",
            },
            ownerId
          );
        } else {
          await movieService.deleteMovie(itemId, tmdbId, item.media_type, ownerId);
        }
      } else {
        await movieService.saveMovie(
          {
            tmdbId,
            mediaType: item.media_type,
            title: item.title,
            rating,
            status: isTracked ? preservedStatus : "watched",
            watchStatus: "watched",
          },
          ownerId
        );
      }
      await reloadFromDb();

      void syncService.triggerSync(ownerId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save rating");
    }
  };

  const handleEditRatedMovie = async (movie: RatedMovie, rating: number) => {
    const itemId = `${movie.media_type}_${movie.tmdb_id}`;
    const key = `${movie.media_type}:${movie.tmdb_id}`;
    const isTracked = queueKeys.has(key) || followingKeys.has(key) || libraryKeys.has(key);
    const existingWatch = watchlist.find((i) => `${i.media_type}:${i.tmdb_id ?? i.id}` === key);
    const preservedStatus = existingWatch?.is_owned
      ? "library"
      : existingWatch?.status === "following"
      ? "following"
      : "queue";
    try {
      if (rating <= 0) {
        if (isTracked) {
          await movieService.saveMovie(
            {
              tmdbId: movie.tmdb_id,
              mediaType: movie.media_type,
              title: movie.title,
              rating: null,
              status: preservedStatus,
              watchStatus: "unwatched",
            },
            ownerId
          );
        } else {
          await movieService.deleteMovie(itemId, movie.tmdb_id, movie.media_type, ownerId);
        }
      } else {
        await movieService.saveMovie(
          {
            tmdbId: movie.tmdb_id,
            mediaType: movie.media_type,
            title: movie.title,
            rating,
            status: isTracked ? preservedStatus : "watched",
            watchStatus: "watched",
          },
          ownerId
        );
      }
      await reloadFromDb();

      void syncService.triggerSync(ownerId);
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

  const sectionTitle = useMemo(() => {
    if (tab !== "search") {
      return TABS.find((entry) => entry.id === tab)?.label ?? "Browse";
    }
    const filterParts: string[] = [];
    if (query.trim()) filterParts.push(`“${query.trim()}”`);
    if (searchFilters.actors.length > 0) {
      filterParts.push(`Actor: ${searchFilters.actors.join(" & ")}`);
    }
    if (searchFilters.director.trim()) {
      filterParts.push(`Director: ${searchFilters.director.trim()}`);
    }
    if (searchFilters.yearType === "exact" && searchFilters.year) {
      filterParts.push(`Year ${searchFilters.year}`);
    } else if (searchFilters.yearType === "before" && searchFilters.yearBefore) {
      filterParts.push(`Before ${searchFilters.yearBefore}`);
    } else if (searchFilters.yearType === "after" && searchFilters.yearAfter) {
      filterParts.push(`After ${searchFilters.yearAfter}`);
    } else if (searchFilters.yearType === "range" && (searchFilters.yearFrom || searchFilters.yearTo)) {
      filterParts.push(`${searchFilters.yearFrom || "..."}–${searchFilters.yearTo || "..."}`);
    }
    if (searchFilters.mediaType === "movie") filterParts.push("Movies only");
    if (searchFilters.mediaType === "tv") filterParts.push("TV shows only");
    if (filterParts.length > 0) {
      return `Results for ${filterParts.join(" • ")}`;
    }
    return "Search Results";
  }, [tab, query, searchFilters]);

  return (
    <div className="app-shell">
      {!user && (
        <div role="status" className="local-workspace-bar">
          <div className="local-workspace-bar-text">
            <span className="local-workspace-dot" aria-hidden="true">●</span>
            <span>
              <strong>{ownerId === "guest_local" ? "Device-only workspace" : "Saved account workspace"}:</strong>{" "}
              changes are saved on this device. Sign in when online to sync.
            </span>
            {authError && <p className="local-workspace-error">Cloud connection: {authError}</p>}
          </div>
          <div className="local-workspace-bar-actions">
            <button type="button" className="local-workspace-btn primary" onClick={onSignIn}>
              Sign in to sync
            </button>
            {ownerId !== "guest_local" && (
              <button type="button" className="local-workspace-btn secondary" onClick={useDeviceWorkspace}>
                Use device-only workspace
              </button>
            )}
          </div>
        </div>
      )}
      <SearchHeader
        query={query}
        setQuery={handleSetQuery}
        onSubmit={handleSearch}
        filters={searchFilters}
        onUpdateFilters={handleUpdateFilters}
        onResetFilters={handleResetFilters}
        user={user ?? { display_name: ownerId === "guest_local" ? "This device" : "Saved account workspace" }}
        onLogout={ownerId !== "guest_local" ? logout : undefined}
        onOpenAgentModal={user ? openAgentModal : undefined}
        ownerId={ownerId}
        onDataCleared={reloadFromDb}
      />

      <SyncStatusBar ownerId={ownerId} onDataCleared={reloadFromDb} />

      {user && <AgentLoginBriefing onOpenChat={() => openAgentModal("chat")} />}

      {error ? <div className="error-banner">{error}</div> : null}

      <div className="desktop-only-tabs">
        <Tabs tabsList={TABS} activeTab={tab} onChangeTab={setTab} />
      </div>

      {user && <AgentModal
        isOpen={agentModalOpen}
        initialTab={agentModalTab}
        onClose={() => setAgentModalOpen(false)}
        onWatchlistUpdated={() => {
          void loadWatchlist();
          void loadRatedMovies();
        }}
      />}


      {user && <BatchRateModal
        isOpen={isBatchRateModalOpen}
        onClose={() => setIsBatchRateModalOpen(false)}
        onRatingsAdded={() => void loadRatedMovies()}
      />}

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
        {["trending", "upcoming", "theatres", "on-air"].includes(tab) && (
          <div className="queue-filter-chips mobile-only-discovery-chips" role="group" aria-label="Discovery feeds">
            {(
              [
                { id: "trending", label: "Trending" },
                { id: "upcoming", label: "Upcoming" },
                { id: "theatres", label: "In Theatres" },
                { id: "on-air", label: "TV On Air" },
              ] as const
            ).map((feed) => (
              <button
                key={feed.id}
                type="button"
                className={`filter-chip ${tab === feed.id ? "active" : ""}`}
                onClick={() => setTab(feed.id)}
              >
                {feed.label}
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
