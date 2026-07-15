import type { MediaDetails, MediaItem, WatchlistItem } from "./types";

export interface FirebaseConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
  appId: string;
  messagingSenderId?: string;
}

export interface CsrfResponse {
  csrf_token: string;
}

export interface UserMe {
  uid: string;
  email: string;
  display_name?: string;
  photo_url?: string;
}

function getCookie(name: string): string | null {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop()?.split(";").shift() || null;
  return null;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const reqInit = { ...init };
  reqInit.credentials = "include"; // Ensure cookies are sent
  
  const method = reqInit.method?.toUpperCase() || "GET";
  if (["POST", "PUT", "DELETE", "PATCH"].includes(method)) {
    const csrfToken = getCookie("cinequeue_csrf");
    if (csrfToken) {
      const headers = { ...(reqInit.headers as Record<string, string>) };
      headers["X-CSRF-Token"] = csrfToken;
      reqInit.headers = headers;
    }
  }

  const response = await fetch(path, reqInit);
  if (!response.ok) {
    if (response.status === 401) {
      window.dispatchEvent(new CustomEvent("cinequeue-unauthorized"));
    }
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || "Request failed");
  }
  return response.json();
}

export const api = {
  // Auth endpoints
  firebaseConfig: () => request<FirebaseConfig>("/api/auth/config"),
  csrf: () => request<CsrfResponse>("/api/auth/csrf"),
  createSession: (idToken: string, csrfToken: string) =>
    request<{ status: string }>("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_token: idToken, csrf_token: csrfToken }),
    }),
  me: () => request<UserMe>("/api/auth/me"),
  logout: (csrfToken: string) =>
    request<{ status: string }>("/api/auth/logout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ csrf_token: csrfToken }),
    }),

  // Watchlist & movies endpoints
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
