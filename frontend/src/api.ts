import type { MediaDetails, MediaItem, WatchlistItem } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init);
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

export const api = {
  search: (q: string) => request<MediaItem[]>(`/api/search?q=${encodeURIComponent(q)}`),
  upcoming: () => request<MediaItem[]>("/api/upcoming"),
  nowPlaying: () => request<MediaItem[]>("/api/now-playing"),
  trending: () => request<MediaItem[]>("/api/trending"),
  onAir: () => request<MediaItem[]>("/api/on-air"),
  details: (mediaType: string, id: number) =>
    request<MediaDetails>(`/api/${mediaType}/${id}`),
  watchlist: () => request<WatchlistItem[]>("/api/watchlist"),
  addToWatchlist: (item: Partial<WatchlistItem>) =>
    request<WatchlistItem>("/api/watchlist", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(item),
    }),
  removeFromWatchlist: (mediaType: string, tmdbId: number) =>
    request<{ status: string }>(`/api/watchlist/${mediaType}/${tmdbId}`, {
      method: "DELETE",
    }),
};
