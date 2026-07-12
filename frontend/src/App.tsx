import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";
import { api } from "./api";
import { DetailModal } from "./components/DetailModal";
import { MediaCard } from "./components/MediaCard";
import type { MediaDetails, MediaItem, WatchlistItem } from "./types";

type Tab = "watchlist" | "upcoming" | "theatres" | "trending" | "on-air" | "search";

const TABS: { id: Tab; label: string }[] = [
  { id: "watchlist", label: "My Queue" },
  { id: "upcoming", label: "Upcoming" },
  { id: "theatres", label: "In Theatres" },
  { id: "on-air", label: "TV On Air" },
  { id: "trending", label: "Trending" },
];

export default function App() {
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
    const data = await api.watchlist();
    setWatchlist(data);
    return data;
  }, []);

  const loadTab = useCallback(async (activeTab: Tab, searchQuery = "") => {
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
  }, [loadWatchlist]);

  useEffect(() => {
    void loadTab(tab);
  }, [tab, loadTab]);

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

  return (
    <div className="app-shell">
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
